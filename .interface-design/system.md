# Interface Design System

## Direction

Personality: Precision archive console
Foundation: Warm monochrome with sparse semantic pastels
Depth: Borders-only

This is a local monitoring surface for a power user checking AI activity, token volume, source health, and pipeline records. It should feel like a clean ledger: dense enough to scan, calm enough to keep open, and explicit about where every number came from.

## Tokens

### Spacing

Base: 4px

Scale: 4, 8, 12, 16, 18, 24, 28, 32, 48

### Colors

- Canvas: `#f7f6f3`
- Surface: `#ffffff`
- Soft surface: `#fbfbfa`
- Ink: `#151515`
- Secondary ink: `#3b3a36`
- Muted ink: `#76736d`
- Border: `#e6e2da`
- Strong border: `#d5d0c7`
- Blue wash: `#e1f3fe`, blue ink `#1f6c9f`
- Green wash: `#edf3ec`, green ink `#346538`
- Yellow wash: `#fbf3db`, yellow ink `#956400`
- Red wash: `#fdebec`, red ink `#9f2f2d`

### Radius

- Panels and metric cards: 8px
- Controls and rows: 6px
- Tags: 999px

### Typography

- UI: `Manrope`, then SF/system sans fallbacks
- Data: `IBM Plex Mono`, then SF Mono/Consolas fallbacks
- Numbers use tabular rendering where supported

## Patterns

- One sticky header with scan status and refresh action
- Three header-switched pages: Usage, Project, Sources
- Metric row for the current page's key totals
- Multi-line usage chart as the primary signature component
- Checkbox legend controls visible chart lines
- Project selector uses stored Codex thread `cwd` records and keeps the page focused on one active workspace
- Border-only panels, no shadows, no decorative gradients
- Dense tables only where detail is useful, mostly on the Project page
- Compact rank rows for selected project runs and source paths
- Status tags use muted pastels only for semantic meaning

## Decisions

- Costs are omitted because local records store token usage, not stable billing rates.
- Auth files are represented as redacted source metadata, never as raw values.
- Hermes is optional and isolated behind the WSL metadata collector so a WSL failure cannot break Codex/Lattice visibility.
