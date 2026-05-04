from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from monitor.codex import _collect_project_usage, scan_session_file


class CodexParserTests(unittest.TestCase):
    def test_session_uses_latest_cumulative_token_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout-test.jsonl"
            rows = [
                {
                    "timestamp": "2026-05-04T10:00:00Z",
                    "type": "session_meta",
                    "payload": {"id": "thread-1", "cwd": r"C:\Work", "source": "vscode", "model_provider": "openai"},
                },
                {
                    "timestamp": "2026-05-04T10:01:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 13},
                            "last_token_usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 13},
                            "model_context_window": 100,
                        },
                    },
                },
                {
                    "timestamp": "2026-05-04T10:02:00Z",
                    "type": "response_item",
                    "payload": {"type": "function_call", "name": "shell_command", "arguments": "{}"},
                },
                {
                    "timestamp": "2026-05-04T10:03:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {"input_tokens": 20, "cached_input_tokens": 4, "output_tokens": 6, "reasoning_output_tokens": 2, "total_tokens": 26},
                            "last_token_usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 13},
                            "model_context_window": 100,
                        },
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

            stats = scan_session_file(path, archive="active", root=Path(tmp))

        self.assertEqual(stats["id"], "thread-1")
        self.assertEqual(stats["latestTokenUsage"]["total_tokens"], 26)
        self.assertEqual(stats["latestTokenUsage"]["input_tokens"], 20)
        self.assertEqual(stats["tools"]["shell_command"], 1)
        self.assertEqual(stats["tokenEvents"], 2)

    def test_project_usage_groups_normalized_cwd_by_day(self) -> None:
        import sqlite3

        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute(
            "create table threads (id text, title text, source text, model_provider text, cwd text, tokens_used integer, created_at integer, updated_at integer, archived integer)"
        )
        con.executemany(
            "insert into threads values (?,?,?,?,?,?,?,?,?)",
            [
                ("1", "A", "vscode", "openai", r"\\?\C:\Users\Example\Desktop", 100, 1777852800, 1777852900, 0),
                ("2", "B", "vscode", "openai", r"C:\Users\Example\Desktop", 50, 1777852800, 1777853000, 0),
                ("3", "C", "vscode", "openai", r"C:\Users\Example\Documents\SampleProject", 25, 1777939200, 1777939300, 0),
            ],
        )

        usage = _collect_project_usage(con)

        self.assertEqual(usage["total"][0]["tokens"], 150)
        self.assertEqual(usage["total"][1]["tokens"], 25)
        desktop = next(project for project in usage["projects"] if project["name"] == "Desktop")
        self.assertEqual(desktop["tokens"], 150)
        self.assertEqual(desktop["threads"], 2)
        self.assertEqual(desktop["days"][0]["tokens"], 150)


if __name__ == "__main__":
    unittest.main()
