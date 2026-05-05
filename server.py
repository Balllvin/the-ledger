from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from monitor.snapshot import collect_snapshot


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
_CACHE: dict[str, object] = {"timestamp": 0.0, "payload": None}
_CACHE_LOCK = threading.Lock()
CACHE_SECONDS = 20


class Handler(BaseHTTPRequestHandler):
    server_version = "AIUsageMonitor/1.0"

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
            self._event("status", {"message": "Starting scan"})
            self._event("status", {"message": "Reading local usage records"})
            payload = get_snapshot(refresh=refresh, include_hermes=include_hermes)
            self._event("complete", payload)
        except Exception as exc:  # pragma: no cover - defensive endpoint boundary
            self._event("error", {"message": str(exc)})


def get_snapshot(*, refresh: bool, include_hermes: bool) -> dict[str, object]:
    now = time.monotonic()
    with _CACHE_LOCK:
        if not refresh and _CACHE["payload"] is not None and now - float(_CACHE["timestamp"]) < CACHE_SECONDS:
            return _CACHE["payload"]  # type: ignore[return-value]
        payload = collect_snapshot(include_hermes=include_hermes)
        _CACHE["timestamp"] = now
        _CACHE["payload"] = payload
        return payload


def encode_sse(event: str, payload: object) -> bytes:
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n".encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local AI usage monitor.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5177)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"AI Usage Monitor running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
