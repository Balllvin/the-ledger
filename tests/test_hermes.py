from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from monitor.hermes import collect_local_hermes


class HermesCollectorTests(unittest.TestCase):
    def test_collects_local_hermes_state_without_auth_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".codex"
            codex.mkdir()
            (codex / "auth.json").write_text('{"access_token":"secret"}', encoding="utf-8")

            root = home / "Desktop" / "runtime" / "hermes" / "chipmunk"
            root2 = home / "Desktop" / "runtime" / "hermes" / "jarvis"
            sessions = root / "sessions"
            sessions2 = root2 / "sessions"
            sessions.mkdir(parents=True)
            sessions2.mkdir(parents=True)
            (root / "auth.json").write_text('{"token":"secret"}', encoding="utf-8")
            (root / "gateway_state.json").write_text('{"online":true}', encoding="utf-8")
            (root / "config.yaml").write_text("profile: default\napi_key: secret\n", encoding="utf-8")
            (sessions / "sample.jsonl").write_text('{"ok":true}\n', encoding="utf-8")
            (root2 / "auth.json").write_text('{"token":"secret"}', encoding="utf-8")
            (sessions2 / "sample2.jsonl").write_text('{"ok":true}\n', encoding="utf-8")

            con = sqlite3.connect(root / "state.db")
            con.execute(
                "create table sessions ("
                "id text, source text, user_id text, model text, model_config text, system_prompt text, "
                "parent_session_id text, started_at text, ended_at text, end_reason text, message_count integer, "
                "tool_call_count integer, input_tokens integer, output_tokens integer, cache_read_tokens integer, "
                "cache_write_tokens integer, reasoning_tokens integer, billing_provider text, billing_base_url text, "
                "billing_mode text, estimated_cost_usd real, actual_cost_usd real, cost_status text, cost_source text, "
                "pricing_version text, title text, api_call_count integer)"
            )
            con.execute(
                "insert into sessions values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "s1",
                    "codex",
                    "u1",
                    "gpt-test",
                    "{}",
                    "",
                    None,
                    "2024-01-01T00:00:00Z",
                    "2024-01-01T00:01:00Z",
                    "done",
                    2,
                    1,
                    10,
                    4,
                    3,
                    0,
                    2,
                    "openai",
                    "",
                    "usage",
                    0.01,
                    0.01,
                    "estimated",
                    "local",
                    "test",
                    "Synthetic",
                    1,
                ),
            )
            con.execute(
                "create table messages (id integer, session_id text, role text, content text, tool_call_id text, "
                "tool_calls text, tool_name text, timestamp text, token_count integer, finish_reason text, reasoning text, "
                "reasoning_content text, reasoning_details text, codex_reasoning_items text, codex_message_items text)"
            )
            con.execute("insert into messages values (1,'s1','assistant','secret body',null,null,'shell','',6,null,null,null,null,null,null)")
            con.execute("insert into messages values (2,'s1','user','what the fuck',null,null,'','2024-01-01T00:00:30Z',3,null,null,null,null,null,null)")
            con.commit()
            con.close()

            con2 = sqlite3.connect(root2 / "state.db")
            con2.execute(
                "create table sessions ("
                "id text, source text, user_id text, model text, model_config text, system_prompt text, "
                "parent_session_id text, started_at text, ended_at text, end_reason text, message_count integer, "
                "tool_call_count integer, input_tokens integer, output_tokens integer, cache_read_tokens integer, "
                "cache_write_tokens integer, reasoning_tokens integer, billing_provider text, billing_base_url text, "
                "billing_mode text, estimated_cost_usd real, actual_cost_usd real, cost_status text, cost_source text, "
                "pricing_version text, title text, api_call_count integer)"
            )
            con2.execute(
                "insert into sessions values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "s2",
                    "telegram",
                    "u2",
                    "gpt-test",
                    "{}",
                    "",
                    None,
                    "2024-01-02T00:00:00Z",
                    "2024-01-02T00:01:00Z",
                    "done",
                    1,
                    0,
                    20,
                    5,
                    0,
                    0,
                    0,
                    "openai",
                    "",
                    "usage",
                    0.02,
                    0.02,
                    "estimated",
                    "local",
                    "test",
                    "Synthetic2",
                    1,
                ),
            )
            con2.execute(
                "create table messages (id integer, session_id text, role text, content text, tool_call_id text, "
                "tool_calls text, tool_name text, timestamp text, token_count integer, finish_reason text, reasoning text, "
                "reasoning_content text, reasoning_details text, codex_reasoning_items text, codex_message_items text)"
            )
            con2.execute("insert into messages values (1,'s2','user','damn this is broken',null,null,'','2024-01-02T00:00:30Z',4,null,null,null,null,null,null)")
            con2.commit()
            con2.close()

            data = collect_local_hermes(home)

        self.assertTrue(data["available"])
        self.assertEqual(data["state"]["sessions"]["total"], 2)
        self.assertEqual(data["state"]["sessions"]["inputTokens"], 30)
        self.assertEqual(data["state"]["messages"]["tokens"], 13)
        self.assertTrue(data["auth"]["redacted"])
        self.assertTrue(data["codexAuth"]["redacted"])
        self.assertEqual(data["sessions"]["files"], 2)
        self.assertEqual(data["state"]["swearMeter"]["directUserMessages"], 2)
        self.assertGreaterEqual(data["state"]["swearMeter"]["swearIndexMessages"], 1)


if __name__ == "__main__":
    unittest.main()
