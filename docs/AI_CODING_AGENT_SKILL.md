# AI Coding Agent Skill: The Ledger

Use this skill when a user wants The Ledger, a local dashboard for Codex usage, Codex auth presence, Codex-linked app records, and related local AI metadata.

## Goal

Make the app run locally on the user's machine and show as much safe usage metadata as possible without exposing secrets or committing private usage records.

## Operating Principles

- Read local records only.
- Never mutate Codex, app databases, logs, sessions, or auth files.
- Never display raw auth values.
- Never upload local usage data.
- Prefer runtime discovery over hardcoded paths.
- Keep scans bounded to user-approved or conventional user folders.

## Install Flow

1. Confirm Python 3.11+ is available.
2. Clone or open the repository.
3. Run tests:

   ```bash
   python -m unittest discover -s tests
   ```

4. Start the app:

   ```bash
   python server.py --host 127.0.0.1 --port 5177
   ```

5. Open `http://127.0.0.1:5177`.

Use `python3` instead of `python` on macOS/Linux when needed.

## Discovery Flow

1. Inspect environment variables:
   - `CODEX_HOME`
   - `THE_LEDGER_SCAN_ROOTS`
   - `THE_LEDGER_EXTRA_APP_ROOTS`
   - `THE_LEDGER_LATTICE_ROOT`
2. Check `~/.codex`.
3. Search bounded roots for `.codex`, `state_5.sqlite`, `logs_2.sqlite`, and `auth.json`.
4. Search bounded roots for app records:
   - `data/lattice.db`
   - `codex_auth`
   - `.codex/auth.json`
   - `CODEX_HOME`
   - `state_5.sqlite`
   - `logs_2.sqlite`
5. Set environment variables only if automatic discovery misses a known location.
6. Reload the dashboard and verify Sources shows discovered roots.

## Collector Rules

When adding a collector:

- Use structured APIs where possible, especially SQLite for databases and JSON parsers for JSON/JSONL.
- Add a source-health section even when detailed parsing is unavailable.
- Redact recursively using `monitor.sanitize`.
- Return empty/missing states instead of raising fatal errors.
- Add focused tests with synthetic data.

## UI Rules

Follow [DESIGN.md](DESIGN.md):

- Three pages only unless the user asks otherwise.
- Keep Usage as the highest-level dashboard.
- Keep Project as one selected workspace.
- Keep Sources as the source-health and local-discovery page.
- Avoid marketing copy and decorative layout.

## Verification

Before handing off:

```bash
python -m unittest discover -s tests
python -m compileall -q server.py monitor
```

Then verify in a browser:

- Usage chart renders.
- Project selector has Codex workspace options when records exist.
- Sources shows Codex root discovery.
- Refresh works.
- Console has no errors.

## Privacy Review

Before committing or publishing:

- Confirm `.gitignore` excludes logs, SQLite files, JSONL files, auth files, caches, and Python bytecode.
- Run `git status --short`.
- Do not stage private runtime records.
- Search for user-specific paths and replace them with generic examples.

## Completion Criteria

The task is complete when the app runs locally, discovers records on the current machine, tests pass, docs explain installation on Windows/macOS/Linux, and the repository contains only reusable source code and instructions.
