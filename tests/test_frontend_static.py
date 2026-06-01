from __future__ import annotations

import re
import unittest
from pathlib import Path


APP_JS = Path(__file__).resolve().parents[1] / "static" / "app.js"
INDEX_HTML = Path(__file__).resolve().parents[1] / "static" / "index.html"


def function_body(name: str) -> str:
    source = APP_JS.read_text(encoding="utf-8")
    match = re.search(rf"function {re.escape(name)}\([^)]*\) \{{", source)
    if not match:
        raise AssertionError(f"{name} was not found in static/app.js")
    depth = 1
    index = match.end()
    while index < len(source) and depth:
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    if depth:
        raise AssertionError(f"{name} body was not balanced")
    return source[match.end() : index - 1]


class FrontendStaticTests(unittest.TestCase):
    def test_load_snapshot_and_main_render_exist_and_are_safe(self) -> None:
        body = function_body("loadSnapshot")
        self.assertIn('fetch(`/api/snapshot', body)
        self.assertIn("render(data)", body)
        self.assertIn("refreshSnapshotStream", body)

        main_render = APP_JS.read_text(encoding="utf-8")
        render_body = function_body("render")
        self.assertIn("snapshot = data", render_body)
        self.assertIn("renderUsagePage(data)", render_body)
        self.assertIn("renderSourcesPage(data)", render_body)
        self.assertIn("renderProjectPage(data)", render_body)

    def test_sources_and_usage_renderers_access_data_safely(self) -> None:
        # Sources and Usage pages must not blow up on missing cursor/grok data
        src = function_body("renderSourcesPage")
        self.assertIn("data.cursor || {}", src)
        self.assertIn("cursorSummary", src)

        usage = function_body("renderUsagePage")
        self.assertIn("selectedOverview(data)", usage)
        self.assertIn("renderLineChart", usage)

    def test_cursor_token_data_surfaces_in_usage_and_sources(self) -> None:
        # Explicitly verify Cursor collector data reaches the UI renderers (the bug being fixed)
        src = APP_JS.read_text(encoding="utf-8")
        overview = function_body("selectedOverview")
        timeline = function_body("mergedTotalDays")
        sources = function_body("renderSourcesPage")
        self.assertIn("overview.cursorTokens || cursorSummary.tokens", overview)
        self.assertIn("(data.cursor || {}).timeline", timeline)
        self.assertIn("Cursor tokens", sources)
        self.assertIn("tokenRecords", sources)
        self.assertNotIn("AI events", src)

    def test_system_toggles_include_cursor_and_all_four(self) -> None:
        html = INDEX_HTML.read_text(encoding="utf-8")
        for system in ("codex", "opencode", "cursor", "grok"):
            self.assertIn(f'data-system-toggle="{system}"', html)

    def test_header_does_not_render_ready_status(self) -> None:
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertNotIn("Ready", html)
        self.assertNotIn("scan-time", html)

    def test_swear_meter_uses_real_codex_and_hermes_data(self) -> None:
        body = function_body("combinedSwearMeter")
        self.assertIn("swearByOrigin", body)
        self.assertIn("hermesMeter", body)
        self.assertIn("swearIndexRate", body)
        self.assertIn("timelineByDay", body)


if __name__ == "__main__":
    unittest.main()
