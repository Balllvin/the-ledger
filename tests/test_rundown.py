from __future__ import annotations

import unittest
from unittest import mock

from monitor.rundown import build_daily_rundown, send_telegram_message


class RundownTests(unittest.TestCase):
    def test_daily_rundown_uses_direct_prompts_and_lifetime_totals(self) -> None:
        snapshot = {
            "overview": {
                "codexStateTokens": 500,
                "codexThreads": 5,
                "codexJsonlTokens": 300,
                "codexSessionFiles": 4,
                "codexModelInputUserItems": 99,
                "hermesTokens": 70,
                "hermesSessions": 2,
            },
            "codex": {
                "state": {
                    "projects": {
                        "total": [{"day": "2026-01-01", "threads": 2, "tokens": 120}],
                    },
                },
                "sessions": {
                    "timeline": [{"day": "2026-01-01", "sessions": 3, "tokens": 100}],
                    "swearMeter": {"timeline": [{"day": "2026-01-01", "messages": 2, "swearMessages": 1}]},
                    "swearByOrigin": {
                        "human": {"timeline": [{"day": "2026-01-01", "messages": 2, "swearMessages": 1}]},
                        "agent": {"timeline": [{"day": "2026-01-01", "messages": 7, "swearMessages": 7}]},
                    },
                }
            },
            "hermes": {
                "local": {
                    "state": {
                        "byDay": [{"day": "2026-01-01", "sessions": 1, "tokens": 50}],
                        "swearMeter": {"timeline": [{"day": "2026-01-01", "messages": 1, "swearMessages": 0}]},
                    }
                }
            },
        }

        rundown = build_daily_rundown(snapshot, day="2026-01-01", timezone_name="UTC")

        self.assertEqual(rundown["codex"]["tokens"], 120)
        self.assertEqual(rundown["codex"]["source"], "state")
        self.assertEqual(rundown["hermes"]["tokens"], 50)
        self.assertIn("Total usage (Codex state ledger + Hermes): 170 tokens, 3 runs", rundown["text"])
        self.assertIn("Direct prompts checked: 3 (2 Codex, 1 Hermes)", rundown["text"])
        self.assertIn("Frustration index: 1/3 direct prompts (33.3%)", rundown["text"])
        self.assertIn("Codex agent prompts excluded from prompt metrics: 7 for this day", rundown["text"])
        self.assertIn("Codex transcript user items excluded from prompt metrics: 99 lifetime items", rundown["text"])
        self.assertIn("Lifetime check -> Codex state ledger: 500 tokens/5 threads | Codex JSONL scan: 300 tokens/4 sessions | Hermes: 70 tokens/2 sessions", rundown["text"])
        self.assertIn("Codex source check -> state ledger: 120 tokens/2 threads | JSONL scan: 100 tokens/3 sessions", rundown["text"])

    def test_daily_rundown_falls_back_to_jsonl_when_state_day_is_missing(self) -> None:
        snapshot = {
            "overview": {"codexStateTokens": 500, "codexJsonlTokens": 300},
            "codex": {
                "state": {"projects": {"total": []}},
                "sessions": {"timeline": [{"day": "2026-01-01", "sessions": 3, "tokens": 100}]},
            },
        }

        rundown = build_daily_rundown(snapshot, day="2026-01-01", timezone_name="UTC")

        self.assertEqual(rundown["codex"]["tokens"], 100)
        self.assertEqual(rundown["codex"]["source"], "jsonl")
        self.assertIn("Codex: 100 tokens, 3 sessions (Codex JSONL scan)", rundown["text"])

    def test_daily_rundown_questions_zero_codex_usage_when_lifetime_exists(self) -> None:
        snapshot = {"overview": {"codexStateTokens": 500}, "codex": {"sessions": {}}}

        rundown = build_daily_rundown(snapshot, day="2026-01-01", timezone_name="UTC")

        self.assertIn("Zero-check: Codex has lifetime records but no usage row for this day.", rundown["text"])

    def test_telegram_send_requires_environment(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            result = send_telegram_message("hello")

        self.assertFalse(result["ok"])
        self.assertIn("TELEGRAM_BOT_TOKEN", result["error"])

    def test_invalid_timezone_is_reported(self) -> None:
        rundown = build_daily_rundown({"overview": {}}, timezone_name="Not/AZone")

        self.assertEqual(rundown["timezone"], "UTC")
        self.assertIn("Timezone note:", rundown["text"])


if __name__ == "__main__":
    unittest.main()
