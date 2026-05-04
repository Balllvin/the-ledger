# AI Usage Monitor

Read-only local dashboard for Codex usage records and nearby AI application metadata.

The app runs on the user's laptop, scans local records at runtime, and does not ship with any usage data. Secrets are redacted before responses reach the browser.

## What It Reads

- Codex roots such as `~/.codex` or `CODEX_HOME`
- Codex SQLite state and log databases when present
- Codex JSONL sessions and archived sessions
- Codex-linked local app folders discovered from bounded user-home scans
- Optional app databases such as `data/lattice.db` when present
- Optional WSL Hermes metadata when available

## Run

```bash
python server.py --host 127.0.0.1 --port 5177
```

Open [http://127.0.0.1:5177](http://127.0.0.1:5177).

## Test

```bash
python -m unittest discover -s tests
```

## Configuration

All configuration is optional.

- `CODEX_HOME`: explicit Codex root to scan.
- `AI_USAGE_MONITOR_SCAN_ROOTS`: path-list of roots to scan for `.codex` folders and Codex-linked app records.
- `AI_USAGE_MONITOR_EXTRA_APP_ROOTS`: additional roots to include in discovery.
- `AI_USAGE_MONITOR_LATTICE_ROOT`: explicit app root containing `data/lattice.db`.

Path lists use the operating system separator: `;` on Windows and `:` on macOS/Linux.

## Agent Docs

Start with [AGENTS.md](AGENTS.md). It links the detailed install, discovery, design, and publishing instructions for AI coding agents adapting this app to a new machine.
