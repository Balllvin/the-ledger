# Design

The Ledger should feel like a local ledger, not a product landing page.

## Structure

- Sticky header with app name, page tabs, scan status, and refresh.
- Three pages:
  - Usage: total and per-workspace usage over time.
  - Project: one selected workspace with chart, metrics, top runs, and recent threads.
  - Sources: discovered local roots, source health, optional app records, and stored metadata.
- No marketing hero.
- No nested cards.
- No decorative gradients or background blobs.

## Visual System

- Light mode.
- Warm monochrome base.
- Border-only panels.
- Compact rows.
- Tabular numeric display.
- Muted semantic colors only for status tags.

## Interaction Rules

- Header tabs switch pages without navigation.
- Usage legend checkboxes choose visible chart lines.
- Project dropdown chooses the active Codex workspace.
- Refresh re-scans local records.
- Missing sources should show readable empty states, not errors that block the full dashboard.

## Accessibility

- Keep native controls where possible.
- Preserve keyboard focus states.
- Make tables horizontally scrollable on small screens.
- Avoid tiny click targets.
- Do not rely on color alone for status.
