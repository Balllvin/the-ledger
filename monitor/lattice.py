from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .sanitize import safe_preview, sanitize
from .utils import count_files, desktop_root, file_info, open_sqlite_readonly, path_for_display, query_rows, table_count, timestamp_to_iso


def collect_lattice(root: Path | None = None) -> dict[str, Any]:
    lattice_root = root or desktop_root() / "Lattice"
    result: dict[str, Any] = {
        "root": path_for_display(lattice_root),
        "available": lattice_root.exists(),
        "filesystem": {
            "root": file_info(lattice_root),
            "readme": file_info(lattice_root / "README.md"),
            "hermes": file_info(lattice_root / "HERMES.md"),
            "aiReviewNotes": file_info(lattice_root / "AI_REVIEW_RUN_NOTES.md"),
            "serverLogs": _recent_files(lattice_root, patterns=("*.log",), limit=25),
            "dataLogs": _recent_files(lattice_root / "data", patterns=("*.log", "*.json", "*.md"), limit=60),
        },
    }
    db = lattice_root / "data" / "lattice.db"
    result["database"] = file_info(db)
    if db.exists():
        result["databaseStats"] = _collect_lattice_db(db)
    return sanitize(result)


def _collect_lattice_db(db: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"available": False}
    try:
        con = open_sqlite_readonly(db)
    except sqlite3.Error as exc:
        result["error"] = safe_preview(exc)
        return result
    try:
        result["available"] = True
        table_names = [row["name"] for row in query_rows(con, "select name from sqlite_master where type='table' order by name")]
        result["tables"] = {name: table_count(con, name) for name in table_names}
        result["core"] = {
            "documents": table_count(con, "documents") or 0,
            "pages": table_count(con, "pages") or 0,
            "pageRegions": table_count(con, "page_regions") or 0,
            "documentRows": table_count(con, "document_rows") or 0,
            "templateRows": table_count(con, "template_rows") or 0,
            "reviewSuggestions": table_count(con, "document_ai_review_suggestions") or 0,
        }
        result["pipelines"] = query_rows(
            con,
            "select pipeline_name pipeline, status, count(*) count, round(avg(confidence), 4) avgConfidence "
            "from document_pipeline_results group by pipeline_name, status order by pipeline_name, count desc",
        )
        result["pipelineTotals"] = query_rows(
            con,
            "select pipeline_name pipeline, count(*) count, round(avg(confidence), 4) avgConfidence, max(updated_at) latest "
            "from document_pipeline_results group by pipeline_name order by count desc",
        )
        result["reviewSuggestions"] = query_rows(
            con,
            "select source_pipeline pipeline, status, count(*) count, round(avg(confidence), 4) avgConfidence "
            "from document_ai_review_suggestions group by source_pipeline, status order by count desc",
        )
        result["recentPipelines"] = query_rows(
            con,
            "select document_id documentId, pipeline_name pipeline, status, confidence, updated_at updated, substr(error,1,160) error "
            "from document_pipeline_results order by updated_at desc limit 40",
        )
        result["codexAuthPayload"] = _scan_ai_payloads(con)
        result["documentsByLanguage"] = query_rows(
            con,
            "select coalesce(text_language, '[unknown]') language, count(*) count from documents group by text_language order by count desc limit 20",
        )
        result["sourceRoots"] = query_rows(
            con,
            "select coalesce(source_root, '[unknown]') sourceRoot, count(*) sources, count(distinct document_id) documents "
            "from document_sources group by source_root order by sources desc limit 25",
        )
    finally:
        con.close()
    return result


def _scan_ai_payloads(con: sqlite3.Connection) -> dict[str, Any]:
    models: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    field_counts: Counter[str] = Counter()
    pages_analyzed = 0
    visual_elements = 0
    text_regions = 0
    parsed = 0
    payload_errors = 0
    status_by_pipeline: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for row in con.execute(
        "select pipeline_name, status, payload_json from document_pipeline_results "
        "where pipeline_name in ('codex_auth','codex_field_review','ai_verifier','xai_vision','opencode_go')"
    ):
        pipeline = row["pipeline_name"]
        status_by_pipeline[pipeline][row["status"] or "[unknown]"] += 1
        payload = row["payload_json"]
        if not payload:
            continue
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            payload_errors += 1
            continue
        parsed += 1
        if isinstance(data, dict):
            if data.get("model"):
                models[str(data["model"])] += 1
            if data.get("provider"):
                providers[str(data["provider"])] += 1
            fields = data.get("fields")
            if isinstance(fields, list):
                field_counts[pipeline] += len(fields)
            pages = data.get("pages_analyzed")
            if isinstance(pages, list):
                pages_analyzed += len(pages)
            regions = data.get("text_regions")
            if isinstance(regions, list):
                text_regions += len(regions)
            visuals = data.get("visual_elements")
            if isinstance(visuals, list):
                visual_elements += len(visuals)
            conflict_suggestions = data.get("conflict_suggestions")
            if isinstance(conflict_suggestions, list):
                field_counts[f"{pipeline}:conflicts"] += len(conflict_suggestions)
            blank_fills = data.get("blank_fills")
            if isinstance(blank_fills, list):
                field_counts[f"{pipeline}:blank_fills"] += len(blank_fills)
            final_fields = data.get("final_fields")
            if isinstance(final_fields, list):
                field_counts[f"{pipeline}:final_fields"] += len(final_fields)
    return {
        "parsedPayloads": parsed,
        "payloadErrors": payload_errors,
        "models": dict(models.most_common(20)),
        "providers": dict(providers.most_common(20)),
        "fieldCounts": dict(field_counts.most_common(20)),
        "pagesAnalyzed": pages_analyzed,
        "textRegions": text_regions,
        "visualElements": visual_elements,
        "statusByPipeline": {pipeline: dict(counts) for pipeline, counts in status_by_pipeline.items()},
    }


def _recent_files(root: Path, *, patterns: tuple[str, ...], limit: int) -> dict[str, Any]:
    if not root.exists():
        return {"path": path_for_display(root), "exists": False, "files": 0, "latest": []}
    files: list[tuple[float, Path, int]] = []
    for pattern in patterns:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            if any(part in {".git", ".venv", "__pycache__", "node_modules"} for part in path.parts):
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
        "latest": [
            {
                "path": path_for_display(path),
                "bytes": size,
                "modified": timestamp_to_iso(mtime),
                "signals": _log_signals(path) if path.suffix.lower() == ".log" else {},
            }
            for mtime, path, size in files[:limit]
        ],
    }


def _log_signals(path: Path) -> dict[str, int]:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > 65536:
                handle.seek(size - 65536)
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return {}
    lowered = text.lower()
    return {
        "error": lowered.count("error"),
        "traceback": lowered.count("traceback"),
        "quota": lowered.count("quota"),
        "rate": lowered.count("rate"),
        "complete": lowered.count("complete"),
    }
