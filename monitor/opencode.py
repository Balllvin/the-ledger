from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .sanitize import safe_preview, sanitize
from .utils import count_files, default_home, file_info, open_sqlite_readonly, path_for_display, query_rows, table_count, timestamp_to_iso


def collect_opencode(home: Path | None = None) -> dict[str, Any]:
    base = home or default_home()
    roots = opencode_roots(base)
    data_root = roots["data"]
    desktop_root = roots["desktop"]
    result: dict[str, Any] = {
        "available": any(path.exists() for path in roots.values()),
        "version": _opencode_version(),
        "roots": {name: file_info(path) for name, path in roots.items()},
        "auth": {**file_info(data_root / "auth.json"), "redacted": True},
        "database": collect_opencode_database(data_root / "opencode.db"),
        "cli": collect_opencode_cli(base, roots),
        "app": collect_opencode_app(desktop_root, base),
        "logs": {
            "cli": _recent_files(data_root / "log", patterns=("*.log",), limit=40),
            "app": _recent_files(base / "Library" / "Logs" / "ai.opencode.desktop", patterns=("*.log",), limit=40),
        },
        "storage": {
            "sessionDiffs": count_files(data_root / "storage" / "session_diff", patterns=("*.json",)),
            "toolOutput": count_files(data_root / "tool-output", patterns=("*",)),
            "cache": count_files(base / ".cache" / "opencode", patterns=("*",), skip_parts={"node_modules", ".git"}),
        },
    }
    return sanitize(result)


def opencode_roots(home: Path | None = None) -> dict[str, Path]:
    base = home or default_home()
    return {
        "install": base / ".opencode",
        "config": base / ".config" / "opencode",
        "data": base / ".local" / "share" / "opencode",
        "desktop": base / "Library" / "Application Support" / "ai.opencode.desktop",
    }


def collect_opencode_database(db: Path) -> dict[str, Any]:
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
        messages = _message_usage(con)
        projects = _project_usage(con, messages["bySession"])
        result["messages"] = messages["summary"]
        result["models"] = messages["models"]
        result["providers"] = messages["providers"]
        result["projects"] = projects
        result["recentSessions"] = _session_rows(con, messages["bySession"], order_by="time_updated desc", limit=60)
        result["topSessions"] = _session_rows(con, messages["bySession"], order_by="tokens desc", limit=30)
        result["todos"] = _todos(con)
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
    finally:
        con.close()
    return result


def collect_opencode_cli(home: Path, roots: dict[str, Path]) -> dict[str, Any]:
    install = roots["install"]
    config = roots["config"]
    return {
        "install": file_info(install),
        "config": file_info(config),
        "binary": file_info(install / "bin" / "opencode"),
        "package": _safe_json_summary(install / "package.json"),
        "configPackage": _safe_json_summary(config / "package.json"),
        "gitRoots": _find_git_opencode_roots(home),
    }


def collect_opencode_app(root: Path, home: Path) -> dict[str, Any]:
    workspace_files = sorted(root.glob("opencode.workspace.*.dat")) if root.exists() else []
    return {
        "root": file_info(root),
        "settings": _safe_json_summary(root / "opencode.settings.dat"),
        "global": _safe_json_summary(root / "opencode.global.dat"),
        "default": _safe_json_summary(root / "default.dat"),
        "model": _safe_json_summary(root / "opencode" / "model.json"),
        "promptHistory": _jsonl_summary(root / "opencode" / "prompt-history.jsonl"),
        "workspaceFiles": {
            "files": len(workspace_files),
            "latest": [file_info(path) for path in sorted(workspace_files, key=lambda item: item.stat().st_mtime, reverse=True)[:20]],
        },
        "crashReports": _recent_files(home / "Library" / "Application Support" / "CrashReporter", patterns=("*opencode*.plist",), limit=20),
    }


def _message_usage(con: sqlite3.Connection) -> dict[str, Any]:
    by_session: dict[str, dict[str, Any]] = defaultdict(lambda: {"tokens": 0, "cost": 0.0, "messages": 0, "assistantMessages": 0, "tools": 0})
    models: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    total_tokens = 0
    input_tokens = 0
    output_tokens = 0
    reasoning_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    cost = 0.0
    parsed = 0
    errors = 0
    for row in con.execute("select session_id, data from message"):
        try:
            data = json.loads(row["data"] or "{}")
        except json.JSONDecodeError:
            errors += 1
            continue
        parsed += 1
        session = by_session[row["session_id"]]
        session["messages"] += 1
        role = str(data.get("role") or "[unknown]")
        roles[role] += 1
        if role == "assistant":
            session["assistantMessages"] += 1
        if data.get("providerID"):
            providers[str(data["providerID"])] += 1
        if data.get("modelID"):
            models[str(data["modelID"])] += 1
        tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        current_total = int(tokens.get("total") or 0)
        session["tokens"] += current_total
        total_tokens += current_total
        input_tokens += int(tokens.get("input") or 0)
        output_tokens += int(tokens.get("output") or 0)
        reasoning_tokens += int(tokens.get("reasoning") or 0)
        cache_read_tokens += int(cache.get("read") or 0)
        cache_write_tokens += int(cache.get("write") or 0)
        current_cost = float(data.get("cost") or 0)
        session["cost"] += current_cost
        cost += current_cost
    for row in con.execute("select session_id, data from part"):
        try:
            data = json.loads(row["data"] or "{}")
        except json.JSONDecodeError:
            continue
        if str(data.get("type") or "") == "tool":
            by_session[row["session_id"]]["tools"] += 1
    return {
        "summary": {
            "parsed": parsed,
            "errors": errors,
            "total": table_count(con, "message") or 0,
            "parts": table_count(con, "part") or 0,
            "roles": dict(roles.most_common()),
            "tokens": {
                "total": total_tokens,
                "input": input_tokens,
                "output": output_tokens,
                "reasoning": reasoning_tokens,
                "cacheRead": cache_read_tokens,
                "cacheWrite": cache_write_tokens,
            },
            "costUsd": round(cost, 6),
        },
        "models": dict(models.most_common(20)),
        "providers": dict(providers.most_common(20)),
        "bySession": by_session,
    }


def _project_usage(con: sqlite3.Connection, by_session: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = query_rows(
        con,
        "select id,title,directory,version,time_created,time_updated,time_archived,parent_id,project_id from session order by time_created asc",
    )
    days: set[str] = set()
    projects: dict[str, dict[str, Any]] = {}
    total_by_day: defaultdict[str, dict[str, int]] = defaultdict(lambda: {"tokens": 0, "threads": 0})
    for row in rows:
        cwd = path_for_display(row.get("directory") or "[unknown]").rstrip("\\/")
        day_iso = timestamp_to_iso(row.get("time_created"))
        day = day_iso[:10] if day_iso else "[unknown]"
        days.add(day)
        usage = by_session.get(str(row.get("id")), {})
        tokens = int(usage.get("tokens") or 0)
        project = projects.setdefault(
            cwd,
            {
                "id": _project_id(f"opencode:{cwd}"),
                "system": "opencode",
                "name": _project_label(cwd),
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
        thread = _session_row(row, usage)
        project["recentThreads"].append(thread)
        project["topThreads"].append(thread)
    sorted_days = sorted(days)
    project_list = []
    for project in projects.values():
        day_map = project["days"]
        project["days"] = [{"day": day, "tokens": int(day_map[day]["tokens"]), "threads": int(day_map[day]["threads"])} for day in sorted_days]
        project["recentThreads"] = sorted(project["recentThreads"], key=lambda item: str(item.get("updated") or ""), reverse=True)[:20]
        project["topThreads"] = sorted(project["topThreads"], key=lambda item: int(item.get("tokens") or 0), reverse=True)[:20]
        project_list.append(project)
    project_list.sort(key=lambda item: int(item.get("tokens") or 0), reverse=True)
    return {
        "days": sorted_days,
        "total": [{"day": day, "tokens": int(total_by_day[day]["tokens"]), "threads": int(total_by_day[day]["threads"])} for day in sorted_days],
        "projects": project_list,
    }


def _session_rows(con: sqlite3.Connection, by_session: dict[str, dict[str, Any]], *, order_by: str, limit: int) -> list[dict[str, Any]]:
    rows = query_rows(
        con,
        "select id,title,directory,version,time_created,time_updated,time_archived,parent_id,project_id "
        "from session order by " + order_by.replace("tokens", "time_updated") + f" limit {limit if order_by != 'tokens desc' else 1000}",
    )
    session_rows = [_session_row(row, by_session.get(str(row.get("id")), {})) for row in rows]
    if order_by == "tokens desc":
        session_rows.sort(key=lambda item: int(item.get("tokens") or 0), reverse=True)
        return session_rows[:limit]
    return session_rows


def _session_row(row: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "title": row.get("title") or "[untitled]",
        "source": "opencode",
        "cwd": path_for_display(row.get("directory") or ""),
        "version": row.get("version"),
        "tokens": int(usage.get("tokens") or 0),
        "costUsd": round(float(usage.get("cost") or 0), 6),
        "messages": int(usage.get("messages") or 0),
        "assistantMessages": int(usage.get("assistantMessages") or 0),
        "tools": int(usage.get("tools") or 0),
        "created": timestamp_to_iso(row.get("time_created")),
        "updated": timestamp_to_iso(row.get("time_updated")),
        "archived": bool(row.get("time_archived")),
    }


def _todos(con: sqlite3.Connection) -> dict[str, Any]:
    if table_count(con, "todo") is None:
        return {"total": 0, "byStatus": []}
    return {
        "total": table_count(con, "todo") or 0,
        "byStatus": query_rows(con, "select coalesce(status,'[unknown]') status, count(*) count from todo group by status order by count desc"),
    }


def _safe_json_summary(path: Path) -> dict[str, Any]:
    info = file_info(path)
    if not path.exists() or path.is_dir():
        return info
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        return {**info, "error": safe_preview(exc)}
    if isinstance(data, dict):
        return {**info, "keys": sorted(map(str, data.keys()))[:80]}
    if isinstance(data, list):
        return {**info, "type": "list", "items": len(data)}
    return {**info, "type": type(data).__name__}


def _jsonl_summary(path: Path) -> dict[str, Any]:
    info = file_info(path)
    if not path.exists():
        return {**info, "lines": 0}
    lines = 0
    modes: Counter[str] = Counter()
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                lines += 1
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("mode"):
                    modes[str(data["mode"])] += 1
    except OSError as exc:
        return {**info, "error": safe_preview(exc)}
    return {**info, "lines": lines, "modes": dict(modes.most_common())}


def _recent_files(root: Path, *, patterns: tuple[str, ...], limit: int) -> dict[str, Any]:
    if not root.exists():
        return {"path": path_for_display(root), "exists": False, "files": 0, "bytes": 0, "latest": []}
    files: list[tuple[float, Path, int]] = []
    for pattern in patterns:
        for path in root.rglob(pattern):
            if not path.is_file() or any(part in {"node_modules", ".git", "__pycache__"} for part in path.parts):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((stat.st_mtime, path, stat.st_size))
    files.sort(reverse=True)
    return {
        "path": path_for_display(root),
        "exists": True,
        "files": len(files),
        "bytes": sum(size for _, _, size in files),
        "latest": [{"path": path_for_display(path), "bytes": size, "modified": timestamp_to_iso(mtime)} for mtime, path, size in files[:limit]],
    }


def _find_git_opencode_roots(home: Path) -> list[dict[str, Any]]:
    roots = [home / "Desktop", home / "Documents", home / "Downloads", home / "code", home / "projects"]
    found = []
    for root in roots:
        if not root.exists():
            continue
        for current, dirs, _ in os.walk(root):
            current_path = Path(current)
            dirs[:] = [item for item in dirs if item not in {"node_modules", "__pycache__", ".venv"}]
            if _depth_from(root, current_path) > 5:
                dirs[:] = []
                continue
            candidate = current_path / ".git" / "opencode"
            if candidate.exists():
                found.append(file_info(candidate))
            if len(found) >= 40:
                return found
    return found


def _opencode_version() -> str | None:
    try:
        completed = subprocess.run(["opencode", "--version"], text=True, capture_output=True, timeout=3)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _project_label(cwd: str) -> str:
    parts = [part for part in cwd.replace("\\", "/").split("/") if part]
    return parts[-1] if parts else cwd or "[unknown]"


def _project_id(cwd: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in cwd)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")[:100] or "unknown"


def _depth_from(root: Path, path: Path) -> int:
    try:
        return len(path.relative_to(root).parts)
    except ValueError:
        return 0
