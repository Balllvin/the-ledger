from __future__ import annotations

import socket
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any

from .codex import collect_codex
from .cursor import collect_cursor
from .discovery import discover_local_sources, enrich_discovery_with_workspaces, preferred_codex_root, preferred_lattice_root
from .hermes import collect_hermes
from .lattice import collect_lattice
from .opencode import collect_opencode
from .pricing import build_billing_estimate
from .swear_meter import swear_meter_methods
from .utils import default_home, utc_now_iso


ProgressCallback = Callable[[str], None]


def collect_snapshot(
    *,
    include_hermes: bool = True,
    home: Path | None = None,
    progress: ProgressCallback | None = None,
    session_cache_dir: Path | None = None,
    refresh_after_day: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    base = home or default_home()
    _progress(progress, "Discovering local sources")
    discovery = discover_local_sources(base)
    codex_root = preferred_codex_root(discovery, base)
    _progress(progress, "Reading Codex records")
    codex = collect_codex(codex_root, session_cache_dir=session_cache_dir, refresh_after_day=refresh_after_day)
    discovery = enrich_discovery_with_workspaces(discovery, _codex_workspaces(codex), base)
    _progress(progress, "Reading OpenCode records")
    opencode = collect_opencode(base)
    _progress(progress, "Reading Cursor records")
    cursor = collect_cursor(base)
    _progress(progress, "Reading app records")
    lattice = collect_lattice(preferred_lattice_root(discovery, base))
    _progress(progress, "Reading Codex agent records")
    hermes_roots = [
        Path(str(item.get("path"))).expanduser()
        for item in discovery.get("hermesRoots") or []
        if isinstance(item, dict) and item.get("exists") and item.get("path")
    ]
    hermes = collect_hermes(base, roots=hermes_roots) if include_hermes else {"available": False, "skipped": True}
    _progress(progress, "Building dashboard snapshot")
    snapshot = {
        "meta": {
            "generatedAt": utc_now_iso(),
            "host": socket.gethostname(),
            "home": str(base),
            "scanSeconds": None,
        },
        "overview": {},
        "discovery": discovery,
        "codex": codex,
        "opencode": opencode,
        "cursor": cursor,
        "lattice": lattice,
        "hermes": hermes,
        "about": {
            "sourceRepo": "https://github.com/petergpt/codex-swear-meter",
            "swearMeterMethods": swear_meter_methods(),
        },
    }
    snapshot["overview"] = _overview(snapshot)
    snapshot["billing"] = build_billing_estimate(snapshot)
    snapshot["meta"]["scanSeconds"] = round(time.perf_counter() - started, 3)
    return snapshot


def _progress(progress: ProgressCallback | None, message: str) -> None:
    if progress:
        progress(message)


def _codex_workspaces(codex: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    projects = (((codex.get("state") or {}).get("projects") or {}).get("projects")) or []
    for project in projects:
        if isinstance(project, dict) and project.get("cwd"):
            paths.append(str(project["cwd"]))
    for key in ("recent", "topByTokens"):
        for session in ((codex.get("sessions") or {}).get(key) or []):
            if isinstance(session, dict) and session.get("cwd"):
                paths.append(str(session["cwd"]))
    for thread in ((codex.get("state") or {}).get("recentThreads") or []):
        if isinstance(thread, dict) and thread.get("cwd"):
            paths.append(str(thread["cwd"]))
    return paths


def _overview(snapshot: dict[str, Any]) -> dict[str, Any]:
    codex = snapshot.get("codex") or {}
    state = codex.get("state") or {}
    sessions = codex.get("sessions") or {}
    logs = codex.get("logs") or {}
    app_database = codex.get("appDatabase") or {}
    lattice = snapshot.get("lattice") or {}
    lattice_db = lattice.get("databaseStats") or {}
    lattice_core = lattice_db.get("core") or {}
    hermes = snapshot.get("hermes") or {}
    hermes_state = (hermes.get("local") or {}).get("state") or hermes.get("state") or {}
    hermes_sessions = hermes_state.get("sessions") or {}
    hermes_swear = hermes_state.get("swearMeter") or {}
    opencode = snapshot.get("opencode") or {}
    opencode_db = opencode.get("database") or {}
    opencode_messages = opencode_db.get("messages") or {}
    opencode_tokens = opencode_messages.get("tokens") or {}
    opencode_projects = opencode_db.get("projects") or {}
    cursor = snapshot.get("cursor") or {}
    cursor_summary = cursor.get("summary") or {}

    codex_auth_complete = 0
    codex_field_review = 0
    for item in lattice_db.get("pipelineTotals") or []:
        if item.get("pipeline") == "codex_auth":
            codex_auth_complete = int(item.get("count") or 0)
        if item.get("pipeline") == "codex_field_review":
            codex_field_review = int(item.get("count") or 0)

    state_threads = (state.get("threads") or {})
    session_tokens = sessions.get("tokenTotals") or {}
    swear_meter = sessions.get("swearMeter") or {}
    human_swear_meter = (sessions.get("swearByOrigin") or {}).get("human") or {}
    return {
        "codexThreads": int(state_threads.get("total") or 0),
        "codexStateTokens": int(state_threads.get("tokens") or 0),
        "codexJsonlTokens": int(session_tokens.get("total_tokens") or 0),
        "codexSessionFiles": int(sessions.get("files") or 0),
        "codexDirectUserMessages": int(swear_meter.get("directUserMessages") or 0),
        "codexSwearIndexMessages": int(swear_meter.get("swearIndexMessages") or 0),
        "codexSwearIndexRate": float(swear_meter.get("swearIndexRate") or 0),
        "codexHumanDirectUserMessages": int(human_swear_meter.get("directUserMessages") or 0),
        "codexHumanSwearIndexMessages": int(human_swear_meter.get("swearIndexMessages") or 0),
        "codexHumanSwearIndexRate": float(human_swear_meter.get("swearIndexRate") or 0),
        "codexModelInputUserItems": int(sessions.get("modelInputUserItems") or 0),
        "codexLogRows": int(logs.get("total") or 0),
        "codexCommandFailures": int(sessions.get("commandFailures") or 0),
        "codexAutomations": int(((app_database.get("automations") or {}).get("total")) or 0),
        "codexAutomationRuns": int(((app_database.get("automationRuns") or {}).get("total")) or 0),
        "opencodeSessions": int((opencode_db.get("tables") or {}).get("session") or 0),
        "opencodeMessages": int(opencode_messages.get("total") or 0),
        "opencodeTokens": int(opencode_tokens.get("total") or 0),
        "opencodeCostUsd": float(opencode_messages.get("costUsd") or 0),
        "opencodeProjects": int(len(opencode_projects.get("projects") or [])),
        "opencodeLogs": int(((opencode.get("logs") or {}).get("cli") or {}).get("files") or 0)
        + int(((opencode.get("logs") or {}).get("app") or {}).get("files") or 0),
        "opencodeAvailable": bool(opencode.get("available")),
        "cursorLogs": int(cursor_summary.get("logs") or 0),
        "cursorLogBytes": int(cursor_summary.get("logBytes") or 0),
        "cursorWorkspaces": int(cursor_summary.get("workspaces") or 0),
        "cursorGenerations": int(cursor_summary.get("generations") or 0),
        "cursorPrompts": int(cursor_summary.get("prompts") or 0),
        "cursorComposers": int(cursor_summary.get("composers") or 0),
        "cursorSuggestedLines": int(cursor_summary.get("suggestedLines") or 0),
        "cursorAcceptedLines": int(cursor_summary.get("acceptedLines") or 0),
        "cursorAvailable": bool(cursor.get("available")),
        "latticeDocuments": int(lattice_core.get("documents") or 0),
        "latticePipelineRows": int((lattice_db.get("tables") or {}).get("document_pipeline_results") or 0),
        "latticeCodexAuthRows": codex_auth_complete,
        "latticeFieldReviewRows": codex_field_review,
        "latticeReviewSuggestions": int(lattice_core.get("reviewSuggestions") or 0),
        "hermesFiles": int((hermes.get("local") or {}).get("files") or hermes.get("files") or 0),
        "hermesSessions": int(hermes_sessions.get("total") or 0),
        "hermesTokens": int(
            (hermes_sessions.get("inputTokens") or 0)
            + (hermes_sessions.get("outputTokens") or 0)
            + (hermes_sessions.get("reasoningTokens") or 0)
        ),
        "hermesSwearIndexMessages": int(hermes_swear.get("swearIndexMessages") or 0),
        "hermesSwearIndexRate": float(hermes_swear.get("swearIndexRate") or 0),
        "hermesAvailable": bool(hermes.get("available")),
    }
