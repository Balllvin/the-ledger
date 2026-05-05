from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import monitor.codex as codex
from monitor.codex import collect_sessions, scan_session_file
from monitor.swear_meter import analyze_user_message, finalize_swear_meter, match_message, should_skip_message


class SwearMeterTests(unittest.TestCase):
    def test_match_message_uses_word_boundaries(self) -> None:
        self.assertEqual(match_message("the tissue sample is fine"), [])
        self.assertEqual(match_message("what the hell is this")[0]["term"], "what the hell is this")
        terms = {hit["term"] for hit in match_message("holy shit, this is nonsense and not even close")}
        self.assertIn("holy shit", terms)
        self.assertIn("this is nonsense", terms)
        self.assertIn("not even close", terms)

    def test_match_message_deduplicates_overlapping_terms(self) -> None:
        terms = {hit["term"]: hit for hit in match_message("what the actual fuck is going on")}

        self.assertIn("what the actual fuck", terms)
        self.assertNotIn("fuck", terms)
        self.assertEqual(sum(hit["count"] for hit in terms.values()), 1)

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
        self.assertEqual(result["timeline"][("2025-01-06", "categoryMessages:wtf_moment")], 1)
        self.assertGreaterEqual(result["categories"]["wtf_moment"], 1)

    def test_category_sets_count_overlapping_categories_once(self) -> None:
        result = analyze_user_message("stop hallucinating and this is bullshit", "2025-01-06T09:00:00Z")
        finalized = finalize_swear_meter(result)
        sets = finalized["timeline"][0]["categorySets"]

        self.assertEqual(sum(row["messages"] for row in sets), 1)
        self.assertTrue(any({"ai_coding_failure", "anger_callout"}.issubset(set(row["categories"])) for row in sets))

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
                            "timestamp": "2025-01-06T08:59:00Z",
                            "type": "session_meta",
                            "payload": {"id": "one", "cwd": "/work/example", "source": "cli"},
                        },
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
                "\n".join(
                    json.dumps(row)
                    for row in [
                        {
                            "timestamp": "2025-01-07T08:59:00Z",
                            "type": "session_meta",
                            "payload": {"id": "two", "cwd": "/work/example", "source": "cli"},
                        },
                        {
                            "timestamp": "2025-01-07T09:00:00Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "looks good"},
                        },
                    ]
                ),
                encoding="utf-8",
            )

            sessions_summary = collect_sessions(root)
            summary = sessions_summary["swearMeter"]

        self.assertEqual(summary["directUserMessages"], 3)
        self.assertEqual(summary["swearIndexMessages"], 1)
        self.assertEqual(summary["swearIndexRate"], 33.33)
        self.assertEqual(summary["terms"][0]["term"], "this is awful")
        self.assertEqual(summary["timeline"][0]["day"], "2025-01-06")
        self.assertEqual(sessions_summary["swearByThread"]["one"]["swearIndexMessages"], 1)
        self.assertEqual(sessions_summary["swearByThread"]["two"]["swearIndexMessages"], 0)

    def test_collect_sessions_lightweight_scans_skipped_files_for_swear_meter(self) -> None:
        old_limit = codex.MAX_PARSED_SESSION_FILES
        codex.MAX_PARSED_SESSION_FILES = 1
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                sessions = root / "sessions"
                sessions.mkdir()
                recent = sessions / "rollout-recent.jsonl"
                older = sessions / "rollout-older.jsonl"
                recent.write_text(
                    json.dumps(
                        {
                            "timestamp": "2025-01-07T09:00:00Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "looks good"},
                        }
                    ),
                    encoding="utf-8",
                )
                older.write_text(
                    json.dumps(
                        {
                            "timestamp": "2025-01-06T09:00:00Z",
                            "type": "event_msg",
                            "payload": {"type": "user_message", "message": "holy shit"},
                        }
                    ),
                    encoding="utf-8",
                )

                summary = collect_sessions(root)

            self.assertEqual(summary["parsedFiles"], 1)
            self.assertEqual(summary["skippedFiles"], 1)
            self.assertEqual(summary["swearMeter"]["directUserMessages"], 2)
            self.assertEqual(summary["swearMeter"]["swearIndexMessages"], 1)
        finally:
            codex.MAX_PARSED_SESSION_FILES = old_limit

    def test_swear_meter_lightweight_scan_ignores_non_candidate_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir()
            path = sessions / "rollout-only.jsonl"
            path.write_text(
                "\n".join(
                    [
                        "{not json",
                        json.dumps(
                            {
                                "timestamp": "2025-01-06T09:00:00Z",
                                "type": "event_msg",
                                "payload": {"type": "user_message", "message": "this is bullshit"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            stats = codex.scan_session_swear_meter(path, archive="active", root=root)

        self.assertNotIn("[invalid_json]", stats["eventCounts"])
        self.assertEqual(stats["swearMeter"]["directUserMessages"], 1)
        self.assertEqual(stats["swearMeter"]["swearIndexMessages"], 1)

    def test_swear_meter_cache_returns_isolated_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sessions = root / "sessions"
            sessions.mkdir()
            path = sessions / "rollout-cache.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "timestamp": "2025-01-06T09:00:00Z",
                        "type": "event_msg",
                        "payload": {"type": "user_message", "message": "what the hell"},
                    }
                ),
                encoding="utf-8",
            )

            first = codex.scan_session_swear_meter(path, archive="active", root=root)
            first["swearMeter"]["directUserMessages"] = 0
            second = codex.scan_session_swear_meter(path, archive="active", root=root)

        self.assertEqual(second["swearMeter"]["directUserMessages"], 1)
        self.assertEqual(second["swearMeter"]["swearIndexMessages"], 1)


if __name__ == "__main__":
    unittest.main()
