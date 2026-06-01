from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from server import encode_sse


class ServerSentEventTests(unittest.TestCase):
    def test_encodes_named_json_event(self) -> None:
        encoded = encode_sse("status", {"message": "Reading local usage records"}).decode("utf-8")

        self.assertTrue(encoded.startswith("event: status\n"))
        self.assertIn("data: ", encoded)
        self.assertTrue(encoded.endswith("\n\n"))
        payload = encoded.split("data: ", 1)[1].strip()
        self.assertEqual(json.loads(payload), {"message": "Reading local usage records"})

    def test_disk_snapshot_cache_round_trips_without_collecting(self) -> None:
        payload = {"meta": {"generatedAt": "example"}, "overview": {"tokens": 12}}
        original_cache = dict(server._CACHE)
        with tempfile.TemporaryDirectory() as raw:
            cache_dir = Path(raw)
            try:
                with patch.object(server, "LOCAL_CACHE", cache_dir), patch.object(server, "SNAPSHOT_CACHE", cache_dir / "snapshot.json"):
                    server.store_snapshot(payload)
                    server._CACHE["payload"] = None

                    loaded = server.load_disk_snapshot()
                    cached = server.cached_payload("disk")
            finally:
                server._CACHE.clear()
                server._CACHE.update(original_cache)

        self.assertEqual(loaded["overview"]["tokens"], 12)
        self.assertTrue(cached["meta"]["cached"])
        self.assertEqual(cached["meta"]["cacheSource"], "disk")

    def test_get_snapshot_returns_fresh_memory_cache_without_relocking(self) -> None:
        payload = {"meta": {"generatedAt": "example"}, "overview": {"tokens": 12}}
        original_cache = dict(server._CACHE)
        with tempfile.TemporaryDirectory() as raw:
            cache_dir = Path(raw)
            try:
                with patch.object(server, "LOCAL_CACHE", cache_dir), patch.object(server, "SNAPSHOT_CACHE", cache_dir / "snapshot.json"):
                    server.store_snapshot(payload)
                    cached = server.get_snapshot(refresh=False, include_hermes=True)
            finally:
                server._CACHE.clear()
                server._CACHE.update(original_cache)

        self.assertEqual(cached["overview"]["tokens"], 12)
        self.assertTrue(cached["meta"]["cached"])
        self.assertEqual(cached["meta"]["cacheSource"], "memory")

    def test_loading_snapshot_is_renderable(self) -> None:
        payload = server.loading_snapshot()

        self.assertTrue(payload["meta"]["loading"])
        self.assertEqual(payload["overview"], {})
        self.assertIn("codex", payload)

    def test_recent_refresh_reuses_previous_discovery_snapshot(self) -> None:
        cached_payload = {
            "meta": {"generatedAt": "example"},
            "discovery": {"scanRoots": ["/tmp/project"], "hermesRoots": []},
            "codex": {"sessions": {"timeline": [{"day": "2024-01-02", "tokens": 1}]}},
            "overview": {},
        }
        original_cache = dict(server._CACHE)
        with tempfile.TemporaryDirectory() as raw:
            cache_dir = Path(raw)
            try:
                with patch.object(server, "LOCAL_CACHE", cache_dir), patch.object(server, "SNAPSHOT_CACHE", cache_dir / "snapshot.json"):
                    server.store_snapshot(cached_payload)
                    with patch.object(server, "collect_snapshot") as collect:
                        collect.return_value = {"meta": {}, "overview": {}, "codex": {}}

                        server.refresh_snapshot(include_hermes=True, refresh_recent=True)
            finally:
                server._CACHE.clear()
                server._CACHE.update(original_cache)

        self.assertEqual(collect.call_args.kwargs["previous_snapshot"]["discovery"], cached_payload["discovery"])
        self.assertEqual(collect.call_args.kwargs["refresh_after_day"], "2024-01-02")


if __name__ == "__main__":
    unittest.main()
