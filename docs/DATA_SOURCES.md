# Data Sources

The Ledger is intentionally read-only. It does not mutate Codex, SQLite files, JSONL sessions, logs, exports, or app records.

## Discovery

Collected records:

- Bounded scan roots used for discovery.
- Candidate Codex roots.
- Candidate Codex-linked app roots.
- Signal counts for local folders that reference Codex records.

Discovery reports paths and counts. It does not report raw file contents.

Discovery avoids broad blocking crawls by default. It checks standard local roots, then adds high-signal workspace roots recorded by Codex sessions and state records so linked app and Hermes records can be found from where work actually happened. Set `THE_LEDGER_BROAD_SCAN=1` only when an explicit deep bounded crawl is needed.

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
  - token totals are also grouped by each session's primary model so cost estimates can use model-specific rates
  - direct user messages are inspected locally for the Codex Swear Meter; the browser receives only aggregate message counts, rates, term counters, group/category counters, daily buckets, and per-thread counts, never raw messages or snippets
  - the Codex Swear Meter uses a lightweight candidate-line pass across all discovered session files, including older files that are not fully parsed for token details
  - very large session files are summarized from the file head and tail so the dashboard stays responsive; those rows are marked partial
  - when thousands of historical session files exist, recent files are parsed for full token/session detail and older files still contribute file metadata plus aggregate swear-meter counts; those rows are marked skipped
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
  - model totals include input, output, reasoning, cache read, and cache write token buckets when the Hermes schema provides them
  - recent and top session summaries include source, model, token buckets, billing provider/mode, and local cost fields when present
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
- message token totals grouped by model, used for local cost estimates
- provider and model counts
- todo status counts

OpenCode auth handling:

- `auth.json`, `account`, `control_account`, session share secrets, and secret-like keys are redacted recursively.
- Raw prompt text, message bodies, tool output, session diffs, and logs are not returned to the browser.

## Optional Cursor

Collected from local Cursor roots when present:

- `~/Library/Application Support/Cursor`
  - app root, log directory, process-monitor directory, global storage, and workspace storage presence
- `~/Library/Application Support/Cursor/logs`
  - log file counts, byte totals, and latest file metadata only
- `~/Library/Application Support/Cursor/process-monitor/*.log`
  - JSONL process sample counts, session counts, top process categories, peak CPU and memory summaries
- `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
  - table counts, grouped key counts, `aiCodeTracking.dailyStats` line totals, and `cursorDiskKV` composer token totals from `composerData:*` records
- `~/Library/Application Support/Cursor/User/workspaceStorage/*/state.vscdb`
  - workspace metadata, generation counts, prompt counts, composer counts, and aggregate line-change counters

Cursor auth handling:

- Cursor auth keys are counted by key group only.
- Cursor access tokens, refresh tokens, prompt text, generation text, composer names, and log bodies are not returned to the browser.
- Cursor token totals come from local composer context/prompt token counters. These records expose prompt-side token usage and a daily token timeline, but not a full provider billing split.

## Grok Build

Grok Build (the local TUI/CLI) is the 4th first-class source alongside Codex, OpenCode, and Cursor.

Default root: `~/.grok` (or `GROK_HOME` when set).

Collected records:

- `grok.db` (primary structured source)
  - `workspaces`, `sessions` (title, model, cwd, status, timestamps)
  - `usage_events` (per-event input/output/total_tokens, cost_micros, model, source)
  - Token totals, per-model and per-source aggregates, recent/top sessions with metadata
- `sessions/<encoded-cwd>/<session-id>/`
  - Filesystem metadata only (summary.json, events.jsonl, chat_history.jsonl, terminal/ logs, etc.)
  - No raw prompt text or full event bodies are returned
- `auth.json` — presence only, always redacted
- `config.toml`, `user-settings.json`, `logs/unified.jsonl` — key names and file metadata only

Grok auth handling:
- `auth.json` and secret-like keys are redacted recursively.
- Raw chat content, tool arguments/results, and full JSONL bodies are never returned.

## Known Limits

- Cost cards are estimates built on the server from local token totals and public, non-discounted provider API prices. The browser displays the server estimate; it does not carry a separate pricing table.
- Codex billing uses the complete `state_5.sqlite` thread token ledger when it is available. Codex state records expose total tokens by model, but not input/output/cache buckets, so the billing estimator allocates those complete totals using model-specific bucket ratios from parsed Codex JSONL sessions when possible and the blended parsed Codex ratio otherwise. These rows are marked as bucket-estimated.
- Unknown or missing model IDs are not fallback-priced. They remain in token totals and are reported as unpriced until a public API price can be matched.
- Cursor exposes local composer prompt/context token counters, but not a complete provider billing ledger with input/output/cache pricing buckets. Cursor contributes token totals to usage charts and remains excluded from cost estimates until a billing-grade split is available.
- If Codex changes its JSONL or SQLite schema, the monitor still returns table counts and source health, but some detailed sections may become empty until parser mappings are updated.
- If OpenCode changes its SQLite JSON payload shape, the monitor still returns source/file health and table counts, but token detail may become empty until parser mappings are updated.
- Optional app, OpenCode, Cursor, and Hermes data may be missing on most machines. Missing optional sources should not block Codex visibility.
