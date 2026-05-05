from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from .sanitize import safe_preview, sanitize
from .swear_meter import analyze_user_message, empty_swear_meter, finalize_swear_meter, merge_swear_meter
from .utils import (
    count_files,
    default_home,
    file_info,
    open_sqlite_readonly,
    path_for_display,
    query_rows,
    safe_relpath,
    table_count,
    timestamp_to_iso,
)


TOKEN_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")
MAX_FULL_SESSION_BYTES = 2_000_000
SESSION_TAIL_BYTES = 256_000
MAX_PARSED_SESSION_FILES = 450
SWEAR_CANDIDATE_MARKERS = (
    b"session_meta",
    b"user_message",
    b'"role":"user"',
    b'"role": "user"',
)
_SWEAR_SCAN_CACHE: dict[tuple[str, str, str, int, int], dict[str, Any]] = {}


def _empty_token_totals() -> dict[str, int]:
    return {key: 0 for key in TOKEN_KEYS}


def add_token_totals(target: dict[str, int], usage: dict[str, Any] | None) -> None:
    if not isinstance(usage, dict):
        return
    for key in TOKEN_KEYS:
        try:
            target[key] += int(usage.get(key) or 0)
        except (TypeError, ValueError):
            continue


def _base_session(path: Path, *, archive: str, root: Path | None = None, file_stat: Any | None = None) -> dict[str, Any]:
    stat = file_stat or path.stat()
    return {
        "id": None,
        "title": None,
        "archive": archive,
        "path": safe_relpath(path, root) if root else path_for_display(path),
        "bytes": stat.st_size,
        "modified": timestamp_to_iso(stat.st_mtime),
        "firstTimestamp": None,
        "lastTimestamp": None,
        "lineCount": 0,
        "eventCounts": Counter(),
        "payloadTypes": Counter(),
        "tools": Counter(),
        "models": Counter(),
        "commands": 0,
        "commandFailures": 0,
        "webSearches": 0,
        "images": 0,
        "userMessages": 0,
        "assistantMessages": 0,
        "contextWindows": Counter(),
        "latestTokenUsage": _empty_token_totals(),
        "lastTurnUsage": _empty_token_totals(),
        "tokenEvents": 0,
        "cwd": None,
        "source": None,
        "originator": None,
        "modelProvider": None,
        "cliVersion": None,
        "agentRole": None,
        "agentNickname": None,
        "recentFailures": [],
        "swearMeter": empty_swear_meter(),
        "_swearMessageIds": set(),
    }


def scan_session_file(path: Path, *, archive: str, root: Path | None = None) -> dict[str, Any]:
    session = _base_session(path, archive=archive, root=root)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                continue
            _apply_session_line(session, raw_line)
    return _finalize_session(path, session)


def scan_session_file_fast(path: Path, *, archive: str, root: Path | None = None) -> dict[str, Any]:
    session = _base_session(path, archive=archive, root=root)
    session["partial"] = True
    try:
        with path.open("rb") as handle:
            head = handle.read(min(262_144, session["bytes"]))
            if session["bytes"] > SESSION_TAIL_BYTES:
                handle.seek(max(0, session["bytes"] - SESSION_TAIL_BYTES))
                tail = handle.read()
            else:
                tail = b""
    except OSError as exc:
        session["error"] = safe_preview(exc)
        return _finalize_session(path, session)
    chunks = [head]
    if tail:
        chunks.append(tail.split(b"\n", 1)[-1])
    for chunk in chunks:
        for raw in chunk.decode("utf-8", errors="replace").splitlines():
            if raw.strip():
                _apply_session_line(session, raw)
    full_swear_meter = scan_session_swear_meter(path, archive=archive, root=root)
    session["swearMeter"] = _swear_meter_from_finalized(full_swear_meter["swearMeter"])
    session["id"] = full_swear_meter.get("id") or session["id"]
    session["cwd"] = full_swear_meter.get("cwd") or session["cwd"]
    session["source"] = full_swear_meter.get("source") or session["source"]
    return _finalize_session(path, session)


def scan_session_swear_meter(path: Path, *, archive: str, root: Path | None = None) -> dict[str, Any]:
    stat = path.stat()
    cache_key = (str(path), archive, str(root or ""), int(stat.st_size), int(stat.st_mtime_ns))
    cached = _SWEAR_SCAN_CACHE.get(cache_key)
    if cached is not None:
        return deepcopy(cached)
    session = _base_session(path, archive=archive, root=root, file_stat=stat)
    try:
        with path.open("rb") as handle:
            for raw_line in handle:
                _apply_swear_candidate_line(session, raw_line)
    except OSError as exc:
        session["error"] = safe_preview(exc)
        return _finalize_session(path, session)
    session["swearOnly"] = True
    finalized = _finalize_session(path, session)
    _SWEAR_SCAN_CACHE[cache_key] = deepcopy(finalized)
    return finalized


def _apply_swear_candidate_line(session: dict[str, Any], raw_line: bytes) -> None:
    if not raw_line.strip():
        return
    if not any(marker in raw_line for marker in SWEAR_CANDIDATE_MARKERS):
        return
    _apply_session_line(session, raw_line.decode("utf-8", errors="replace"))


def _apply_session_line(session: dict[str, Any], raw_line: str) -> None:
    session["lineCount"] += 1
    try:
        obj = json.loads(raw_line)
    except json.JSONDecodeError:
        session["eventCounts"]["[invalid_json]"] += 1
        return

    timestamp = obj.get("timestamp")
    if timestamp:
        session["firstTimestamp"] = session["firstTimestamp"] or timestamp
        session["lastTimestamp"] = timestamp

    event_type = str(obj.get("type") or "[missing]")
    session["eventCounts"][event_type] += 1
    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return
    payload_type = str(payload.get("type") or "[missing]")
    session["payloadTypes"][payload_type] += 1

    if event_type == "session_meta":
        session["id"] = payload.get("id") or session["id"]
        session["cwd"] = payload.get("cwd") or session["cwd"]
        session["source"] = payload.get("source") or session["source"]
        session["originator"] = payload.get("originator") or session["originator"]
        session["modelProvider"] = payload.get("model_provider") or session["modelProvider"]
        session["cliVersion"] = payload.get("cli_version") or session["cliVersion"]
        session["agentRole"] = payload.get("agent_role") or session["agentRole"]
        session["agentNickname"] = payload.get("agent_nickname") or session["agentNickname"]

    if event_type == "turn_context":
        model = payload.get("model")
        if model:
            session["models"][str(model)] += 1
        session["cwd"] = payload.get("cwd") or session["cwd"]

    if payload_type == "token_count":
        info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
        total_usage = info.get("total_token_usage") if isinstance(info, dict) else None
        last_usage = info.get("last_token_usage") if isinstance(info, dict) else None
        session["latestTokenUsage"] = _empty_token_totals()
        add_token_totals(session["latestTokenUsage"], total_usage)
        session["lastTurnUsage"] = _empty_token_totals()
        add_token_totals(session["lastTurnUsage"], last_usage)
        session["tokenEvents"] += 1
        window = info.get("model_context_window") if isinstance(info, dict) else None
        if window:
            session["contextWindows"][str(window)] += 1

    if payload_type == "exec_command_end":
        session["commands"] += 1
        exit_code = payload.get("exit_code")
        if exit_code not in (0, "0", None):
            session["commandFailures"] += 1
            if len(session["recentFailures"]) < 10:
                session["recentFailures"].append(
                    {
                        "command": safe_preview(payload.get("command"), limit=120),
                        "exitCode": exit_code,
                        "cwd": safe_preview(payload.get("cwd"), limit=120),
                    }
                )

    if payload_type in {"web_search_call", "web_search_end"}:
        session["webSearches"] += 1
    if payload_type in {"image_generation_call", "image_generation_end", "view_image_tool_call"}:
        session["images"] += 1
    if payload_type == "user_message":
        session["userMessages"] += 1
        _apply_user_message_for_swear_meter(session, payload.get("message"), timestamp)
    if payload_type in {"agent_message", "message"} or payload.get("role") == "assistant":
        session["assistantMessages"] += 1

    if event_type == "response_item":
        name = payload.get("name") or payload.get("tool_name")
        if name and payload_type in {"function_call", "custom_tool_call", "mcp_tool_call"}:
            session["tools"][str(name)] += 1
        if payload.get("role") == "user":
            session["userMessages"] += 1
            _apply_user_message_for_swear_meter(session, _content_to_text(payload.get("content")), timestamp)
        if payload.get("role") == "assistant":
            session["assistantMessages"] += 1


def _apply_user_message_for_swear_meter(session: dict[str, Any], message: Any, timestamp: Any) -> None:
    if not isinstance(message, str):
        return
    clean = message.strip()
    if not clean:
        return
    message_id = sha256(f"{timestamp or ''}\0{clean}".encode("utf-8", errors="replace")).hexdigest()
    seen = session.setdefault("_swearMessageIds", set())
    if message_id in seen:
        return
    seen.add(message_id)
    merge_swear_meter(session["swearMeter"], analyze_user_message(clean, str(timestamp or "")))


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts)


def _finalize_session(path: Path, session: dict[str, Any]) -> dict[str, Any]:
    for counter_key in ("eventCounts", "payloadTypes", "tools", "models", "contextWindows"):
        session[counter_key] = dict(session[counter_key].most_common(25))
    session["swearMeter"] = finalize_swear_meter(session["swearMeter"])
    session.pop("_swearMessageIds", None)
    session["id"] = session["id"] or _id_from_rollout_name(path.name)
    return session


def _id_from_rollout_name(name: str) -> str:
    stem = name.removesuffix(".jsonl")
    parts = stem.split("-")
    if len(parts) >= 7:
        return "-".join(parts[-5:])
    return stem


def collect_sessions(codex_root: Path) -> dict[str, Any]:
    roots = [
        ("active", codex_root / "sessions"),
        ("archived", codex_root / "archived_sessions"),
    ]
    all_sessions: list[dict[str, Any]] = []
    totals = _empty_token_totals()
    by_archive: Counter[str] = Counter()
    by_day: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"sessions": 0, "tokens": 0})
    tools: Counter[str] = Counter()
    models: Counter[str] = Counter()
    payload_types: Counter[str] = Counter()
    event_types: Counter[str] = Counter()
    failed_commands = 0
    command_count = 0
    bytes_total = 0
    parsed_files = 0
    skipped_files = 0
    swear_meter = empty_swear_meter()
    swear_by_thread: dict[str, dict[str, Any]] = {}

    for archive, root in roots:
        if not root.exists():
            continue
        entries: list[tuple[float, int, Path]] = []
        for path in root.rglob("*.jsonl"):
            try:
                stat = path.stat()
            except OSError as exc:
                all_sessions.append(
                    {
                        "id": _id_from_rollout_name(path.name),
                        "archive": archive,
                        "path": safe_relpath(path, codex_root),
                        "error": safe_preview(exc),
                    }
                )
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
        entries.sort(key=lambda item: item[0], reverse=True)
        for index, (_, size, path) in enumerate(entries):
            try:
                if index >= MAX_PARSED_SESSION_FILES:
                    session = scan_session_swear_meter(path, archive=archive, root=codex_root)
                    session["skipped"] = True
                    skipped_files += 1
                elif size > MAX_FULL_SESSION_BYTES:
                    session = scan_session_file_fast(path, archive=archive, root=codex_root)
                    parsed_files += 1
                else:
                    session = scan_session_file(path, archive=archive, root=codex_root)
                    parsed_files += 1
            except OSError as exc:
                all_sessions.append(
                    {
                        "id": _id_from_rollout_name(path.name),
                        "archive": archive,
                        "path": safe_relpath(path, codex_root),
                        "error": safe_preview(exc),
                    }
                )
                continue
            all_sessions.append(session)
            by_archive[archive] += 1
            bytes_total += int(session.get("bytes") or 0)
            add_token_totals(totals, session.get("latestTokenUsage"))
            for name, count in (session.get("tools") or {}).items():
                tools[name] += int(count)
            for name, count in (session.get("models") or {}).items():
                models[name] += int(count)
            for name, count in (session.get("payloadTypes") or {}).items():
                payload_types[name] += int(count)
            for name, count in (session.get("eventCounts") or {}).items():
                event_types[name] += int(count)
            session_swear_meter = _swear_meter_from_finalized(session.get("swearMeter") or {})
            merge_swear_meter(swear_meter, session_swear_meter)
            session_id = session.get("id")
            if session_id:
                thread_meter = swear_by_thread.setdefault(str(session_id), empty_swear_meter())
                merge_swear_meter(thread_meter, session_swear_meter)
            failed_commands += int(session.get("commandFailures") or 0)
            command_count += int(session.get("commands") or 0)
            day = str(session.get("firstTimestamp") or session.get("modified") or "")[:10]
            if day:
                by_day[day]["sessions"] += 1
                by_day[day]["tokens"] += int((session.get("latestTokenUsage") or {}).get("total_tokens") or 0)

    all_sessions.sort(key=lambda item: str(item.get("lastTimestamp") or item.get("modified") or ""), reverse=True)
    return {
        "files": len(all_sessions),
        "bytes": bytes_total,
        "byArchive": dict(by_archive),
        "tokenTotals": totals,
        "commands": command_count,
        "commandFailures": failed_commands,
        "tools": dict(tools.most_common(30)),
        "models": dict(models.most_common(20)),
        "payloadTypes": dict(payload_types.most_common(30)),
        "eventTypes": dict(event_types.most_common(20)),
        "parsedFiles": parsed_files,
        "skippedFiles": skipped_files,
        "swearMeter": finalize_swear_meter(swear_meter),
        "swearByThread": {thread_id: finalize_swear_meter(meter) for thread_id, meter in swear_by_thread.items()},
        "timeline": [{"day": day, **values} for day, values in sorted(by_day.items())],
        "recent": _compact_sessions(all_sessions[:80]),
        "topByTokens": _compact_sessions(sorted(all_sessions, key=lambda item: int((item.get("latestTokenUsage") or {}).get("total_tokens") or 0), reverse=True)[:25]),
    }


def _swear_meter_from_finalized(summary: dict[str, Any]) -> dict[str, Any]:
    meter = empty_swear_meter()
    meter["directUserMessages"] = int(summary.get("directUserMessages") or 0)
    meter["swearIndexMessages"] = int(summary.get("swearIndexMessages") or 0)
    meter["swearIndexOccurrences"] = int(summary.get("swearIndexOccurrences") or 0)
    meter["swearIndexScore"] = int(summary.get("swearIndexScore") or 0)
    meter["groups"].update(summary.get("groups") or {})
    for row in summary.get("categories") or []:
        category = row.get("id")
        if not category:
            continue
        meter["categories"][str(category)] += int(row.get("occurrences") or 0)
        meter["categoryMessages"][str(category)] += int(row.get("messages") or 0)
        meter["categoryScores"][str(category)] += int(row.get("score") or 0)
    for row in summary.get("terms") or []:
        term = row.get("term")
        if not term:
            continue
        meter["terms"][str(term)] += int(row.get("messages") or 0)
        meter["termOccurrences"][str(term)] += int(row.get("occurrences") or 0)
    for row in summary.get("timeline") or []:
        day = row.get("day")
        if not day:
            continue
        meter["timeline"][(str(day), "messages")] += int(row.get("messages") or 0)
        meter["timeline"][(str(day), "swearMessages")] += int(row.get("swearMessages") or 0)
        for category, values in (row.get("categories") or {}).items():
            if not isinstance(values, dict):
                continue
            meter["timeline"][(str(day), f"categoryMessages:{category}")] += int(values.get("messages") or 0)
            meter["timeline"][(str(day), f"category:{category}")] += int(values.get("occurrences") or 0)
    return meter


def _compact_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted = []
    for item in sessions:
        compacted.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "archive": item.get("archive"),
                "path": item.get("path"),
                "cwd": item.get("cwd"),
                "source": item.get("source"),
                "agentRole": item.get("agentRole"),
                "agentNickname": item.get("agentNickname"),
                "firstTimestamp": item.get("firstTimestamp"),
                "lastTimestamp": item.get("lastTimestamp"),
                "modified": item.get("modified"),
                "bytes": item.get("bytes"),
                "lineCount": item.get("lineCount"),
                "partial": item.get("partial"),
                "skipped": item.get("skipped"),
                "tokens": item.get("latestTokenUsage"),
                "commands": item.get("commands"),
                "commandFailures": item.get("commandFailures"),
                "swearMeter": item.get("swearMeter"),
                "tools": item.get("tools"),
                "models": item.get("models"),
            }
        )
    return compacted


def collect_state(codex_root: Path) -> dict[str, Any]:
    db = codex_root / "state_5.sqlite"
    result: dict[str, Any] = {"database": file_info(db), "available": False}
    if not db.exists():
        return result
    try:
        con = open_sqlite_readonly(db)
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
        return result
    try:
        result["available"] = True
        tables = query_rows(con, "select name from sqlite_master where type='table' order by name")
        result["tables"] = {row["name"]: table_count(con, row["name"]) for row in tables}
        result["threads"] = {
            "total": table_count(con, "threads") or 0,
            "archived": con.execute("select count(*) from threads where archived=1").fetchone()[0],
            "withUserEvent": con.execute("select count(*) from threads where has_user_event=1").fetchone()[0],
            "tokens": int(con.execute("select coalesce(sum(tokens_used), 0) from threads").fetchone()[0] or 0),
            "maxTokens": int(con.execute("select coalesce(max(tokens_used), 0) from threads").fetchone()[0] or 0),
        }
        result["bySource"] = _rows_with_source_labels(
            query_rows(
                con,
                "select source, count(*) threads, coalesce(sum(tokens_used),0) tokens from threads group by source order by tokens desc",
            )
        )
        result["byCwd"] = [
            {
                "cwd": path_for_display(row["cwd"] or "[unknown]"),
                "threads": row["threads"],
                "tokens": row["tokens"],
            }
            for row in query_rows(
                con,
                "select cwd, count(*) threads, coalesce(sum(tokens_used),0) tokens from threads group by cwd order by tokens desc limit 25",
            )
        ]
        result["byDay"] = [
            {
                "day": timestamp_to_iso(row["created_at"])[:10] if timestamp_to_iso(row["created_at"]) else "[unknown]",
                "threads": row["threads"],
                "tokens": row["tokens"],
            }
            for row in query_rows(
                con,
                "select cast(created_at / 86400 as integer) bucket, min(created_at) created_at, count(*) threads, coalesce(sum(tokens_used),0) tokens from threads group by bucket order by bucket",
            )
        ]
        result["recentThreads"] = [
            _thread_row(row)
            for row in query_rows(
                con,
                "select id,title,source,model_provider,cwd,tokens_used,has_user_event,archived,created_at,updated_at,rollout_path from threads order by updated_at desc limit 50",
            )
        ]
        result["topThreads"] = [
            _thread_row(row)
            for row in query_rows(
                con,
                "select id,title,source,model_provider,cwd,tokens_used,has_user_event,archived,created_at,updated_at,rollout_path from threads order by tokens_used desc limit 30",
            )
        ]
        result["projects"] = _collect_project_usage(con)
        result["dynamicTools"] = query_rows(
            con,
            "select name, count(*) threads from thread_dynamic_tools group by name order by threads desc limit 30",
        )
        result["spawnEdges"] = query_rows(
            con,
            "select status, count(*) count from thread_spawn_edges group by status order by count desc",
        )
    finally:
        con.close()
    return result


def _rows_with_source_labels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labeled = []
    for row in rows:
        source = row.get("source") or "[unknown]"
        label = source
        if isinstance(source, str) and source.startswith("{"):
            try:
                data = json.loads(source)
                spawn = data.get("subagent", {}).get("thread_spawn", {})
                role = spawn.get("agent_role") or "subagent"
                label = f"subagent/{role}"
            except (json.JSONDecodeError, AttributeError):
                label = "subagent"
        labeled.append({"source": label, "threads": row.get("threads"), "tokens": row.get("tokens")})
    return labeled


def _thread_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title") or "[untitled]",
        "source": _source_label(row.get("source")),
        "modelProvider": row.get("model_provider"),
        "cwd": path_for_display(row.get("cwd") or ""),
        "tokens": int(row.get("tokens_used") or 0),
        "hasUserEvent": bool(row.get("has_user_event")),
        "archived": bool(row.get("archived")),
        "created": timestamp_to_iso(row.get("created_at")),
        "updated": timestamp_to_iso(row.get("updated_at")),
        "rolloutPath": row.get("rollout_path"),
    }


def _collect_project_usage(con: sqlite3.Connection) -> dict[str, Any]:
    rows = query_rows(
        con,
        "select id,title,source,model_provider,cwd,tokens_used,created_at,updated_at,archived "
        "from threads order by created_at asc",
    )
    days: set[str] = set()
    projects: dict[str, dict[str, Any]] = {}
    total_by_day: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"tokens": 0, "threads": 0})

    for row in rows:
        cwd = _normalized_cwd(row.get("cwd"))
        label = _project_label(cwd)
        day_iso = timestamp_to_iso(row.get("created_at"))
        day = day_iso[:10] if day_iso else "[unknown]"
        days.add(day)
        tokens = int(row.get("tokens_used") or 0)
        project = projects.setdefault(
            cwd,
            {
                "id": _project_id(cwd),
                "name": label,
                "cwd": cwd,
                "tokens": 0,
                "threads": 0,
                "days": defaultdict(lambda: {"tokens": 0, "threads": 0}),
                "recentThreads": [],
                "topThreads": [],
            },
        )
        project["tokens"] += tokens
        project["threads"] += 1
        project["days"][day]["tokens"] += tokens
        project["days"][day]["threads"] += 1
        total_by_day[day]["tokens"] += tokens
        total_by_day[day]["threads"] += 1
        compact_thread = _thread_row(row)
        project["recentThreads"].append(compact_thread)
        project["topThreads"].append(compact_thread)

    sorted_days = sorted(days)
    project_list = []
    for project in projects.values():
        day_map = project["days"]
        project["days"] = [
            {
                "day": day,
                "tokens": int(day_map[day]["tokens"]),
                "threads": int(day_map[day]["threads"]),
            }
            for day in sorted_days
        ]
        project["recentThreads"] = sorted(project["recentThreads"], key=lambda item: str(item.get("updated") or ""), reverse=True)[:20]
        project["topThreads"] = sorted(project["topThreads"], key=lambda item: int(item.get("tokens") or 0), reverse=True)[:20]
        project_list.append(project)

    project_list.sort(key=lambda item: int(item.get("tokens") or 0), reverse=True)
    return {
        "days": sorted_days,
        "total": [
            {
                "day": day,
                "tokens": int(total_by_day[day]["tokens"]),
                "threads": int(total_by_day[day]["threads"]),
            }
            for day in sorted_days
        ],
        "projects": project_list,
    }


def _normalized_cwd(cwd: Any) -> str:
    text = path_for_display(str(cwd or "[unknown]"))
    return text.rstrip("\\/")


def _project_label(cwd: str) -> str:
    if cwd in {"", "[unknown]"}:
        return "[unknown]"
    normalized = cwd.replace("/", "\\")
    parts = [part for part in normalized.split("\\") if part and part != "?"]
    if not parts:
        return cwd
    leaf = parts[-1]
    parent = parts[-2] if len(parts) > 1 else ""
    if leaf.lower() in {"desktop", "documents"} and len(parts) >= 3:
        return leaf
    if parent and leaf.lower() in {"lattice"}:
        return leaf
    return leaf


def _project_id(cwd: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in cwd)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:80] or "unknown"


def _source_label(source: Any) -> str:
    if not source:
        return "[unknown]"
    text = str(source)
    if text.startswith("{"):
        try:
            data = json.loads(text)
            spawn = data.get("subagent", {}).get("thread_spawn", {})
            role = spawn.get("agent_role") or "subagent"
            nickname = spawn.get("agent_nickname")
            return f"subagent/{role}" + (f" {nickname}" if nickname else "")
        except (json.JSONDecodeError, AttributeError):
            return "subagent"
    return text


def collect_logs(codex_root: Path) -> dict[str, Any]:
    db = codex_root / "logs_2.sqlite"
    result: dict[str, Any] = {"database": file_info(db), "available": False}
    if not db.exists():
        return result
    try:
        con = open_sqlite_readonly(db)
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
        return result
    try:
        result["available"] = True
        result["total"] = table_count(con, "logs") or 0
        recent_scope = "select * from logs order by id desc limit 20000"
        result["sampledRows"] = min(20000, int(result["total"] or 0))
        result["levels"] = query_rows(con, f"select level, count(*) count from ({recent_scope}) group by level order by count desc")
        result["targets"] = query_rows(
            con,
            f"select target, count(*) count, coalesce(sum(estimated_bytes),0) bytes from ({recent_scope}) group by target order by count desc limit 30",
        )
        result["recentWarnings"] = [
            {
                "time": timestamp_to_iso(row["ts"]),
                "level": row["level"],
                "target": row["target"],
                "message": safe_preview(row["body"], limit=220),
            }
            for row in query_rows(
                con,
                f"select ts, level, target, feedback_log_body body from ({recent_scope}) where level in ('WARN','WARNING','ERROR') order by id desc limit 40",
            )
        ]
        result["byHour"] = [
            {
                "time": timestamp_to_iso(row["bucket"] * 3600),
                "count": row["count"],
            }
            for row in query_rows(
                con,
                f"select cast(ts / 3600 as integer) bucket, count(*) count from ({recent_scope}) group by bucket order by bucket desc limit 48",
            )
        ]
    finally:
        con.close()
    return result


def collect_filesystem(codex_root: Path) -> dict[str, Any]:
    auth = codex_root / "auth.json"
    config = codex_root / "config.toml"
    global_state = codex_root / ".codex-global-state.json"
    models_cache = codex_root / "models_cache.json"
    session_index = codex_root / "session_index.jsonl"
    safe_files = [config, global_state, models_cache, session_index]
    auth_info = file_info(auth)
    auth_info["redacted"] = True

    index_count = 0
    if session_index.exists():
        try:
            with session_index.open("r", encoding="utf-8", errors="replace") as handle:
                index_count = sum(1 for line in handle if line.strip())
        except OSError:
            index_count = 0

    model_count = None
    if models_cache.exists():
        try:
            with models_cache.open("r", encoding="utf-8", errors="replace") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                model_count = len(data)
            elif isinstance(data, dict):
                model_count = len(data.get("models") or data)
        except (OSError, json.JSONDecodeError):
            model_count = None

    return {
        "root": file_info(codex_root),
        "safeFiles": [file_info(path) for path in safe_files],
        "auth": auth_info,
        "sessionIndexEntries": index_count,
        "modelCacheEntries": model_count,
        "generatedImages": count_files(codex_root / "generated_images", patterns=("*",)),
        "plugins": count_files(codex_root / "plugins", patterns=("*",), skip_parts={"node_modules", ".git"}),
        "skills": count_files(codex_root / "skills", patterns=("SKILL.md",)),
        "automations": count_files(codex_root / "automations", patterns=("*",)),
        "cache": count_files(codex_root / "cache", patterns=("*",), skip_parts={"node_modules", ".git"}),
        "sqlite": count_files(codex_root / "sqlite", patterns=("*",)),
    }


def collect_app_database(codex_root: Path) -> dict[str, Any]:
    db = codex_root / "sqlite" / "codex-dev.db"
    result: dict[str, Any] = {"database": file_info(db), "available": False}
    if not db.exists():
        return result
    try:
        con = open_sqlite_readonly(db)
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
        return result
    try:
        result["available"] = True
        tables = query_rows(con, "select name from sqlite_master where type='table' order by name")
        result["tables"] = {row["name"]: table_count(con, row["name"]) for row in tables}
        if table_count(con, "automations") is not None:
            result["automations"] = {
                "total": table_count(con, "automations") or 0,
                "byStatus": query_rows(con, "select coalesce(status,'[unknown]') status, count(*) count from automations group by status order by count desc"),
                "recent": [
                    {
                        "id": row.get("id"),
                        "name": row.get("name") or "[untitled]",
                        "status": row.get("status"),
                        "model": row.get("model"),
                        "reasoningEffort": row.get("reasoning_effort"),
                        "nextRun": timestamp_to_iso(row.get("next_run_at")),
                        "lastRun": timestamp_to_iso(row.get("last_run_at")),
                    }
                    for row in query_rows(
                        con,
                        "select id,name,status,next_run_at,last_run_at,model,reasoning_effort from automations order by updated_at desc limit 30",
                    )
                ],
            }
        if table_count(con, "automation_runs") is not None:
            result["automationRuns"] = {
                "total": table_count(con, "automation_runs") or 0,
                "byStatus": query_rows(
                    con,
                    "select coalesce(status,'[unknown]') status, count(*) count from automation_runs group by status order by count desc",
                ),
                "recent": [
                    {
                        "threadId": row.get("thread_id"),
                        "automationId": row.get("automation_id"),
                        "status": row.get("status"),
                        "threadTitle": row.get("thread_title"),
                        "sourceCwd": path_for_display(row.get("source_cwd") or ""),
                        "created": timestamp_to_iso(row.get("created_at")),
                        "updated": timestamp_to_iso(row.get("updated_at")),
                    }
                    for row in query_rows(
                        con,
                        "select thread_id,automation_id,status,thread_title,source_cwd,created_at,updated_at "
                        "from automation_runs order by updated_at desc limit 30",
                    )
                ],
            }
        if table_count(con, "inbox_items") is not None:
            result["inboxItems"] = {
                "total": table_count(con, "inbox_items") or 0,
                "unread": con.execute("select count(*) from inbox_items where read_at is null").fetchone()[0],
            }
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
    finally:
        con.close()
    return result


def collect_desktop_app_support(home: Path | None = None) -> dict[str, Any]:
    base = home or default_home()
    roots = _desktop_app_support_roots(base)
    root = next((path for path in roots if path.exists()), roots[0])
    result: dict[str, Any] = {
        "root": file_info(root),
        "available": root.exists(),
        "candidates": [path_for_display(path) for path in roots],
    }
    if not root.exists():
        return result
    result["preferences"] = file_info(root / "Preferences")
    result["browserSidebarLocalServers"] = file_info(root / "browser-sidebar-local-servers.json")
    result["sessionStorage"] = count_files(root / "Session Storage", patterns=("*",))
    result["cache"] = count_files(root / "Cache", patterns=("*",))
    result["gpuCache"] = count_files(root / "GPUCache", patterns=("*",))
    result["blobStorage"] = count_files(root / "blob_storage", patterns=("*",))
    result["crashpad"] = count_files(root / "Crashpad", patterns=("*",))
    return result


def _desktop_app_support_roots(home: Path) -> list[Path]:
    candidates = [
        home / "Library" / "Application Support" / "Codex",
        home / "AppData" / "Roaming" / "Codex",
        home / ".config" / "Codex",
        home / ".local" / "share" / "Codex",
    ]
    return candidates


def collect_codex(home: Path | None = None) -> dict[str, Any]:
    base = home or default_home()
    codex_root = base if (base / "state_5.sqlite").exists() or (base / "auth.json").exists() else base / ".codex"
    result: dict[str, Any] = {
        "root": path_for_display(codex_root),
        "available": codex_root.exists(),
    }
    if not codex_root.exists():
        return result
    result["filesystem"] = collect_filesystem(codex_root)
    result["state"] = collect_state(codex_root)
    result["logs"] = collect_logs(codex_root)
    result["sessions"] = collect_sessions(codex_root)
    result["appDatabase"] = collect_app_database(codex_root)
    result["desktopApp"] = collect_desktop_app_support(default_home())
    result = sanitize(result)
    return result
