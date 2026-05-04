# Data Sources

The monitor is intentionally read-only. It does not mutate Codex, SQLite files, JSONL sessions, logs, exports, or app records.

## Discovery

Collected records:

- Bounded scan roots used for discovery.
- Candidate Codex roots.
- Candidate Codex-linked app roots.
- Signal counts for local folders that reference Codex records.

Discovery reports paths and counts. It does not report raw file contents.

## Codex

Default root: `~/.codex`

Override: `CODEX_HOME`

Collected records:

- `state_5.sqlite`
  - `threads`: title, source, model provider, cwd, timestamps, archived state, `tokens_used`
  - `thread_dynamic_tools`: tool availability counts
  - `thread_spawn_edges`: subagent edge counts
  - table counts for the rest of the state database
- `sessions/**/*.jsonl`
  - session metadata, turn context, model mentions, token count events, tool calls, command exits, image/search events
  - token totals use the latest cumulative `total_token_usage` per session file
- `archived_sessions/**/*.jsonl`
  - same parser as active sessions
- `logs_2.sqlite`
  - log counts by level, target, recent warning/error previews
- Filesystem metadata
  - generated images, plugins, skills, automations, cache, model cache, session index

Auth handling:

- `auth.json` is reported as present/missing only.
- Secret-like keys and values are redacted recursively.

## Optional App Database

Default candidate: a discovered app root with `data/lattice.db`

Override: `AI_USAGE_MONITOR_LATTICE_ROOT`

Collected records when present:

- `data/lattice.db`
  - AI pipeline totals from `document_pipeline_results`
  - review suggestion totals from `document_ai_review_suggestions`
  - core table counts for documents, pages, page regions, document rows, and template rows
  - parsed AI payload shape counts for known AI pipeline payloads
- Filesystem metadata
  - root logs and recent data artifacts
- Project notes
  - selected documentation file presence and modification metadata

## Optional Hermes

Collected through WSL with `wsl python3 -c ...` when available:

- `~/.hermes` root metadata
- `~/.hermes/config.yaml`, `~/.hermes/channel_directory.json`, `~/.hermes/gateway_state.json`
- `~/.hermes/.env` key names only, values redacted
- `~/.hermes/hermes-agent` repo presence, branch, and short commit when Git is available
- `~/.hermes/cron/output` file metadata
- WSL-side `~/.codex/auth.json` presence only

The Hermes scan skips `.git`, `node_modules`, and `__pycache__` for file counts.

## Known Limits

- Local records expose tokens, not billing prices. The dashboard does not estimate cost.
- If Codex changes its JSONL or SQLite schema, the monitor still returns table counts and source health, but some detailed sections may become empty until parser mappings are updated.
- Optional app and WSL/Hermes data may be missing on most machines. Missing optional sources should not block Codex visibility.
