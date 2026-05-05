from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Any

from .codex import collect_codex
from .discovery import discover_local_sources, preferred_codex_root, preferred_lattice_root
from .hermes import collect_hermes
from .lattice import collect_lattice
from .opencode import collect_opencode
from .utils import default_home, utc_now_iso


def collect_snapshot(*, include_hermes: bool = True, home: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    base = home or default_home()
    discovery = discover_local_sources(base)
    codex_root = preferred_codex_root(discovery, base)
    codex = collect_codex(codex_root)
    opencode = collect_opencode(base)
    lattice = collect_lattice(preferred_lattice_root(discovery, base))
    hermes = collect_hermes() if include_hermes else {"available": False, "skipped": True}
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
        "lattice": lattice,
        "hermes": hermes,
    }
    snapshot["overview"] = _overview(snapshot)
    snapshot["meta"]["scanSeconds"] = round(time.perf_counter() - started, 3)
    return snapshot


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
    opencode = snapshot.get("opencode") or {}
    opencode_db = opencode.get("database") or {}
    opencode_messages = opencode_db.get("messages") or {}
    opencode_tokens = opencode_messages.get("tokens") or {}
    opencode_projects = opencode_db.get("projects") or {}

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
    return {
        "codexThreads": int(state_threads.get("total") or 0),
        "codexStateTokens": int(state_threads.get("tokens") or 0),
        "codexJsonlTokens": int(session_tokens.get("total_tokens") or 0),
        "codexSessionFiles": int(sessions.get("files") or 0),
        "codexDirectUserMessages": int(swear_meter.get("directUserMessages") or 0),
        "codexSwearIndexMessages": int(swear_meter.get("swearIndexMessages") or 0),
        "codexSwearIndexRate": float(swear_meter.get("swearIndexRate") or 0),
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
        "latticeDocuments": int(lattice_core.get("documents") or 0),
        "latticePipelineRows": int((lattice_db.get("tables") or {}).get("document_pipeline_results") or 0),
        "latticeCodexAuthRows": codex_auth_complete,
        "latticeFieldReviewRows": codex_field_review,
        "latticeReviewSuggestions": int(lattice_core.get("reviewSuggestions") or 0),
        "hermesFiles": int((hermes.get("local") or {}).get("files") or hermes.get("files") or 0),
        "hermesAvailable": bool(hermes.get("available")),
    }
