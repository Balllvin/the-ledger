from __future__ import annotations

import json
import unittest

from server import encode_sse


class ServerSentEventTests(unittest.TestCase):
    def test_encodes_named_json_event(self) -> None:
        encoded = encode_sse("status", {"message": "Reading local usage records"}).decode("utf-8")

        self.assertTrue(encoded.startswith("event: status\n"))
        self.assertIn("data: ", encoded)
        self.assertTrue(encoded.endswith("\n\n"))
        payload = encoded.split("data: ", 1)[1].strip()
        self.assertEqual(json.loads(payload), {"message": "Reading local usage records"})


if __name__ == "__main__":
    unittest.main()
