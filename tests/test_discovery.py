from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from monitor.discovery import discover_local_sources, preferred_codex_root


class DiscoveryTests(unittest.TestCase):
    def test_discovers_codex_root_and_app_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".codex"
            codex.mkdir()
            (codex / "auth.json").write_text("{}", encoding="utf-8")
            (codex / "state_5.sqlite").write_bytes(b"")
            app = home / "Documents" / "sample-app"
            app.mkdir(parents=True)
            (app / "README.md").write_text("Uses CODEX_HOME for local runs.", encoding="utf-8")

            discovery = discover_local_sources(home)

        self.assertTrue(discovery["codexRoots"])
        self.assertEqual(Path(discovery["codexRoots"][0]["path"]).name, ".codex")
        self.assertTrue(any(item["path"].endswith("sample-app") for item in discovery["appRoots"]))

    def test_preferred_codex_root_uses_existing_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".codex"
            codex.mkdir()
            discovery = discover_local_sources(home)

            preferred = preferred_codex_root(discovery, home)

        self.assertEqual(preferred.name, ".codex")


if __name__ == "__main__":
    unittest.main()
