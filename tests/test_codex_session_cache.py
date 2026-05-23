from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
            self.assertEqual(refreshed["cache"]["refreshed"], 1)
            self.assertEqual(refreshed["parsedFiles"], 1)
            self.assertEqual(refreshed["swearMeter"]["swearIndexMessages"], 1)

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
