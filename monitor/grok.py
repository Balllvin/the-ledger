from __future__ import annotations

import os
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .sanitize import safe_preview, sanitize
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


def grok_roots(home: Path | None = None) -> dict[str, Path]:
    """Return standard locations for Grok Build data roots.

    Highest priority: GROK_HOME env var (exact root).
    Fallback: ~/.grok under the user's home (cross-platform via default_home).
    """
    env_root = os.environ.get("GROK_HOME")
    if env_root:
        root = Path(env_root).expanduser()
    else:
        base = home or default_home()
        root = base / ".grok"
    return {
        "root": root,
        "db": root / "grok.db",
        "sessions": root / "sessions",
        "auth": root / "auth.json",
        "config": root / "config.toml",
        "userSettings": root / "user-settings.json",
        "logs": root / "logs",
        "bin": root / "bin",
    }


def collect_grok(home: Path | None = None) -> dict[str, Any]:
    """Collect read-only Grok Build usage and thread metadata.

    Primary source: ~/.grok/grok.db (workspaces, sessions, usage_events).
    Secondary: filesystem metadata under sessions/, auth presence (redacted), logs.
    Never returns raw chat content, prompt text, or secret values.
    """
    roots = grok_roots(home)
    db_path = roots["db"]
    sessions_root = roots["sessions"]

    available = any(p.exists() for p in roots.values())

    database = collect_grok_database(db_path)
    fs_sessions = count_files(
        sessions_root,
        patterns=("*.jsonl", "*.json", "*"),
        skip_parts={".git", "node_modules", "__pycache__"},
        max_files=2000,
    )

    logs = {
        "unified": file_info(roots["logs"] / "unified.jsonl"),
        "dir": file_info(roots["logs"]),
    }

    auth = {**file_info(roots["auth"]), "redacted": True}

    # Build high-level summary for snapshot/overview (flat keys for convenience + UI)
    db_summary = database.get("summary") or {}
    tables = database.get("tables") or {}
    usage = database.get("usage") or {}
    total_tok = int(db_summary.get("totalTokens") or usage.get("totalTokens") or 0)
    summary = {
        "threads": int(db_summary.get("sessions") or db_summary.get("threads") or tables.get("sessions", 0) or tables.get("session", 0) or 0),
        "tokens": total_tok,
        "totalTokens": total_tok,
        "inputTokens": int(db_summary.get("inputTokens") or usage.get("inputTokens") or 0),
        "outputTokens": int(db_summary.get("outputTokens") or usage.get("outputTokens") or 0),
        "reasoningTokens": int(db_summary.get("reasoningTokens") or usage.get("reasoningTokens") or 0),
        "sessions": int(db_summary.get("sessions") or tables.get("sessions", 0) or tables.get("session", 0) or 0),
        "models": db_summary.get("models") or usage.get("models") or [],
        "projects": int(db_summary.get("projects") or usage.get("projects") or 0),
        "costUsd": float(db_summary.get("costUsd") or usage.get("costUsd") or 0.0),
        "available": bool(database.get("available")),
    }

    result = {
        "available": bool(available),
        "roots": {name: file_info(path) for name, path in roots.items()},
        "database": database,
        "sessions": fs_sessions,
        "logs": logs,
        "auth": auth,
        "summary": summary,
        "recentSessions": database.get("recentSessions", []),
    }
    return sanitize(result)


def collect_grok_database(db: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "database": file_info(db),
        "available": False,
        "tables": {},
        "usage": {},
        "recentSessions": [],
        "summary": {},
    }
    if not db.exists():
        return result

    try:
        con = open_sqlite_readonly(db)
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
        return result

    try:
        result["available"] = True
        tables = query_rows(con, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        result["tables"] = {row["name"]: table_count(con, row["name"]) for row in tables}

        # Usage aggregates from usage_events (the source of truth for tokens/cost)
        usage = _grok_usage_aggregates(con)
        result["usage"] = usage

        # Recent + top sessions (join sessions + usage_events + workspaces)
        recent = _grok_recent_sessions(con, limit=50)
        result["recentSessions"] = recent
        result["topByTokens"] = _grok_top_sessions(con, limit=30)

        # High-level summary for overview/billing
        result["summary"] = {
            "sessions": result["tables"].get("sessions", 0) or result["tables"].get("session", 0),
            "workspaces": result["tables"].get("workspaces", 0),
            "usageEvents": result["tables"].get("usage_events", 0),
            "totalTokens": usage.get("totalTokens", 0),
            "inputTokens": usage.get("inputTokens", 0),
            "outputTokens": usage.get("outputTokens", 0),
            "reasoningTokens": usage.get("reasoningTokens", 0),
            "models": usage.get("models", []),
            "projects": usage.get("projects", 0),
            "costUsd": usage.get("costUsd", 0.0),
        }
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
    finally:
        con.close()
    return result


def _grok_usage_aggregates(con: sqlite3.Connection) -> dict[str, Any]:
    row = query_rows(
        con,
        """
        SELECT
            COALESCE(SUM(input_tokens), 0)  AS inputTokens,
            COALESCE(SUM(output_tokens), 0) AS outputTokens,
            COALESCE(SUM(total_tokens), 0)  AS totalTokens,
            COALESCE(SUM(CASE WHEN model LIKE '%reason%' THEN total_tokens ELSE 0 END), 0) AS reasoningTokens,
            COALESCE(SUM(cost_micros), 0)   AS costMicros
        FROM usage_events
        """,
    )
    agg = row[0] if row else {}

    by_model = query_rows(
        con,
        """
        SELECT model,
               COUNT(*) as events,
               COALESCE(SUM(input_tokens),0)  AS inputTokens,
               COALESCE(SUM(output_tokens),0) AS outputTokens,
               COALESCE(SUM(total_tokens),0)  AS totalTokens,
               COALESCE(SUM(cost_micros),0)   AS costMicros
        FROM usage_events
        GROUP BY model
        ORDER BY totalTokens DESC
        LIMIT 30
        """,
    )

    by_source = query_rows(
        con,
        """
        SELECT source,
               COUNT(*) as events,
               COALESCE(SUM(total_tokens),0) AS totalTokens
        FROM usage_events
        GROUP BY source
        ORDER BY totalTokens DESC
        LIMIT 20
        """,
    )

    models = [m["model"] for m in by_model if m.get("model")]
    projects = query_rows(
        con,
        """
        SELECT COUNT(DISTINCT w.canonical_path) as projects
        FROM sessions s
        JOIN workspaces w ON w.id = s.workspace_id
        """,
    )
    project_count = projects[0]["projects"] if projects else 0

    cost_usd = (agg.get("costMicros") or 0) / 1_000_000.0

    return {
        "inputTokens": int(agg.get("inputTokens") or 0),
        "outputTokens": int(agg.get("outputTokens") or 0),
        "totalTokens": int(agg.get("totalTokens") or 0),
        "reasoningTokens": int(agg.get("reasoningTokens") or 0),
        "costMicros": int(agg.get("costMicros") or 0),
        "costUsd": round(cost_usd, 6),
        "models": models,
        "byModel": by_model,
        "bySource": by_source,
        "projects": project_count,
    }


def _grok_recent_sessions(con: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = query_rows(
        con,
        f"""
        SELECT
            s.id,
            s.title,
            s.model,
            s.mode,
            s.cwd_last,
            s.status,
            s.created_at,
            s.updated_at,
            COALESCE(SUM(u.total_tokens), 0) AS totalTokens,
            COALESCE(SUM(u.input_tokens), 0)  AS inputTokens,
            COALESCE(SUM(u.output_tokens), 0) AS outputTokens
        FROM sessions s
        LEFT JOIN usage_events u ON u.session_id = s.id
        GROUP BY s.id
        ORDER BY s.updated_at DESC
        LIMIT {limit}
        """,
    )
    out = []
    for r in rows:
        out.append(
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "model": r.get("model"),
                "mode": r.get("mode"),
                "cwd": r.get("cwd_last"),
                "status": r.get("status"),
                "created": timestamp_to_iso(r.get("created_at")),
                "updated": timestamp_to_iso(r.get("updated_at")),
                "tokens": int(r.get("totalTokens") or 0),
                "inputTokens": int(r.get("inputTokens") or 0),
                "outputTokens": int(r.get("outputTokens") or 0),
            }
        )
    return out

def _grok_top_sessions(con: sqlite3.Connection, limit: int = 30) -> list[dict[str, Any]]:
    rows = query_rows(
        con,
        f"""
        SELECT
            s.id,
            s.title,
            s.model,
            s.cwd_last,
            COALESCE(SUM(u.total_tokens), 0) AS totalTokens
        FROM sessions s
        LEFT JOIN usage_events u ON u.session_id = s.id
        GROUP BY s.id
        ORDER BY totalTokens DESC
        LIMIT {limit}
        """,
    )
    out = []
    for r in rows:
        out.append(
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "model": r.get("model"),
                "cwd": r.get("cwd_last"),
                "tokens": int(r.get("totalTokens") or 0),
            }
        )
    return out
