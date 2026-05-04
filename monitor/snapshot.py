from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import Any

from .codex import collect_codex
from .discovery import discover_local_sources, preferred_codex_root, preferred_lattice_root
from .hermes import collect_hermes
from .lattice import collect_lattice
from .utils import default_home, utc_now_iso


def collect_snapshot(*, include_hermes: bool = True, home: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    base = home or default_home()
    discovery = discover_local_sources(base)
    codex_root = preferred_codex_root(discovery, base)
    codex = collect_codex(codex_root)
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
    lattice = snapshot.get("lattice") or {}
    lattice_db = lattice.get("databaseStats") or {}
    lattice_core = lattice_db.get("core") or {}
    hermes = snapshot.get("hermes") or {}

    codex_auth_complete = 0
    codex_field_review = 0
    for item in lattice_db.get("pipelineTotals") or []:
        if item.get("pipeline") == "codex_auth":
            codex_auth_complete = int(item.get("count") or 0)
        if item.get("pipeline") == "codex_field_review":
            codex_field_review = int(item.get("count") or 0)

    state_threads = (state.get("threads") or {})
    session_tokens = sessions.get("tokenTotals") or {}
    return {
        "codexThreads": int(state_threads.get("total") or 0),
        "codexStateTokens": int(state_threads.get("tokens") or 0),
        "codexJsonlTokens": int(session_tokens.get("total_tokens") or 0),
        "codexSessionFiles": int(sessions.get("files") or 0),
        "codexLogRows": int(logs.get("total") or 0),
        "codexCommandFailures": int(sessions.get("commandFailures") or 0),
        "latticeDocuments": int(lattice_core.get("documents") or 0),
        "latticePipelineRows": int((lattice_db.get("tables") or {}).get("document_pipeline_results") or 0),
        "latticeCodexAuthRows": codex_auth_complete,
        "latticeFieldReviewRows": codex_field_review,
        "latticeReviewSuggestions": int(lattice_core.get("reviewSuggestions") or 0),
        "hermesFiles": int(hermes.get("files") or 0),
        "hermesAvailable": bool(hermes.get("available")),
    }
