from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monitor.discovery import discover_local_sources, preferred_codex_root, preferred_lattice_root


class DiscoveryTests(unittest.TestCase):
    def test_discovers_codex_root_and_app_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".codex"
            codex.mkdir()
            (codex / "auth.json").write_text("{}", encoding="utf-8")
            (codex / "state_5.sqlite").write_bytes(b"")
            codex_app = home / "Library" / "Application Support" / "Codex"
            codex_app.mkdir(parents=True)
            (codex_app / "Preferences").write_text("{}", encoding="utf-8")
            hermes = home / "Documents" / "agent-runtime" / "chipmunk"
            (hermes / "sessions").mkdir(parents=True)
            (hermes / "state.db").write_bytes(b"")
            (hermes / "auth.json").write_text("{}", encoding="utf-8")
            app = home / "Documents" / "sample-app"
            app.mkdir(parents=True)
            (app / "codex_auth.json").write_text("{}", encoding="utf-8")

            discovery = discover_local_sources(home)

        self.assertTrue(discovery["codexRoots"])
        self.assertEqual(Path(discovery["codexRoots"][0]["path"]).name, ".codex")
        self.assertTrue(discovery["codexAppRoots"][0]["exists"])
        self.assertTrue(any(item["path"].endswith("chipmunk") for item in discovery["hermesRoots"]))
        self.assertTrue(any(item["path"].endswith("sample-app") for item in discovery["appRoots"]))

    def test_preferred_codex_root_uses_existing_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".codex"
            codex.mkdir()
            discovery = discover_local_sources(home)

            preferred = preferred_codex_root(discovery, home)

        self.assertEqual(preferred.name, ".codex")

    def test_the_ledger_scan_roots_override_default_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            scan_root = Path(tmp) / "scan-root"
            app = scan_root / "sample-app"
            app.mkdir(parents=True)
            (app / "codex_auth.json").write_text("{}", encoding="utf-8")

            with patch.dict("os.environ", {"THE_LEDGER_SCAN_ROOTS": str(scan_root)}, clear=True):
                discovery = discover_local_sources(home)

        self.assertEqual(discovery["scanRoots"], [str(scan_root.resolve())])
        self.assertTrue(any(item["path"].endswith("sample-app") for item in discovery["appRoots"]))

    def test_preferred_lattice_root_uses_the_ledger_env_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ledger-app"

            with patch.dict("os.environ", {"THE_LEDGER_LATTICE_ROOT": str(root)}, clear=True):
                preferred = preferred_lattice_root({}, Path(tmp))

        self.assertEqual(preferred, root)


if __name__ == "__main__":
    unittest.main()
