from __future__ import annotations

import unittest
from unittest import mock

from monitor.rundown import build_daily_rundown, send_telegram_message


class RundownTests(unittest.TestCase):
    def test_daily_rundown_uses_direct_prompts_and_lifetime_totals(self) -> None:
        snapshot = {
            "overview": {
                "codexJsonlTokens": 300,
                "codexSessionFiles": 4,
                "codexModelInputUserItems": 99,
                "hermesTokens": 70,
                "hermesSessions": 2,
            },
            "codex": {
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

        self.assertEqual(rundown["codex"]["tokens"], 100)
        self.assertEqual(rundown["hermes"]["tokens"], 50)
        self.assertIn("Direct prompts checked: 3 (2 Codex, 1 Hermes)", rundown["text"])
        self.assertIn("Frustration index: 1/3 direct prompts (33.3%)", rundown["text"])
        self.assertIn("Codex agent prompts excluded from prompt metrics: 7 for this day", rundown["text"])
        self.assertIn("Codex transcript user items excluded from prompt metrics: 99 lifetime items", rundown["text"])
        self.assertIn("Lifetime check -> Codex: 300 tokens/4 sessions | Hermes: 70 tokens/2 sessions", rundown["text"])

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
