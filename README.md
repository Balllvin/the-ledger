# The Ledger

Read-only local ledger for Codex usage records and nearby AI application metadata.

The app runs on the user's laptop, scans local records at runtime, and does not ship with any usage data. Secrets are redacted before responses reach the browser.

## What It Reads

- Codex roots such as `~/.codex` or `CODEX_HOME`
- Codex SQLite state and log databases when present
- Codex JSONL sessions and archived sessions
- Codex Swear Meter counts from direct user messages, returned as aggregate rates and term counters only
- Codex desktop app metadata and local automation database when present
- OpenCode CLI, app, SQLite session database, logs, prompt history, and auth presence when present
- Codex-linked local app folders discovered from bounded user-home scans
- Optional app databases such as `data/lattice.db` when present
- Optional local and WSL Hermes metadata when available

## Run

macOS users can double-click:

```text
bin/the-ledger.command
```

Or run it directly from a terminal on any platform:

```bash
python server.py --host 127.0.0.1 --port 5177
```

Open [http://127.0.0.1:5177](http://127.0.0.1:5177).

## AI Agent Install Prompt

Give this prompt to an AI coding agent on a new machine:

```text
Clone https://github.com/Balllvin/the-ledger, run the tests, start the local server, open The Ledger, and follow docs/DISCOVERY.md until Codex, OpenCode, and any local app records are discovered. Keep everything read-only and never upload usage data or secrets.
```

## Test

```bash
python -m unittest discover -s tests
```

## Configuration

All configuration is optional.

- `CODEX_HOME`: explicit Codex root to scan.
- `THE_LEDGER_SCAN_ROOTS`: path-list of roots to scan for `.codex` folders and Codex-linked app records.
- `THE_LEDGER_EXTRA_APP_ROOTS`: additional roots to include in discovery.
- `THE_LEDGER_LATTICE_ROOT`: explicit app root containing `data/lattice.db`.
- `THE_LEDGER_HERMES_ROOTS`: explicit Hermes runtime roots to include.
- `THE_LEDGER_DEEP_TEXT_SCAN`: set to `1` to also scan small project text files for marker strings.


Path lists use the operating system separator: `;` on Windows and `:` on macOS/Linux.

## Agent Docs

Start with [AGENTS.md](AGENTS.md). It links the detailed install, discovery, design, and publishing instructions for AI coding agents adapting this app to a new machine.
