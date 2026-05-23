from __future__ import annotations

import unittest

from monitor.pricing import build_billing_estimate


class PricingTests(unittest.TestCase):
    def test_codex_billing_uses_complete_state_tokens_with_estimated_buckets(self) -> None:
        snapshot = {
            "overview": {"codexStateTokens": 200, "codexJsonlTokens": 100},
            "codex": {
                "state": {"tokensByModel": [{"model": "gpt-5.4", "threads": 2, "tokens": 200}]},
                "sessions": {
                    "tokenTotalsByModel": {
                        "gpt-5.4": {
                            "input_tokens": 80,
                            "cached_input_tokens": 40,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 5,
                            "total_tokens": 100,
                        }
                    }
                },
            },
        }

        billing = build_billing_estimate(snapshot)
        codex = billing["sources"]["codex"]

        self.assertEqual(codex["pricedTokens"], 200)
        self.assertEqual(codex["estimatedTokens"], 200)
        self.assertEqual(codex["billableInputTokens"], 160)
        self.assertEqual(codex["billableOutputTokens"], 40)
        self.assertAlmostEqual(codex["inputUsd"], 0.00022)
        self.assertAlmostEqual(codex["outputUsd"], 0.0006)
        self.assertIn("complete state ledger", codex["note"])

    def test_unknown_model_is_unpriced_not_fallback_priced(self) -> None:
        snapshot = {
            "overview": {"codexStateTokens": 50},
            "codex": {"state": {"tokensByModel": [{"model": "[missing]", "threads": 1, "tokens": 50}]}, "sessions": {}},
        }

        billing = build_billing_estimate(snapshot)
        row = billing["sources"]["codex"]["models"][0]

        self.assertEqual(row["pricedTokens"], 0)
        self.assertEqual(row["unpricedTokens"], 50)
        self.assertEqual(row["totalUsd"], 0)
        self.assertEqual(row["priceModel"], "")

    def test_opencode_deepseek_v4_pro_uses_public_non_discounted_price(self) -> None:
        snapshot = {
            "opencode": {
                "database": {
                    "tokensByModel": {
                        "deepseek-v4-pro": {
                        "input": 1_000_000,
                        "output": 1_000_000,
                        "reasoning": 0,
                        "cacheRead": 1_000_000,
                        "cacheWrite": 0,
                        "total": 3_000_000,
                    }
                }
            }
            }
        }

        billing = build_billing_estimate(snapshot)
        opencode = billing["sources"]["opencode"]

        self.assertEqual(opencode["billableInputTokens"], 2_000_000)
        self.assertAlmostEqual(opencode["inputUsd"], 1.7545)
        self.assertAlmostEqual(opencode["outputUsd"], 3.48)
        self.assertAlmostEqual(opencode["totalUsd"], 5.2345)
        self.assertEqual(opencode["models"][0]["priceSource"], "deepseek")

    def test_cursor_activity_without_token_ledger_is_marked_unavailable_for_billing(self) -> None:
        snapshot = {"cursor": {"available": True, "summary": {"generations": 3}}}

        billing = build_billing_estimate(snapshot)

        self.assertFalse(billing["sources"]["cursor"]["available"])
        self.assertIn("no token/model billing ledger", billing["sources"]["cursor"]["note"])
        self.assertEqual(billing["sources"]["cursor"]["totalUsd"], 0)


if __name__ == "__main__":
    unittest.main()
