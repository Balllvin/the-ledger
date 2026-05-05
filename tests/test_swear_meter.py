from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from monitor.codex import collect_sessions, scan_session_file
from monitor.swear_meter import analyze_user_message, match_message, should_skip_message


class SwearMeterTests(unittest.TestCase):
    def test_match_message_uses_word_boundaries(self) -> None:
        self.assertEqual(match_message("the tissue sample is fine"), [])
        self.assertEqual(match_message("what the hell is this")[0]["term"], "what the hell")

    def test_skip_scaffold_and_automations(self) -> None:
        self.assertTrue(should_skip_message("# AGENTS.md instructions\n..."))
        self.assertTrue(should_skip_message("<skill>\n<name>example</name>"))
        self.assertTrue(should_skip_message("Automation: Queue Keeper\n..."))
        self.assertFalse(should_skip_message("Automation: Queue Keeper\n...", include_automations=True))

    def test_analyze_user_message_counts_rate_inputs_without_raw_text(self) -> None:
        result = analyze_user_message("what the hell is this, this is garbage", "2025-01-06T09:00:00Z")

        self.assertEqual(result["directUserMessages"], 1)
        self.assertEqual(result["swearIndexMessages"], 1)
        self.assertGreaterEqual(result["swearIndexOccurrences"], 2)
        self.assertEqual(result["timeline"][("2025-01-06", "messages")], 1)
        self.assertEqual(result["timeline"][("2025-01-06", "swearMessages")], 1)

    def test_scan_session_file_adds_privacy_safe_swear_meter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout-test.jsonl"
            rows = [
                {
                    "timestamp": "2025-01-06T09:00:00Z",
                    "type": "session_meta",
                    "payload": {"id": "thread-1", "cwd": "/work/example", "source": "cli"},
                },
                {
                    "timestamp": "2025-01-06T09:01:00Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "what the hell is this"},
                },
                {
                    "timestamp": "2025-01-06T09:02:00Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "# AGENTS.md instructions\nignore me"},
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            stats = scan_session_file(path, archive="active", root=Path(tmp))

        meter = stats["swearMeter"]
        self.assertEqual(meter["directUserMessages"], 1)
        self.assertEqual(meter["swearIndexMessages"], 1)
        self.assertEqual(meter["swearIndexRate"], 100)
        self.assertNotIn("ignore me", json.dumps(meter).lower())

    def test_scan_session_file_deduplicates_user_message_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout-test.jsonl"
            rows = [
                {
                    "timestamp": "2025-01-06T09:01:00Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "this is awful"},
                },
                {
                    "timestamp": "2025-01-06T09:01:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "this is awful"}],
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            stats = scan_session_file(path, archive="active", root=Path(tmp))

        meter = stats["swearMeter"]
        self.assertEqual(meter["directUserMessages"], 1)
        self.assertEqual(meter["swearIndexMessages"], 1)

    def test_collect_sessions_aggregates_swear_meter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir()
            first = sessions / "rollout-one.jsonl"
            second = sessions / "rollout-two.jsonl"
            first.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        {
                            "timestamp": "2025-01-06T09:00:00Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "this is awful"},
                        },
                        {
                            "timestamp": "2025-01-06T09:05:00Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "ship it"},
                        },
                    ]
                ),
                encoding="utf-8",
            )
            second.write_text(
                json.dumps(
                    {
                        "timestamp": "2025-01-07T09:00:00Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "looks good"},
                    }
                ),
                encoding="utf-8",
            )

            summary = collect_sessions(root)["swearMeter"]

        self.assertEqual(summary["directUserMessages"], 3)
        self.assertEqual(summary["swearIndexMessages"], 1)
        self.assertEqual(summary["swearIndexRate"], 33.33)
        self.assertEqual(summary["terms"][0]["term"], "this is awful")
        self.assertEqual(summary["timeline"][0]["day"], "2025-01-06")


if __name__ == "__main__":
    unittest.main()
