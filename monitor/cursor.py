from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .sanitize import safe_preview, sanitize
from .utils import default_home, file_info, open_sqlite_readonly, path_for_display, query_rows, table_count, timestamp_to_iso


AI_CODE_STATS_PREFIX = "aiCodeTracking.dailyStats.v1.5."
MAX_WORKSPACE_DATABASES = 80
MAX_PROCESS_MONITOR_LINES = 20_000


def cursor_roots(home: Path | None = None) -> dict[str, Path]:
    base = home or default_home()
    app = _first_existing(
        [
            base / "Library" / "Application Support" / "Cursor",
            base / "AppData" / "Roaming" / "Cursor",
            base / ".config" / "Cursor",
        ]
    )
    return {
        "app": app,
        "config": base / ".cursor",
        "logs": app / "logs",
        "processMonitor": app / "process-monitor",
        "globalStorage": app / "User" / "globalStorage",
        "workspaceStorage": app / "User" / "workspaceStorage",
    }


def collect_cursor(home: Path | None = None) -> dict[str, Any]:
    base = home or default_home()
    roots = cursor_roots(base)
    global_database = roots["globalStorage"] / "state.vscdb"
    workspace_storage = roots["workspaceStorage"]
    logs = _recent_files(roots["logs"], patterns=("*.log",), limit=50)
    process_monitor = collect_process_monitor(roots["processMonitor"])
    workspaces = collect_workspace_storage(workspace_storage)
    global_state = collect_global_state(global_database)
    available = any(path.exists() for path in roots.values())
    return sanitize(
        {
            "available": available,
            "roots": {name: file_info(path) for name, path in roots.items()},
            "globalState": global_state,
            "workspaces": workspaces,
            "logs": logs,
            "processMonitor": process_monitor,
            "summary": _cursor_summary(global_state, workspaces, logs, process_monitor),
        }
    )


def collect_global_state(db: Path) -> dict[str, Any]:
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
        result["tables"] = {row["name"]: table_count(con, row["name"]) for row in query_rows(con, "select name from sqlite_master where type='table' order by name")}
        result["keyCounts"] = _state_key_counts(con)
        result["dailyStats"] = _ai_code_daily_stats(con)
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
    finally:
        con.close()
    return result


def collect_workspace_storage(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"root": file_info(root), "available": root.exists(), "workspaces": [], "total": 0}
    if not root.exists():
        return result
    workspaces = []
    for index, state_db in enumerate(sorted(root.glob("*/state.vscdb"))):
        if index >= MAX_WORKSPACE_DATABASES:
            break
        workspaces.append(_workspace_summary(state_db))
    result["workspaces"] = sorted(workspaces, key=lambda item: str(item.get("modified") or ""), reverse=True)
    result["total"] = len(workspaces)
    result["limited"] = len(list(root.glob("*/state.vscdb"))) > MAX_WORKSPACE_DATABASES
    return result


def collect_process_monitor(root: Path) -> dict[str, Any]:
    result = _recent_files(root, patterns=("*.log",), limit=25)
    if not root.exists():
        return result
    sessions: set[str] = set()
    samples = 0
    subsamples = 0
    processes: Counter[str] = Counter()
    peak_memory = 0.0
    peak_cpu = 0.0
    errors = 0
    for path in sorted(root.glob("*.log"), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        try:
            handle = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            errors += 1
            continue
        with handle:
            for raw in handle:
                if samples >= MAX_PROCESS_MONITOR_LINES:
                    break
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    errors += 1
                    continue
                samples += 1
                if data.get("sessionId"):
                    sessions.add(str(data["sessionId"]))
                subsamples += int(data.get("numSubsamples") or 0)
                for row in data.get("rows") or []:
                    name = _process_label(row.get("processName"))
                    processes[name] += 1
                    peak_memory = max(peak_memory, float(row.get("samplePeakMemMb") or 0), float(row.get("sessionPeakMemMb") or 0))
                    peak_cpu = max(peak_cpu, float(row.get("cpuDuringSamplePeakPct") or 0))
        if samples >= MAX_PROCESS_MONITOR_LINES:
            break
    result.update(
        {
            "samples": samples,
            "subsamples": subsamples,
            "sessions": len(sessions),
            "topProcesses": [{"name": name, "samples": count} for name, count in processes.most_common(12)],
            "peakMemoryMb": round(peak_memory, 2),
            "peakCpuPct": round(peak_cpu, 2),
            "parseErrors": errors,
            "limited": samples >= MAX_PROCESS_MONITOR_LINES,
        }
    )
    return result


def _workspace_summary(state_db: Path) -> dict[str, Any]:
    workspace_root = state_db.parent
    workspace_uri = _workspace_uri(workspace_root / "workspace.json")
    summary = {
        "id": workspace_root.name,
        "workspace": workspace_uri,
        "name": _workspace_label(workspace_uri or workspace_root.name),
        "database": file_info(state_db),
        "modified": file_info(state_db).get("modified"),
        "generations": 0,
        "prompts": 0,
        "composers": 0,
        "linesSuggested": 0,
        "linesAccepted": 0,
        "hasBackgroundComposer": False,
    }
    try:
        con = open_sqlite_readonly(state_db)
    except sqlite3.Error as exc:
        summary["error"] = safe_preview(exc)
        return summary
    try:
        values = _workspace_values(con)
        generations = _json_list(values.get("aiService.generations"))
        prompts = _json_list(values.get("aiService.prompts"))
        composer_data = _json_dict(values.get("composer.composerData"))
        composers = composer_data.get("allComposers") if isinstance(composer_data.get("allComposers"), list) else []
        summary["generations"] = len(generations)
        summary["prompts"] = len(prompts)
        summary["composers"] = len(composers)
        summary["linesSuggested"] = sum(int(item.get("totalLinesAdded") or 0) for item in composers if isinstance(item, dict))
        summary["linesAccepted"] = sum(int(item.get("totalLinesRemoved") or 0) for item in composers if isinstance(item, dict))
        summary["hasBackgroundComposer"] = bool(values.get("workbench.backgroundComposer.workspacePersistentData"))
    except sqlite3.Error as exc:
        summary["error"] = safe_preview(exc)
    finally:
        con.close()
    return summary


def _state_key_counts(con: sqlite3.Connection) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for row in con.execute("select key from ItemTable"):
        key = str(row["key"] if isinstance(row, sqlite3.Row) else row[0])
        counts[_key_group(key)] += 1
    return dict(counts.most_common())


def _ai_code_daily_stats(con: sqlite3.Connection) -> dict[str, Any]:
    rows = []
    totals = {"tabSuggestedLines": 0, "tabAcceptedLines": 0, "composerSuggestedLines": 0, "composerAcceptedLines": 0}
    for row in con.execute("select key, value from ItemTable where key like ? order by key", (f"{AI_CODE_STATS_PREFIX}%",)):
        data = _json_dict(row["value"])
        day = str(data.get("date") or str(row["key"]).removeprefix(AI_CODE_STATS_PREFIX))
        if not day:
            continue
        item = {"day": day}
        for key in totals:
            value = int(data.get(key) or 0)
            item[key] = value
            totals[key] += value
        rows.append(item)
    return {"days": rows, "totals": totals}


def _workspace_values(con: sqlite3.Connection) -> dict[str, str]:
    keys = (
        "aiService.generations",
        "aiService.prompts",
        "composer.composerData",
        "workbench.backgroundComposer.workspacePersistentData",
    )
    values = {}
    for key in keys:
        row = con.execute("select value from ItemTable where key = ?", (key,)).fetchone()
        if row:
            values[key] = row["value"]
    return values


def _cursor_summary(global_state: dict[str, Any], workspaces: dict[str, Any], logs: dict[str, Any], process_monitor: dict[str, Any]) -> dict[str, Any]:
    workspace_rows = workspaces.get("workspaces") or []
    daily_totals = ((global_state.get("dailyStats") or {}).get("totals") or {})
    return {
        "logs": int(logs.get("files") or 0) + int(process_monitor.get("files") or 0),
        "logBytes": int(logs.get("bytes") or 0) + int(process_monitor.get("bytes") or 0),
        "workspaces": len(workspace_rows),
        "generations": sum(int(row.get("generations") or 0) for row in workspace_rows),
        "prompts": sum(int(row.get("prompts") or 0) for row in workspace_rows),
        "composers": sum(int(row.get("composers") or 0) for row in workspace_rows),
        "processSamples": int(process_monitor.get("samples") or 0),
        "suggestedLines": int(daily_totals.get("tabSuggestedLines") or 0) + int(daily_totals.get("composerSuggestedLines") or 0),
        "acceptedLines": int(daily_totals.get("tabAcceptedLines") or 0) + int(daily_totals.get("composerAcceptedLines") or 0),
    }


def _workspace_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    folder = data.get("folder") if isinstance(data, dict) else None
    if not isinstance(folder, str):
        return None
    parsed = urlparse(folder)
    if parsed.scheme == "file":
        return unquote(parsed.path)
    return folder


def _workspace_label(value: str) -> str:
    text = value.rstrip("/")
    if not text:
        return "[unknown]"
    if "://" in text:
        return text.split("/")[-1] or text
    return Path(text).name or text


def _process_label(value: Any) -> str:
    text = str(value or "[unknown]")
    lowered = text.lower()
    if "agent-exec" in lowered:
        return "agent-exec"
    if "retrieval" in lowered or "always-local" in lowered:
        return "retrieval"
    if "renderer" in lowered:
        return "renderer"
    if "filewatcher" in lowered or "filewatcher" in text.replace(" ", "").lower():
        return "fileWatcher"
    if "terminal" in lowered or "pty-host" in lowered:
        return "terminal"
    if "mcp" in lowered:
        return "mcp"
    if "shared-process" in lowered:
        return "shared-process"
    if "gpu" in lowered:
        return "gpu"
    if "cursor helper" in lowered:
        return "cursor-helper"
    return Path(text.split()[0]).name[:80] if text else "[unknown]"


def _key_group(key: str) -> str:
    if key.startswith("secret://"):
        return "secret"
    if key.startswith(AI_CODE_STATS_PREFIX):
        return "aiCodeTracking.dailyStats"
    if "/" in key:
        return key.split("/", 1)[0]
    if "." in key:
        return key.split(".", 1)[0]
    return key


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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


def _first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]
