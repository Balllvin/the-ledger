from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from monitor.lattice import _collect_lattice_db


class LatticePayloadTests(unittest.TestCase):
    def test_lattice_payload_summary_counts_ai_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "lattice.db"
            con = sqlite3.connect(db)
            con.execute(
                "create table document_pipeline_results (document_id integer, pipeline_name text, status text, confidence real, payload_json text, error text, updated_at text)"
            )
            con.execute("create table document_ai_review_suggestions (source_pipeline text, status text, confidence real)")
            con.execute("create table documents (text_language text)")
            con.execute("create table document_sources (source_root text, document_id integer)")
            for table in ["pages", "page_regions", "document_rows", "template_rows"]:
                con.execute(f"create table {table} (id integer)")
            payload = {
                "model": "gpt-5.5",
                "provider": "codex_auth",
                "fields": [{"name": "amount"}, {"name": "date"}],
                "pages_analyzed": [1, 2],
                "text_regions": [{"text": "A"}],
                "visual_elements": [{"label": "stamp"}],
            }
            con.execute(
                "insert into document_pipeline_results values (1,'codex_auth','complete',0.9,?,?,?)",
                (json.dumps(payload), "", "2026-05-04 10:00:00"),
            )
            con.execute("insert into document_ai_review_suggestions values ('codex_field_review','conflict_suggested',0.95)")
            con.execute("insert into documents values ('de')")
            con.commit()
            con.close()

            stats = _collect_lattice_db(db)

        summary = stats["codexAuthPayload"]
        self.assertEqual(summary["models"]["gpt-5.5"], 1)
        self.assertEqual(summary["providers"]["codex_auth"], 1)
        self.assertEqual(summary["fieldCounts"]["codex_auth"], 2)
        self.assertEqual(summary["pagesAnalyzed"], 2)
        self.assertEqual(summary["textRegions"], 1)
        self.assertEqual(summary["visualElements"], 1)


if __name__ == "__main__":
    unittest.main()
