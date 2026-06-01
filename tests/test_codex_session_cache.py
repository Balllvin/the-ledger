from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from monitor.codex import _get_swear_cache_dir, _swear_cache_key, scan_session_file_fast, scan_session_swear_meter
from monitor.codex import collect_sessions


class CodexSessionCacheTests(unittest.TestCase):
    def test_collect_sessions_reuses_cached_history_and_refreshes_recent_slice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "codex"
            sessions = root / "sessions"
            sessions.mkdir(parents=True)
            cache_dir = Path(directory) / "cache"
            session_file = sessions / "rollout-2024-01-02-aaa-bbb-ccc-ddd-eee.jsonl"
            self._write_session(session_file, "2024-01-02T10:00:00Z", "this is broken", 123)

            first = collect_sessions(root, cache_dir=cache_dir)
            self.assertEqual(first["cache"]["misses"], 1)
            self.assertEqual(first["cache"]["hits"], 0)
            self.assertEqual(first["tokenTotals"]["total_tokens"], 123)
            self.assertEqual(first["tokenTotalsByModel"]["gpt-5.5"]["total_tokens"], 123)
            self.assertEqual(first["swearMeter"]["swearIndexMessages"], 1)

            second = collect_sessions(root, cache_dir=cache_dir)
            self.assertEqual(second["cache"]["hits"], 1)
            self.assertEqual(second["cache"]["misses"], 0)
            self.assertEqual(second["parsedFiles"], 0)
            self.assertEqual(second["swearMeter"]["swearIndexMessages"], 1)

            refreshed = collect_sessions(root, cache_dir=cache_dir, refresh_after_day="2024-01-02")
            self.assertEqual(refreshed["cache"]["hits"], 1)
            self.assertEqual(refreshed["parsedFiles"], 0)
            self.assertEqual(refreshed["swearMeter"]["swearIndexMessages"], 1)

            self._write_session(session_file, "2024-01-02T10:01:00Z", "this is still broken", 456)
            changed = collect_sessions(root, cache_dir=cache_dir, refresh_after_day="2024-01-02")
            self.assertEqual(changed["cache"]["misses"], 1)
            self.assertEqual(changed["parsedFiles"], 1)
            self.assertEqual(changed["tokenTotals"]["total_tokens"], 456)

    def test_swear_cache_hit_keeps_full_session_shape_for_fast_scans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "codex"
            sessions = root / "sessions"
            sessions.mkdir(parents=True)
            cache_dir = Path(directory) / "cache"
            session_file = sessions / "rollout-2024-01-02-aaa-bbb-ccc-ddd-eee.jsonl"
            self._write_session(session_file, "2024-01-02T10:00:00Z", "this is broken", 123)
            _get_swear_cache_dir(cache_dir)

            fresh = scan_session_swear_meter(session_file, archive="active", root=root)
            cached = scan_session_swear_meter(session_file, archive="active", root=root)
            fast = scan_session_file_fast(session_file, archive="active", root=root)

            self.assertIn("swearMeter", fresh)
            self.assertIn("swearMeter", cached)
            self.assertEqual(cached["id"], "thread-one")
            self.assertEqual(cached["swearMeter"]["swearIndexMessages"], 1)
            self.assertEqual(fast["swearMeter"]["swearIndexMessages"], 1)

    def test_swear_cache_key_is_bounded_for_deep_session_paths(self) -> None:
        long_path = Path("/tmp") / ("deep-" * 30) / "rollout-2024-01-02-aaa-bbb-ccc-ddd-eee.jsonl"

        key = _swear_cache_key(long_path)

        self.assertLessEqual(len(key), 69)
        self.assertTrue(key.endswith(".json"))

    @staticmethod
    def _write_session(path: Path, timestamp: str, message: str, tokens: int) -> None:
        rows = [
            {
                "timestamp": timestamp,
                "type": "session_meta",
                "payload": {"type": "session_meta", "id": "thread-one", "cwd": "/tmp/project"},
            },
            {
                "timestamp": timestamp,
                "type": "turn_context",
                "payload": {"type": "turn_context", "model": "gpt-5.5"},
            },
            {
                "timestamp": timestamp,
                "type": "event_msg",
                "payload": {"type": "user_message", "message": message},
            },
            {
                "timestamp": timestamp,
                "type": "response_item",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": tokens,
                            "cached_input_tokens": 0,
                            "output_tokens": 0,
                            "reasoning_output_tokens": 0,
                            "total_tokens": tokens,
                        }
                    },
                },
            },
        ]
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
