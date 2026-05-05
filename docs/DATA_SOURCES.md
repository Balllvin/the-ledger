# Data Sources

The Ledger is intentionally read-only. It does not mutate Codex, SQLite files, JSONL sessions, logs, exports, or app records.

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
  - very large session files are summarized from the file head and tail so the dashboard stays responsive; those rows are marked partial
  - when thousands of historical session files exist, recent files are parsed and older files remain counted as file metadata; those rows are marked skipped
- `archived_sessions/**/*.jsonl`
  - same parser as active sessions
- `logs_2.sqlite`
  - total row count from the full table
  - level, target, recent warning/error previews, and hourly counts from a bounded recent-row sample so large local log databases stay responsive
- Filesystem metadata
  - generated images, plugins, skills, automations, cache, model cache, session index
- `sqlite/codex-dev.db`
  - automation counts, run counts, run status totals, unread inbox item count
- Desktop app support directory, when present
  - app preferences presence, local server registry presence, cache/session/blob/crashpad file metadata

Auth handling:

- `auth.json` is reported as present/missing only.
- Secret-like keys and values are redacted recursively.

## Optional App Database

Default candidate: a discovered app root with `data/lattice.db`

Override: `THE_LEDGER_LATTICE_ROOT`

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

Collected from local Hermes roots when present:

- `~/.hermes`, `~/.local/state/hermes`, roots listed in `THE_LEDGER_HERMES_ROOTS`, and bounded app folders with Hermes state markers
- `auth.json` and `auth.lock` presence only
- user Codex `~/.codex/auth.json` presence only, for Hermes/Codex auth coverage
- `state.db`
  - session counts, token totals, model/source totals, recent and top session metadata
  - message counts, message token totals, role totals, tool-name counts
- `kanban.db`
  - task and run status totals
- `sessions/*.json` and `sessions/*.jsonl`
  - file counts, suffix counts, latest file metadata
- `config.yaml`, `channel_directory.json`, `gateway_state.json`, and `processes.json`
  - key names and file metadata only

Collected through WSL with `wsl python3 -c ...` when available:

- `~/.hermes` root metadata
- `~/.hermes/config.yaml`, `~/.hermes/channel_directory.json`, `~/.hermes/gateway_state.json`
- `~/.hermes/.env` key names only, values redacted
- `~/.hermes/hermes-agent` repo presence, branch, and short commit when Git is available
- `~/.hermes/cron/output` file metadata
- WSL-side `~/.codex/auth.json` presence only

The Hermes scan skips `.git`, `node_modules`, `__pycache__`, common test caches, and large nested inspection checkouts for file counts.

## OpenCode

Collected from local OpenCode roots when present:

- `~/.opencode`
  - CLI install metadata and binary presence
- `~/.config/opencode`
  - config package metadata
- `~/.local/share/opencode`
  - `auth.json` presence only, always redacted
  - `opencode.db` read-only SQLite summaries
  - CLI log file metadata from `log/*.log`
  - session diff and tool-output file metadata
- `~/Library/Application Support/ai.opencode.desktop`
  - desktop app settings/global/default key summaries
  - model settings key summaries
  - prompt history JSONL line counts and mode counts, not prompt text
  - workspace `.dat` file metadata
- `~/Library/Logs/ai.opencode.desktop`
  - desktop app log file metadata

SQLite records collected from `opencode.db`:

- table counts
- sessions by workspace with title, directory, version, timestamps, token totals, message counts, tool counts, and cost totals
- message token totals from assistant message payloads: total, input, output, reasoning, cache reads, cache writes
- provider and model counts
- todo status counts

OpenCode auth handling:

- `auth.json`, `account`, `control_account`, session share secrets, and secret-like keys are redacted recursively.
- Raw prompt text, message bodies, tool output, session diffs, and logs are not returned to the browser.

## Known Limits

- Local records expose tokens, not billing prices. The dashboard does not estimate cost.
- If Codex changes its JSONL or SQLite schema, the monitor still returns table counts and source health, but some detailed sections may become empty until parser mappings are updated.
- If OpenCode changes its SQLite JSON payload shape, the monitor still returns source/file health and table counts, but token detail may become empty until parser mappings are updated.
- Optional app, OpenCode, and Hermes data may be missing on most machines. Missing optional sources should not block Codex visibility.
