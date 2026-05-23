from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from monitor.codex import collect_sessions, scan_session_file


class CodexDirectPromptTests(unittest.TestCase):
    def test_response_item_user_content_is_not_counted_as_direct_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            rows = [
                {
                    "type": "session_meta",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "payload": {"id": "session-id", "source": "vscode"},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-01-01T00:00:01Z",
                    "payload": {"role": "user", "content": [{"text": "<context>broken awful internal transcript</context>"}]},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-01-01T00:00:02Z",
                    "payload": {"type": "user_message", "message": "this is broken"},
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            session = scan_session_file(path, archive="active", root=Path(directory))

        self.assertEqual(session["userMessages"], 1)
        self.assertEqual(session["modelInputUserItems"], 1)
        self.assertEqual(session["swearMeter"]["directUserMessages"], 1)
        self.assertEqual(session["swearMeter"]["swearIndexMessages"], 1)

    def test_collect_sessions_splits_human_and_agent_prompt_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions = root / "sessions"
            sessions.mkdir()
            human = sessions / "human.jsonl"
            agent = sessions / "agent.jsonl"
            human.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z", "payload": {"id": "human", "source": "vscode"}},
                        {"type": "event_msg", "timestamp": "2026-01-01T00:00:01Z", "payload": {"type": "user_message", "message": "this is broken"}},
                    ]
                ),
                encoding="utf-8",
            )
            agent.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        {"type": "session_meta", "timestamp": "2026-01-01T00:00:00Z", "payload": {"id": "agent", "agent_role": "explorer"}},
                        {"type": "event_msg", "timestamp": "2026-01-01T00:00:01Z", "payload": {"type": "user_message", "message": "this is broken"}},
                    ]
                ),
                encoding="utf-8",
            )

            result = collect_sessions(root)

        self.assertEqual(result["swearByOrigin"]["human"]["directUserMessages"], 1)
        self.assertEqual(result["swearByOrigin"]["agent"]["directUserMessages"], 1)


if __name__ == "__main__":
    unittest.main()
