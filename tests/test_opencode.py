from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from monitor.opencode import collect_opencode


class OpenCodeCollectorTests(unittest.TestCase):
    def test_collects_cli_app_and_database_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            data_root = home / ".local" / "share" / "opencode"
            data_root.mkdir(parents=True)
            (data_root / "auth.json").write_text('{"token":"secret"}', encoding="utf-8")
            (data_root / "log").mkdir()
            (data_root / "log" / "run.log").write_text("ok", encoding="utf-8")

            app = home / "Library" / "Application Support" / "ai.opencode.desktop" / "opencode"
            app.mkdir(parents=True)
            (app / "model.json").write_text(json.dumps({"recent": [{"providerID": "opencode-go", "modelID": "deepseek-v4-pro"}]}), encoding="utf-8")
            (app / "prompt-history.jsonl").write_text(json.dumps({"input": "hello", "mode": "normal"}) + "\n", encoding="utf-8")

            con = sqlite3.connect(data_root / "opencode.db")
            con.execute("create table session (id text, project_id text, parent_id text, slug text, directory text, title text, version text, share_url text, summary_additions integer, summary_deletions integer, summary_files integer, summary_diffs text, revert text, permission text, time_created integer, time_updated integer, time_compacting integer, time_archived integer, workspace_id text)")
            con.execute("create table message (id text, session_id text, time_created integer, time_updated integer, data text)")
            con.execute("create table part (id text, message_id text, session_id text, time_created integer, time_updated integer, data text)")
            con.execute("create table todo (session_id text, content text, status text, priority text, position integer, time_created integer, time_updated integer)")
            con.execute("insert into session values ('s1','global',null,'slug',?,'Title','1.0',null,0,0,0,null,null,null,1000,2000,null,null,null)", (str(home / "Project"),))
            con.execute(
                "insert into message values ('m1','s1',1000,2000,?)",
                (
                    json.dumps(
                        {
                            "role": "assistant",
                            "providerID": "opencode-go",
                            "modelID": "deepseek-v4-pro",
                            "cost": 0.25,
                            "tokens": {"total": 12, "input": 8, "output": 3, "reasoning": 1, "cache": {"read": 2, "write": 0}},
                        }
                    ),
                ),
            )
            con.execute("insert into part values ('p1','m1','s1',1000,2000,?)", (json.dumps({"type": "tool"}),))
            con.commit()
            con.close()

            data = collect_opencode(home)

        self.assertTrue(data["available"])
        self.assertTrue(data["auth"]["redacted"])
        self.assertEqual(data["database"]["tables"]["session"], 1)
        self.assertEqual(data["database"]["messages"]["tokens"]["total"], 12)
        self.assertEqual(data["database"]["models"]["deepseek-v4-pro"], 1)
        self.assertEqual(data["database"]["projects"]["projects"][0]["tokens"], 12)
        self.assertEqual(data["app"]["promptHistory"]["lines"], 1)
        self.assertEqual(data["logs"]["cli"]["files"], 1)


if __name__ == "__main__":
    unittest.main()
