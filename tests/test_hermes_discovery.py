from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from monitor.discovery import discover_local_sources
from monitor.hermes import _local_hermes_roots


class HermesDiscoveryTests(unittest.TestCase):
    def test_local_hermes_roots_include_profiles_and_project_runtimes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / ".hermes" / "profiles" / "iron-man").mkdir(parents=True)
            (home / ".hermes" / "profiles" / "iron-man" / "state.db").touch()
            (home / ".hermes" / "profiles" / "jarvis").mkdir(parents=True)
            (home / ".hermes" / "profiles" / "jarvis" / "gateway_state.json").write_text("{}", encoding="utf-8")
            (home / "Desktop" / "Marauder" / "hermes" / "runtime" / "tony").mkdir(parents=True)
            (home / "Desktop" / "Marauder" / "hermes" / "runtime" / "tony" / "state.db").touch()
            (home / "Desktop" / "hermes-desktop-agent" / ".hermes").mkdir(parents=True)
            (home / "Desktop" / "hermes-desktop-agent" / ".hermes" / "state.db").touch()

            roots = {str(path.resolve()) for path in _local_hermes_roots(home)}

        self.assertIn(str((home / ".hermes" / "profiles" / "iron-man").resolve()), roots)
        self.assertIn(str((home / ".hermes" / "profiles" / "jarvis").resolve()), roots)
        self.assertIn(str((home / "Desktop" / "Marauder" / "hermes" / "runtime" / "tony").resolve()), roots)
        self.assertIn(str((home / "Desktop" / "hermes-desktop-agent" / ".hermes").resolve()), roots)

    def test_discovery_reports_profile_roots_without_deep_text_scan(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / ".hermes" / "profiles" / "chipmunk").mkdir(parents=True)
            (home / ".hermes" / "profiles" / "chipmunk" / "state.db").touch()
            (home / "Desktop" / "App" / "hermes" / "runtime" / "iron-man").mkdir(parents=True)
            (home / "Desktop" / "App" / "hermes" / "runtime" / "iron-man" / "gateway_state.json").write_text("{}", encoding="utf-8")

            discovery = discover_local_sources(home)
            roots = {str(Path(item["path"]).resolve()) for item in discovery["hermesRoots"]}

        self.assertIn(str((home / ".hermes" / "profiles" / "chipmunk").resolve()), roots)
        self.assertIn(str((home / "Desktop" / "App" / "hermes" / "runtime" / "iron-man").resolve()), roots)


if __name__ == "__main__":
    unittest.main()
