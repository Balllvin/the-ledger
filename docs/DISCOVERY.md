# Discovery

The Ledger should discover local AI usage records without requiring the user to know exact paths. Keep discovery bounded, read-only, and transparent.

## Codex Root Search Order

1. `CODEX_HOME` when set.
2. The current user's `~/.codex`.
3. `.codex` directories under bounded scan roots:
   - Desktop
   - Documents
   - Downloads
   - Developer
   - dev
   - code
   - projects
   - source
4. Paths listed in `THE_LEDGER_SCAN_ROOTS`.
5. Paths listed in `THE_LEDGER_EXTRA_APP_ROOTS`.

The app treats auth files as presence-only metadata. It never displays auth values.

## Codex Files To Recognize

- `auth.json`: present/missing only, always redacted.
- `state_5.sqlite`: primary thread, token, workspace, source, dynamic tool, and spawn-edge records.
- `logs_2.sqlite`: local Codex log counts and warning/error previews.
- `sessions/**/*.jsonl`: active session event streams.
- `archived_sessions/**/*.jsonl`: archived event streams.
- `session_index.jsonl`: count only.
- `generated_images`, `plugins`, `skills`, `automations`, `cache`, `sqlite`: filesystem metadata only.
- `sqlite/codex-dev.db`: local Codex app automation/inbox metadata when present.
- Desktop app support directories such as `~/Library/Application Support/Codex`, `%APPDATA%\Codex`, and `~/.config/Codex`: filesystem metadata only.

## Hermes And Local Agent Search

Hermes roots are discovered from:

- `THE_LEDGER_HERMES_ROOTS`
- `~/.hermes`
- `~/.local/state/hermes`
- bounded scan roots that contain Hermes state markers such as `state.db`, `auth.json`, `gateway_state.json`, or a `sessions` directory

Hermes auth files are presence-only metadata. The Ledger reads Hermes SQLite databases read-only and summarizes tokens, sessions, messages, task status counts, and file metadata.

## OpenCode Search

OpenCode roots are discovered from:

- `~/.opencode`
- `~/.config/opencode`
- `~/.local/share/opencode`
- `~/Library/Application Support/ai.opencode.desktop`
- project-local `.git/opencode` folders under bounded scan roots

OpenCode auth files are presence-only metadata. The monitor reads `~/.local/share/opencode/opencode.db` read-only and summarizes sessions, workspaces, message token totals, models, providers, todos, CLI logs, desktop app logs, and desktop app metadata.

## Codex-Linked App Search

For each bounded scan root, identify likely app roots by looking for:

- `.codex`
- `CODEX_HOME`
- `codex_auth`
- `state_5.sqlite`
- `logs_2.sqlite`
- `lattice.db`
- `data/lattice.db`
- references to `.codex/auth.json`

By default, discovery uses known metadata names and avoids opening arbitrary project text files. Set `THE_LEDGER_DEEP_TEXT_SCAN=1` to also scan small text files for marker strings. Skip:

- `.git`
- `node_modules`
- virtual environments
- `__pycache__`
- cache directories
- files larger than 256 KB for text-marker checks

Do not read or report raw private document contents. Signal counts and paths are enough.

## Environment Overrides

- `CODEX_HOME`: exact Codex root.
- `THE_LEDGER_SCAN_ROOTS`: complete bounded roots, replacing the default scan roots.
- `THE_LEDGER_EXTRA_APP_ROOTS`: appended roots for extra app discovery.
- `THE_LEDGER_LATTICE_ROOT`: exact app root containing `data/lattice.db`.
- `THE_LEDGER_HERMES_ROOTS`: exact Hermes root paths to include.
- `THE_LEDGER_DEEP_TEXT_SCAN`: set to `1` to scan small text files for Codex marker strings.


## Grok Build Search

Grok Build roots are discovered from:

- `GROK_HOME` (exact root, highest priority)
- `~/.grok`
- Bounded scan roots that contain `grok.db`, a `sessions/` directory, or `auth.json` at the expected depth

Grok auth files are presence-only metadata. The collector reads `grok.db` read-only and returns session counts, token/cost aggregates (from `usage_events`), model breakdowns, workspace counts, and recent thread metadata. Raw chat history and full event streams are never returned.

## Grok Files To Recognize

- `grok.db`: primary sessions + usage_events ledger
- `sessions/`: per-workspace thread directories (summary.json, events.jsonl, chat_history.jsonl, signals.json, terminal/ logs)
- `auth.json`: present/missing only, always redacted
- `config.toml`, `user-settings.json`: key names + metadata only
- `logs/unified.jsonl`: file metadata only

Environment override: `GROK_HOME`

## Agent Checklist

When adapting to a new laptop:

1. Check whether `CODEX_HOME` is set.
2. Check whether `~/.codex` exists.
3. Search bounded roots for `.codex` directories.
4. Search bounded roots for `state_5.sqlite`, `logs_2.sqlite`, and app databases.
5. Start the app.
6. Open Sources and confirm discovered roots are listed.
7. Open Usage and confirm token timeline is populated when records exist.
