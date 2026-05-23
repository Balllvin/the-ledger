from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from monitor.cursor import collect_cursor


class CursorCollectorTests(unittest.TestCase):
    def test_collects_cursor_logs_and_workspace_activity_without_raw_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            app = home / "Library" / "Application Support" / "Cursor"
            logs = app / "logs" / "run"
            process_monitor = app / "process-monitor"
            global_storage = app / "User" / "globalStorage"
            workspace_storage = app / "User" / "workspaceStorage" / "workspace-one"
            logs.mkdir(parents=True)
            process_monitor.mkdir(parents=True)
            global_storage.mkdir(parents=True)
            workspace_storage.mkdir(parents=True)
            (logs / "main.log").write_text("log body should not be returned", encoding="utf-8")
            (process_monitor / "sample.log").write_text(
                json.dumps(
                    {
                        "sampleStart": 1_700_000_000_000,
                        "sampleEnd": 1_700_000_001_000,
                        "numSubsamples": 2,
                        "sessionId": "session-one",
                        "rows": [{"processName": "Cursor Helper (Plugin): extension-host (agent-exec)", "samplePeakMemMb": 12, "cpuDuringSamplePeakPct": 3}],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            self._state_db(
                global_storage / "state.vscdb",
                {
                    "aiCodeTracking.dailyStats.v1.5.2024-01-02": json.dumps(
                        {
                            "date": "2024-01-02",
                            "tabSuggestedLines": 3,
                            "tabAcceptedLines": 2,
                            "composerSuggestedLines": 5,
                            "composerAcceptedLines": 4,
                        }
                    ),
                    "cursorAuth/accessToken": "secret-token",
                },
            )
            (workspace_storage / "workspace.json").write_text(json.dumps({"folder": f"file://{home}/Project"}), encoding="utf-8")
            self._state_db(
                workspace_storage / "state.vscdb",
                {
                    "aiService.generations": json.dumps([{"unixMs": 1, "textDescription": "private prompt output"}]),
                    "aiService.prompts": json.dumps([{"text": "private prompt input"}]),
                    "composer.composerData": json.dumps({"allComposers": [{"composerId": "c1", "totalLinesAdded": 7, "totalLinesRemoved": 2}]}),
                },
            )

            data = collect_cursor(home)

        self.assertTrue(data["available"])
        self.assertEqual(data["logs"]["files"], 1)
        self.assertEqual(data["processMonitor"]["samples"], 1)
        self.assertEqual(data["processMonitor"]["topProcesses"][0]["name"], "agent-exec")
        self.assertEqual(data["globalState"]["dailyStats"]["totals"]["composerAcceptedLines"], 4)
        self.assertEqual(data["workspaces"]["workspaces"][0]["generations"], 1)
        self.assertEqual(data["workspaces"]["workspaces"][0]["prompts"], 1)
        self.assertEqual(data["summary"]["acceptedLines"], 6)
        self.assertNotIn("private prompt", json.dumps(data))
        self.assertNotIn("secret-token", json.dumps(data))

    @staticmethod
    def _state_db(path: Path, values: dict[str, str]) -> None:
        con = sqlite3.connect(path)
        con.execute("create table ItemTable (key text primary key, value text)")
        for key, value in values.items():
            con.execute("insert into ItemTable values (?, ?)", (key, value))
        con.commit()
        con.close()


if __name__ == "__main__":
    unittest.main()
