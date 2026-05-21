from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from monitor.discovery import enrich_discovery_with_workspaces
from monitor.hermes import _aggregate_hermes_state, collect_hermes_state


class WorkspaceDiscoveryTests(unittest.TestCase):
    def test_workspaces_add_codex_linked_app_and_hermes_roots(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            workspace = home / "Projects" / "ClientApp"
            (workspace / "data").mkdir(parents=True)
            (workspace / "data" / "lattice.db").touch()
            hermes_root = workspace / "runtime" / "hermes" / "chipmunk"
            hermes_root.mkdir(parents=True)
            (hermes_root / "state.db").touch()

            discovery = enrich_discovery_with_workspaces({"scanRoots": [], "appRoots": [], "hermesRoots": []}, [workspace], home)

        app_paths = {item["path"] for item in discovery["appRoots"]}
        hermes_paths = {item["path"] for item in discovery["hermesRoots"]}
        self.assertIn(str(workspace.resolve()), app_paths)
        self.assertIn(str(hermes_root.resolve()), hermes_paths)

    def test_hermes_session_rows_include_model_source_and_cost_fields(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "state.db"
            con = sqlite3.connect(db)
            con.execute(
                """
                create table sessions (
                    id text primary key,
                    title text,
                    source text,
                    model text,
                    started_at real not null,
                    ended_at real,
                    end_reason text,
                    message_count integer,
                    tool_call_count integer,
                    input_tokens integer,
                    output_tokens integer,
                    cache_read_tokens integer,
                    cache_write_tokens integer,
                    reasoning_tokens integer,
                    billing_provider text,
                    billing_mode text,
                    estimated_cost_usd real,
                    actual_cost_usd real,
                    cost_status text,
                    cost_source text
                )
                """
            )
            con.execute(
                """
                insert into sessions values (
                    's1', 'Cron run', 'cron', 'gpt-5.3-codex', 1000, 1100, 'done', 4, 2,
                    100, 20, 30, 7, 5, 'openai', 'estimated', 0.42, 0.41, 'priced', 'local'
                )
                """
            )
            con.commit()
            con.close()

            state = collect_hermes_state(db)

        self.assertEqual(state["sessions"]["total"], 1)
        self.assertEqual(state["byModel"][0]["model"], "gpt-5.3-codex")
        self.assertEqual(state["bySource"][0]["source"], "cron")
        self.assertEqual(state["recentSessions"][0]["cacheReadTokens"], 30)
        self.assertEqual(state["recentSessions"][0]["billingProvider"], "openai")
        self.assertEqual(state["recentSessions"][0]["actualCostUsd"], 0.41)

    def test_hermes_aggregate_keeps_sources_and_recent_sessions_from_all_roots(self) -> None:
        state = _aggregate_hermes_state(
            [
                {
                    "available": True,
                    "sessions": {"total": 1, "inputTokens": 10, "outputTokens": 2, "reasoningTokens": 1},
                    "messages": {"total": 1, "tokens": 0},
                    "bySource": [{"source": "cli", "sessions": 1, "tokens": 13}],
                    "recentSessions": [{"id": "a", "source": "cli", "model": "gpt-5.5", "started": "1970-01-01T00:00:01Z", "tokens": 13}],
                    "topSessions": [{"id": "a", "tokens": 13}],
                    "swearMeter": {},
                },
                {
                    "available": True,
                    "sessions": {"total": 2, "inputTokens": 20, "outputTokens": 4, "reasoningTokens": 2},
                    "messages": {"total": 2, "tokens": 0},
                    "bySource": [{"source": "cron", "sessions": 2, "tokens": 26}],
                    "recentSessions": [{"id": "b", "source": "cron", "model": "gpt-5.3-codex", "started": "1970-01-01T00:00:02Z", "tokens": 26}],
                    "topSessions": [{"id": "b", "tokens": 26}],
                    "swearMeter": {},
                },
            ]
        )

        self.assertEqual(state["sessions"]["total"], 3)
        self.assertEqual({row["source"] for row in state["bySource"]}, {"cli", "cron"})
        self.assertEqual(state["recentSessions"][0]["source"], "cron")
        self.assertEqual(state["topSessions"][0]["id"], "b")


if __name__ == "__main__":
    unittest.main()
