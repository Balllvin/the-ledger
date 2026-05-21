from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from monitor.sanitize import safe_preview
from monitor.snapshot import collect_snapshot


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
LOCAL_CACHE = ROOT / ".ledger-cache"
SNAPSHOT_CACHE = LOCAL_CACHE / "snapshot.json"
_CACHE: dict[str, object] = {"timestamp": 0.0, "payload": None, "cacheWarning": None}
_CACHE_LOCK = threading.Lock()
_REFRESH_LOCK = threading.Lock()
_BACKGROUND_REFRESH: subprocess.Popen[bytes] | None = None
CACHE_SECONDS = 20
BACKGROUND_REFRESH_SECONDS = int(os.environ.get("THE_LEDGER_BACKGROUND_REFRESH_SECONDS", "0"))


class Handler(BaseHTTPRequestHandler):
    server_version = "TheLedger/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._json({"ok": True})
            return
        if parsed.path == "/api/snapshot":
            params = parse_qs(parsed.query)
            refresh = params.get("refresh", ["0"])[0] == "1"
            include_hermes = params.get("hermes", ["1"])[0] != "0"
            self._json(get_snapshot(refresh=refresh, include_hermes=include_hermes))
            return
        if parsed.path == "/api/snapshot/events":
            params = parse_qs(parsed.query)
            refresh = params.get("refresh", ["0"])[0] == "1"
            include_hermes = params.get("hermes", ["1"])[0] != "0"
            self._snapshot_events(refresh=refresh, include_hermes=include_hermes)
            return
        if parsed.path in {"/", "/index.html"}:
            self._file(STATIC / "index.html")
            return
        static_path = (STATIC / parsed.path.removeprefix("/")).resolve()
        if not str(static_path).startswith(str(STATIC.resolve())):
            self.send_error(404)
            return
        self._file(static_path)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, payload: object, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _event(self, event: str, payload: object) -> None:
        self.wfile.write(encode_sse(event, payload))
        self.wfile.flush()

    def _snapshot_events(self, *, refresh: bool, include_hermes: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            def progress(message: str) -> None:
                self._event("status", {"message": message})

            if refresh:
                progress("Refreshing the latest local day")
                payload = refresh_snapshot(include_hermes=include_hermes, progress=progress, refresh_recent=True)
            else:
                payload = get_snapshot(refresh=False, include_hermes=include_hermes)
                if (payload.get("meta") or {}).get("loading"):
                    progress("Starting first local scan")
                    payload = refresh_snapshot(include_hermes=include_hermes, progress=progress, refresh_recent=False)
            self._event("complete", payload)
        except Exception as exc:  # pragma: no cover - defensive endpoint boundary
            self._event("error", {"message": str(exc)})


def get_snapshot(*, refresh: bool, include_hermes: bool) -> dict[str, object]:
    now = time.monotonic()
    if refresh:
        return refresh_snapshot(include_hermes=include_hermes, refresh_recent=True)

    with _CACHE_LOCK:
        memory_is_fresh = _CACHE["payload"] is not None and now - float(_CACHE["timestamp"]) < CACHE_SECONDS
        payload = _CACHE["payload"]

    if not refresh and memory_is_fresh:
        return cached_payload("memory") or loading_snapshot()

    if payload is None:
        payload = load_disk_snapshot()

    if payload is not None:
        ensure_background_refresh(include_hermes=include_hermes)
        return cached_payload("disk") or payload  # type: ignore[return-value]

    return loading_snapshot()


def refresh_snapshot(
    *,
    include_hermes: bool,
    progress: Callable[[str], None] | None = None,
    refresh_recent: bool = False,
) -> dict[str, object]:
    with _REFRESH_LOCK:
        cached = cached_payload("memory") or load_disk_snapshot()
        refresh_after_day = latest_snapshot_day(cached) if refresh_recent and cached else None
        payload = collect_snapshot(
            include_hermes=include_hermes,
            progress=progress,
            session_cache_dir=LOCAL_CACHE,
            refresh_after_day=refresh_after_day,
        )
        meta = payload.setdefault("meta", {})
        if isinstance(meta, dict) and refresh_after_day:
            meta["refreshScope"] = "latest-day"
            meta["refreshAfterDay"] = refresh_after_day
        cache_error = store_snapshot(payload)
        if cache_error:
            meta = payload.setdefault("meta", {})
            if isinstance(meta, dict):
                meta["cacheWarning"] = cache_error
        return payload


def ensure_background_refresh(*, include_hermes: bool) -> None:
    global _BACKGROUND_REFRESH
    if not should_background_refresh():
        return
    if _BACKGROUND_REFRESH and _BACKGROUND_REFRESH.poll() is None:
        return
    try:
        LOCAL_CACHE.mkdir(exist_ok=True)
        log = (LOCAL_CACHE / "refresh.log").open("ab")
        command = [sys.executable, "-S", str(ROOT / "server.py"), "--warm-cache"]
        if not include_hermes:
            command.append("--no-hermes")
        _BACKGROUND_REFRESH = subprocess.Popen(command, cwd=str(ROOT), stdout=log, stderr=log, stdin=subprocess.DEVNULL)
        log.close()
    except OSError as exc:
        set_cache_warning(f"Unable to start background refresh: {safe_preview(exc)}")
        return


def should_background_refresh() -> bool:
    with _CACHE_LOCK:
        payload = _CACHE.get("payload")
        timestamp = float(_CACHE.get("timestamp") or 0)
    if payload is None:
        return True
    if BACKGROUND_REFRESH_SECONDS <= 0:
        return False
    return payload is None or time.monotonic() - timestamp > BACKGROUND_REFRESH_SECONDS


def store_snapshot(payload: dict[str, object]) -> str | None:
    error = None
    try:
        LOCAL_CACHE.mkdir(exist_ok=True)
        temporary = SNAPSHOT_CACHE.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(SNAPSHOT_CACHE)
    except OSError as exc:
        error = f"Unable to write snapshot cache: {safe_preview(exc)}"
        write_cache_log(error)
    with _CACHE_LOCK:
        _CACHE["timestamp"] = time.monotonic()
        _CACHE["cacheWarning"] = error
        _CACHE["payload"] = payload
    return error


def load_disk_snapshot() -> dict[str, object] | None:
    try:
        stat = SNAPSHOT_CACHE.stat()
        payload = json.loads(SNAPSHOT_CACHE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        set_cache_warning(f"Unable to read snapshot cache: {safe_preview(exc)}")
        return None
    if not isinstance(payload, dict):
        set_cache_warning("Snapshot cache has an unsupported shape")
        return None
    age = max(0.0, time.time() - stat.st_mtime)
    with _CACHE_LOCK:
        _CACHE["timestamp"] = time.monotonic() - age
        _CACHE["cacheWarning"] = None
        _CACHE["payload"] = payload
    return payload


def cached_payload(source: str) -> dict[str, object] | None:
    with _CACHE_LOCK:
        payload = _CACHE.get("payload")
    if not isinstance(payload, dict):
        return None
    return with_cache_meta(payload, source=source)


def with_cache_meta(payload: dict[str, object], *, source: str) -> dict[str, object]:
    with _CACHE_LOCK:
        cache_warning = _CACHE.get("cacheWarning")
    cloned = dict(payload)
    existing_meta = payload.get("meta")
    meta = dict(existing_meta) if isinstance(existing_meta, dict) else {}
    meta["cached"] = True
    meta["cacheSource"] = source
    meta["refreshing"] = bool(_BACKGROUND_REFRESH and _BACKGROUND_REFRESH.poll() is None)
    if cache_warning:
        meta["cacheWarning"] = cache_warning
    cloned["meta"] = meta
    return cloned


def loading_snapshot() -> dict[str, object]:
    with _CACHE_LOCK:
        cache_warning = _CACHE.get("cacheWarning")
    return {
        "meta": {
            "generatedAt": None,
            "scanSeconds": None,
            "loading": True,
            "message": "Scanning local records",
            **({"cacheWarning": cache_warning} if cache_warning else {}),
        },
        "overview": {},
        "discovery": {},
        "codex": {},
        "opencode": {},
        "cursor": {},
        "lattice": {},
        "hermes": {},
        "about": {},
    }


def set_cache_warning(message: str) -> None:
    with _CACHE_LOCK:
        _CACHE["cacheWarning"] = message
    write_cache_log(message)


def write_cache_log(message: str) -> None:
    try:
        LOCAL_CACHE.mkdir(exist_ok=True)
        with (LOCAL_CACHE / "refresh.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{message}\n")
    except OSError:
        return


def latest_snapshot_day(payload: dict[str, object] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    days: set[str] = set()
    codex = payload.get("codex") if isinstance(payload.get("codex"), dict) else {}
    hermes = payload.get("hermes") if isinstance(payload.get("hermes"), dict) else {}
    opencode = payload.get("opencode") if isinstance(payload.get("opencode"), dict) else {}
    sources = [
        ((codex.get("sessions") or {}).get("timeline") if isinstance(codex, dict) else None),
        (((codex.get("state") or {}).get("projects") or {}).get("total") if isinstance(codex, dict) else None),
        ((((hermes.get("local") or {}).get("state") or {}).get("byDay")) if isinstance(hermes, dict) else None),
        (((opencode.get("database") or {}).get("projects") or {}).get("total") if isinstance(opencode, dict) else None),
    ]
    for rows in sources:
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            day = str(row.get("day") or "")
            if day:
                days.add(day)
    return max(days) if days else None


def encode_sse(event: str, payload: object) -> bytes:
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run The Ledger local usage dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5177)
    parser.add_argument("--warm-cache", action="store_true", help="Refresh the local aggregate snapshot cache and exit.")
    parser.add_argument("--no-hermes", action="store_true", help="Skip Hermes/Codex-agent records for this scan.")
    args = parser.parse_args()
    if args.warm_cache:
        refresh_snapshot(include_hermes=not args.no_hermes)
        return
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"The Ledger running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
