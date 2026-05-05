from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from .sanitize import sanitize, safe_preview
from .utils import (
    count_files,
    default_home,
    file_info,
    open_sqlite_readonly,
    path_for_display,
    query_rows,
    table_count,
    timestamp_to_iso,
)


HERMES_WSL_COLLECTOR = r"""
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

SECRET_KEYS = ("TOKEN", "SECRET", "PASSWORD", "KEY", "AUTH", "COOKIE")

def safe_file(path):
    data = {"path": str(path), "exists": path.exists()}
    if path.exists():
        stat = path.stat()
        data.update({"bytes": stat.st_size, "modified": stat.st_mtime, "is_dir": path.is_dir()})
    return data

def safe_kv_file(path):
    if not path.exists():
        return {"exists": False, "keys": []}
    keys = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        keys.append({"key": key, "present": True, "redacted": any(part in key.upper() for part in SECRET_KEYS)})
    return {"exists": True, "keys": keys}

def safe_json_keys(path):
    if not path.exists():
        return {"exists": False, "keys": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {"exists": True, "error": str(exc), "keys": []}
    if isinstance(data, dict):
        return {"exists": True, "keys": sorted(map(str, data.keys()))[:80]}
    if isinstance(data, list):
        return {"exists": True, "type": "list", "items": len(data)}
    return {"exists": True, "type": type(data).__name__}

home = Path.home()
root = home / ".hermes"
agent = root / "hermes-agent"
files = []
by_suffix = Counter()
total_bytes = 0
skip = {".git", "node_modules", "__pycache__"}
if root.exists():
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip for part in path.parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        files.append((stat.st_mtime, str(path), stat.st_size, path.suffix.lower() or "[none]"))
        by_suffix[path.suffix.lower() or "[none]"] += 1
        total_bytes += stat.st_size
files.sort(reverse=True)

cron_root = root / "cron" / "output"
cron_files = []
if cron_root.exists():
    for path in cron_root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            cron_files.append({"path": str(path), "bytes": stat.st_size, "modified": stat.st_mtime})
cron_files.sort(key=lambda item: item["modified"], reverse=True)

git = {"available": False}
if (agent / ".git").exists():
    try:
        branch = subprocess.run(["git", "-C", str(agent), "branch", "--show-current"], text=True, capture_output=True, timeout=5)
        head = subprocess.run(["git", "-C", str(agent), "rev-parse", "--short", "HEAD"], text=True, capture_output=True, timeout=5)
        git = {"available": True, "branch": branch.stdout.strip(), "head": head.stdout.strip()}
    except Exception as exc:
        git = {"available": True, "error": str(exc)}

print(json.dumps({
    "home": str(home),
    "root": safe_file(root),
    "agent": safe_file(agent),
    "config": safe_file(root / "config.yaml"),
    "env": safe_kv_file(root / ".env"),
    "channelDirectory": safe_json_keys(root / "channel_directory.json"),
    "gatewayState": safe_json_keys(root / "gateway_state.json"),
    "codexAuth": {**safe_file(home / ".codex" / "auth.json"), "redacted": True},
    "files": len(files),
    "bytes": total_bytes,
    "bySuffix": dict(by_suffix.most_common(30)),
    "latest": [{"path": p, "bytes": b, "modified": m, "suffix": s} for m, p, b, s in files[:40]],
    "cronOutput": {"files": len(cron_files), "latest": cron_files[:25]},
    "git": git,
}, ensure_ascii=False))
"""


def collect_hermes(home: Path | None = None) -> dict[str, Any]:
    local = collect_local_hermes(home or default_home())
    wsl = collect_wsl_hermes()
    preferred = local if local.get("available") else wsl
    result = {
        **preferred,
        "available": bool(local.get("available") or wsl.get("available")),
        "local": local,
        "wsl": wsl,
    }
    return sanitize(result)


def collect_wsl_hermes() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["wsl", "python3", "-c", HERMES_WSL_COLLECTOR],
            text=True,
            capture_output=True,
            timeout=15,
        )
    except FileNotFoundError:
        return {"available": False, "error": "wsl command not found"}
    except subprocess.TimeoutExpired:
        return {"available": False, "error": "Hermes WSL scan timed out"}

    if completed.returncode != 0:
        return {
            "available": False,
            "error": safe_preview(completed.stderr or completed.stdout or f"wsl exited {completed.returncode}"),
        }
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"available": False, "error": f"Unable to parse Hermes WSL scan: {safe_preview(exc)}"}
    data["available"] = True
    data["kind"] = "wsl"
    return sanitize(data)


def collect_local_hermes(home: Path) -> dict[str, Any]:
    roots = _local_hermes_roots(home)
    if not roots:
        return {"available": False, "kind": "local", "roots": []}
    primary = roots[0]
    result: dict[str, Any] = {
        "available": primary.exists(),
        "kind": "local",
        "root": file_info(primary),
        "roots": [path_for_display(path) for path in roots],
        "auth": {**file_info(primary / "auth.json"), "redacted": True},
        "authLock": file_info(primary / "auth.lock"),
        "codexAuth": {**file_info(home / ".codex" / "auth.json"), "redacted": True},
        "config": _safe_structured_keys(primary / "config.yaml"),
        "channelDirectory": _safe_structured_keys(primary / "channel_directory.json"),
        "gatewayState": _safe_structured_keys(primary / "gateway_state.json"),
        "processes": _safe_structured_keys(primary / "processes.json"),
        "state": collect_hermes_state(primary / "state.db"),
        "kanban": collect_hermes_kanban(primary / "kanban.db"),
        "sessions": collect_hermes_session_files(primary / "sessions"),
        "files": 0,
        "bytes": 0,
        "bySuffix": {},
        "latest": [],
        "cronOutput": {"files": 0, "latest": []},
        "git": {"available": False},
        "agent": file_info(primary),
    }
    files = count_files(
        primary,
        patterns=("*",),
        skip_parts={".git", "node_modules", "__pycache__", ".pytest_cache", "oss-inspection"},
    )
    result["files"] = files.get("files", 0)
    result["bytes"] = files.get("bytes", 0)
    result["bySuffix"] = files.get("bySuffix", {})
    result["latest"] = files.get("latest", [])
    return sanitize(result)


def collect_hermes_state(db: Path) -> dict[str, Any]:
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
        if table_count(con, "sessions") is not None:
            result["sessions"] = {
                "total": table_count(con, "sessions") or 0,
                "inputTokens": _sum_column(con, "sessions", "input_tokens"),
                "outputTokens": _sum_column(con, "sessions", "output_tokens"),
                "cacheReadTokens": _sum_column(con, "sessions", "cache_read_tokens"),
                "cacheWriteTokens": _sum_column(con, "sessions", "cache_write_tokens"),
                "reasoningTokens": _sum_column(con, "sessions", "reasoning_tokens"),
                "estimatedCostUsd": _sum_column(con, "sessions", "estimated_cost_usd"),
                "actualCostUsd": _sum_column(con, "sessions", "actual_cost_usd"),
            }
            result["byModel"] = query_rows(
                con,
                "select coalesce(model,'[unknown]') model, count(*) sessions, "
                "coalesce(sum(input_tokens + output_tokens + reasoning_tokens),0) tokens "
                "from sessions group by model order by tokens desc limit 20",
            )
            result["bySource"] = query_rows(
                con,
                "select coalesce(source,'[unknown]') source, count(*) sessions, "
                "coalesce(sum(input_tokens + output_tokens + reasoning_tokens),0) tokens "
                "from sessions group by source order by sessions desc limit 20",
            )
            result["recentSessions"] = [
                _session_row(row)
                for row in query_rows(
                    con,
                    "select id,title,source,model,started_at,ended_at,end_reason,message_count,tool_call_count,"
                    "input_tokens,output_tokens,reasoning_tokens,estimated_cost_usd,cost_status "
                    "from sessions order by coalesce(ended_at, started_at) desc limit 40",
                )
            ]
            result["topSessions"] = [
                _session_row(row)
                for row in query_rows(
                    con,
                    "select id,title,source,model,started_at,ended_at,end_reason,message_count,tool_call_count,"
                    "input_tokens,output_tokens,reasoning_tokens,estimated_cost_usd,cost_status "
                    "from sessions order by (input_tokens + output_tokens + reasoning_tokens) desc limit 20",
                )
            ]
        if table_count(con, "messages") is not None:
            result["messages"] = {
                "total": table_count(con, "messages") or 0,
                "tokens": _sum_column(con, "messages", "token_count"),
                "byRole": query_rows(con, "select coalesce(role,'[unknown]') role, count(*) count from messages group by role order by count desc"),
                "tools": query_rows(
                    con,
                    "select coalesce(tool_name,'[unknown]') tool, count(*) count from messages "
                    "where tool_name is not null and tool_name != '' group by tool_name order by count desc limit 30",
                ),
            }
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
    finally:
        con.close()
    return result


def collect_hermes_kanban(db: Path) -> dict[str, Any]:
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
        if table_count(con, "tasks") is not None:
            result["tasksByStatus"] = query_rows(con, "select coalesce(status,'[unknown]') status, count(*) count from tasks group by status order by count desc")
        if table_count(con, "task_runs") is not None:
            result["runsByStatus"] = query_rows(con, "select coalesce(status,'[unknown]') status, count(*) count from task_runs group by status order by count desc")
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
    finally:
        con.close()
    return result


def collect_hermes_session_files(root: Path) -> dict[str, Any]:
    files = count_files(root, patterns=("*.json", "*.jsonl"))
    if not root.exists():
        return files
    by_suffix = Counter()
    latest = []
    for path in root.glob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        by_suffix[path.suffix.lower()] += 1
        latest.append((stat.st_mtime, path, stat.st_size))
    latest.sort(reverse=True)
    files["bySuffix"] = dict(by_suffix)
    files["latest"] = [
        {"path": path_for_display(path), "bytes": size, "modified": timestamp_to_iso(mtime)}
        for mtime, path, size in latest[:25]
    ]
    return files


def _local_hermes_roots(home: Path) -> list[Path]:
    candidates = _env_paths("AI_USAGE_MONITOR_HERMES_ROOTS")
    candidates.extend(
        [
            home / ".hermes",
            home / ".local" / "state" / "hermes",
            home / "Desktop" / "brain spa" / "brain-spa" / "runtime" / "hermes" / "chipmunk",
            home / "Desktop" / "brain-spa" / "runtime" / "hermes" / "chipmunk",
        ]
    )
    for root in _bounded_roots(home):
        candidates.extend(_find_hermes_state_roots(root, max_depth=7, limit=20))
    result = []
    seen: set[str] = set()
    for path in candidates:
        resolved = _safe_resolve(path)
        key = str(resolved).lower()
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        result.append(resolved)
    result.sort(key=_hermes_root_score, reverse=True)
    return result


def _find_hermes_state_roots(root: Path, *, max_depth: int, limit: int) -> list[Path]:
    found = []
    skip = {".git", "node_modules", "__pycache__", ".pytest_cache", "oss-inspection"}
    visited = 0
    for current, dirs, files in os.walk(root):
        visited += 1
        if visited > 4000:
            break
        current_path = Path(current)
        dirs[:] = [item for item in dirs if item not in skip]
        if _depth_from(root, current_path) > max_depth:
            dirs[:] = []
            continue
        names = set(files)
        if {"state.db", "auth.json", "gateway_state.json"} & names and ("sessions" in dirs or "state.db" in names):
            found.append(current_path)
            dirs[:] = []
            if len(found) >= limit:
                break
    return found


def _bounded_roots(home: Path) -> list[Path]:
    roots = [home / "Desktop", home / "Documents", home / "Developer", home / "dev", home / "code", home / "projects"]
    roots.extend(_env_paths("AI_USAGE_MONITOR_EXTRA_APP_ROOTS"))
    return [_safe_resolve(path) for path in roots if _safe_resolve(path).exists()]


def _safe_structured_keys(path: Path) -> dict[str, Any]:
    info = file_info(path)
    if not path.exists() or path.is_dir():
        return info
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {**info, "error": safe_preview(exc)}
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return {**info, "error": safe_preview(exc)}
        if isinstance(data, dict):
            return {**info, "keys": sorted(map(str, data.keys()))[:80]}
        if isinstance(data, list):
            return {**info, "type": "list", "items": len(data)}
        return {**info, "type": type(data).__name__}
    keys = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        if key:
            keys.append(key)
    return {**info, "keys": keys[:80]}


def _session_row(row: dict[str, Any]) -> dict[str, Any]:
    input_tokens = int(row.get("input_tokens") or 0)
    output_tokens = int(row.get("output_tokens") or 0)
    reasoning_tokens = int(row.get("reasoning_tokens") or 0)
    return {
        "id": row.get("id"),
        "title": row.get("title") or "[untitled]",
        "source": row.get("source") or "[unknown]",
        "model": row.get("model") or "[unknown]",
        "started": timestamp_to_iso(row.get("started_at")),
        "ended": timestamp_to_iso(row.get("ended_at")),
        "endReason": row.get("end_reason"),
        "messages": int(row.get("message_count") or 0),
        "toolCalls": int(row.get("tool_call_count") or 0),
        "tokens": input_tokens + output_tokens + reasoning_tokens,
        "estimatedCostUsd": row.get("estimated_cost_usd"),
        "costStatus": row.get("cost_status"),
    }


def _sum_column(con: sqlite3.Connection, table: str, column: str) -> int | float:
    try:
        return con.execute(f"select coalesce(sum([{column}]), 0) from [{table}]").fetchone()[0] or 0
    except sqlite3.Error:
        return 0


def _hermes_root_score(path: Path) -> tuple[int, float, str]:
    score = 0
    for name in ("state.db", "auth.json", "gateway_state.json", "config.yaml"):
        if (path / name).exists():
            score += 2
    if (path / "sessions").exists():
        score += 3
    if path.name == "chipmunk":
        score += 4
    try:
        modified = max((item.stat().st_mtime for item in path.iterdir()), default=0.0)
    except OSError:
        modified = 0.0
    return score, modified, str(path)


def _env_paths(name: str) -> list[Path]:
    raw = os.environ.get(name, "")
    if not raw:
        return []
    return [Path(part).expanduser() for part in raw.split(os.pathsep) if part.strip()]


def _depth_from(root: Path, path: Path) -> int:
    try:
        return len(path.relative_to(root).parts)
    except ValueError:
        return 0


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()
