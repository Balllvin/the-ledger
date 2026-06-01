from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from monitor.codex import collect_logs


class CodexLogTests(unittest.TestCase):
    def test_collect_logs_aggregates_recent_sample_once(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            db = root / "logs_2.sqlite"
            con = sqlite3.connect(db)
            con.execute(
                """
                create table logs (
                    id integer primary key,
                    ts integer not null,
                    ts_nanos integer not null,
                    level text not null,
                    target text not null,
                    feedback_log_body text,
                    module_path text,
                    file text,
                    line integer,
                    thread_id text,
                    process_uuid text,
                    estimated_bytes integer not null default 0
                )
                """
            )
            con.executemany(
                """
                insert into logs (id, ts, ts_nanos, level, target, feedback_log_body, estimated_bytes)
                values (?, ?, 0, ?, ?, ?, ?)
                """,
                [
                    (1, 1000, "INFO", "one", "ok", 10),
                    (2, 1300, "WARN", "two", "careful", 20),
                    (3, 3700, "ERROR", "two", "broken", 30),
                ],
            )
            con.commit()
            con.close()

            logs = collect_logs(root)

        self.assertTrue(logs["available"])
        self.assertEqual(logs["total"], 3)
        self.assertEqual(logs["sampledRows"], 3)
        self.assertEqual({row["level"]: row["count"] for row in logs["levels"]}, {"INFO": 1, "WARN": 1, "ERROR": 1})
        self.assertEqual(logs["targets"][0], {"target": "two", "count": 2, "bytes": 50})
        self.assertEqual(logs["recentWarnings"][0]["message"], "broken")
        self.assertEqual(logs["byHour"][0]["count"], 1)

    def test_collect_logs_updates_cached_count_from_new_ids(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "codex"
            cache = Path(raw) / "cache"
            root.mkdir()
            db = root / "logs_2.sqlite"
            con = sqlite3.connect(db)
            con.execute(
                """
                create table logs (
                    id integer primary key,
                    ts integer not null,
                    ts_nanos integer not null,
                    level text not null,
                    target text not null,
                    feedback_log_body text,
                    module_path text,
                    file text,
                    line integer,
                    thread_id text,
                    process_uuid text,
                    estimated_bytes integer not null default 0
                )
                """
            )
            con.execute(
                "insert into logs (id, ts, ts_nanos, level, target, estimated_bytes) values (1, 1000, 0, 'INFO', 'one', 10)"
            )
            con.commit()
            con.close()

            first = collect_logs(root, cache_dir=cache)
            con = sqlite3.connect(db)
            con.executemany(
                "insert into logs (id, ts, ts_nanos, level, target, estimated_bytes) values (?, 1000, 0, 'INFO', 'one', 10)",
                [(2,), (3,)],
            )
            con.commit()
            con.close()
            second = collect_logs(root, cache_dir=cache)

        self.assertEqual(first["total"], 1)
        self.assertEqual(second["total"], 3)
        self.assertTrue(second["countCache"]["hit"])


if __name__ == "__main__":
    unittest.main()
