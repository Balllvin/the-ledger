# Discovery

The monitor should discover local AI usage records without requiring the user to know exact paths. Keep discovery bounded, read-only, and transparent.

## Codex Root Search Order

1. `CODEX_HOME` when set.
2. The current user's `~/.codex`.
3. `.codex` directories under bounded scan roots:
   - user home
   - Desktop
   - Documents
   - Downloads
   - Developer
   - dev
   - code
   - projects
   - source
4. Paths listed in `AI_USAGE_MONITOR_SCAN_ROOTS`.
5. Paths listed in `AI_USAGE_MONITOR_EXTRA_APP_ROOTS`.

The app treats auth files as presence-only metadata. It never displays auth values.

## Codex Files To Recognize

- `auth.json`: present/missing only, always redacted.
- `state_5.sqlite`: primary thread, token, workspace, source, dynamic tool, and spawn-edge records.
- `logs_2.sqlite`: local Codex log counts and warning/error previews.
- `sessions/**/*.jsonl`: active session event streams.
- `archived_sessions/**/*.jsonl`: archived event streams.
- `session_index.jsonl`: count only.
- `generated_images`, `plugins`, `skills`, `automations`, `cache`, `sqlite`: filesystem metadata only.

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

Only scan small text files and known metadata names. Skip:

- `.git`
- `node_modules`
- virtual environments
- `__pycache__`
- cache directories
- files larger than 256 KB for text-marker checks

Do not read or report raw private document contents. Signal counts and paths are enough.

## Environment Overrides

- `CODEX_HOME`: exact Codex root.
- `AI_USAGE_MONITOR_SCAN_ROOTS`: complete bounded roots, replacing the default scan roots.
- `AI_USAGE_MONITOR_EXTRA_APP_ROOTS`: appended roots for extra app discovery.
- `AI_USAGE_MONITOR_LATTICE_ROOT`: exact app root containing `data/lattice.db`.

## Agent Checklist

When adapting to a new laptop:

1. Check whether `CODEX_HOME` is set.
2. Check whether `~/.codex` exists.
3. Search bounded roots for `.codex` directories.
4. Search bounded roots for `state_5.sqlite`, `logs_2.sqlite`, and app databases.
5. Start the app.
6. Open Sources and confirm discovered roots are listed.
7. Open Usage and confirm token timeline is populated when records exist.
