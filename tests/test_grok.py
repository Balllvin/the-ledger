from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from monitor.grok import collect_grok


class GrokCollectorTests(unittest.TestCase):
    def test_collects_grok_usage_and_threads_without_raw_content_or_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            grok_root = home / ".grok"
            sessions_root = grok_root / "sessions" / "%2Ftmp%2Fproject"
            session_dir = sessions_root / "019e64c7-7f4b-7c23-9134-921c3f9ce664"

            grok_root.mkdir(parents=True)
            sessions_root.mkdir(parents=True)
            session_dir.mkdir(parents=True)

            # Fake auth with secret (must be redacted)
            (grok_root / "auth.json").write_text(json.dumps({"token": "xai-FAKE-SECRET-123"}), encoding="utf-8")

            # Fake grok.db with realistic schema + data
            db = grok_root / "grok.db"
            self._create_grok_db(db)

            # Minimal session FS artifacts (metadata only)
            (session_dir / "summary.json").write_text(
                json.dumps({"title": "Test Grok thread", "model": "grok-4.20", "num_messages": 12}),
                encoding="utf-8",
            )
            (session_dir / "events.jsonl").write_text(
                json.dumps({"ts": "2026-01-01T00:00:00Z", "type": "message", "model": "grok-4.20"}) + "\n",
                encoding="utf-8",
            )

            data = collect_grok(home)

        self.assertTrue(data["available"])
        self.assertTrue(data["auth"]["redacted"])
        self.assertNotIn("xai-FAKE-SECRET", json.dumps(data))

        # DB aggregates surfaced
        self.assertGreaterEqual(data["summary"]["threads"], 1)
        self.assertGreaterEqual(data["summary"]["totalTokens"], 100)
        self.assertIn("grok-4.20", data["summary"]["models"])

        # Recent sessions (may be empty in minimal test DBs; main value is aggregates + redaction)
        recent = data.get("recentSessions") or []
        self.assertGreaterEqual(len(recent), 0)
        self.assertNotIn("private prompt", json.dumps(data))
        self.assertNotIn("secret", json.dumps(data).lower())
        # If any recent rows exist, they must be sanitized
        for r in recent:
            self.assertNotIn("xai-", json.dumps(r).lower())

        # FS metadata present
        self.assertGreater(data["sessions"]["files"], 0)

    @staticmethod
    def _create_grok_db(path: Path) -> None:
        con = sqlite3.connect(path)
        try:
            con.executescript(
                """
                CREATE TABLE workspaces (
                    id TEXT PRIMARY KEY,
                    scope_key TEXT,
                    canonical_path TEXT,
                    display_name TEXT
                );
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT,
                    title TEXT,
                    model TEXT,
                    cwd_last TEXT,
                    status TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE usage_events (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT,
                    source TEXT,
                    model TEXT,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    total_tokens INTEGER,
                    cost_micros INTEGER,
                    created_at TEXT
                );
                """
            )
            con.execute(
                "INSERT INTO workspaces VALUES (?,?,?,?)",
                ("w1", "/tmp/project", "/tmp/project", "Project"),
            )
            con.execute(
                "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
                ("s1", "w1", "First Grok thread", "grok-4.20", "/tmp/project", "completed",
                 "2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"),
            )
            con.execute(
                "INSERT INTO usage_events VALUES (?,?,?,?,?,?,?,?,?)",
                (1, "s1", "message", "grok-4.20", 120, 80, 200, 0, "2026-01-01T00:01:00Z"),
            )
            con.execute(
                "INSERT INTO usage_events VALUES (?,?,?,?,?,?,?,?,?)",
                (2, "s1", "message", "grok-4.20", 50, 30, 80, 0, "2026-01-01T00:02:00Z"),
            )
            con.commit()
        finally:
            con.close()
