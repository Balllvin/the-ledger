from __future__ import annotations

import unittest

from monitor.sanitize import sanitize


class SanitizeTests(unittest.TestCase):
    def test_secret_keys_are_redacted_recursively(self) -> None:
        payload = {
            "tokens": {"access_token": "secret", "refresh_token": "secret"},
            "safe": {"path": r"C:\Users\Example\.codex"},
            "items": [{"api_key": "sk-testsecretsecretsecret"}, {"name": "visible"}],
        }

        redacted = sanitize(payload)

        self.assertEqual(redacted["tokens"]["access_token"], "[redacted]")
        self.assertEqual(redacted["tokens"]["refresh_token"], "[redacted]")
        self.assertEqual(redacted["items"][0]["api_key"], "[redacted]")
        self.assertEqual(redacted["items"][1]["name"], "visible")
        self.assertIn(".codex", redacted["safe"]["path"])

    def test_secret_like_string_is_redacted(self) -> None:
        redacted = sanitize({"message": "Bearer abcdefghijklmnopqrstuvwxyz123456"})

        self.assertEqual(redacted["message"], "[redacted]")


if __name__ == "__main__":
    unittest.main()
