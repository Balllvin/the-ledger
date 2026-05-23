# The Ledger

Read-only local ledger for Codex usage records and nearby AI application metadata.

The app runs on the user's laptop, scans local records at runtime, and does not ship with any usage data. Secrets are redacted before responses reach the browser.

## Open

Use one command:

```bash
bin/ledger
```

It starts the local server when needed, reuses it when already running, applies the standard bounded scan roots, and prints the URL:

```text
http://127.0.0.1:5177/
```

macOS users can also double-click:

```text
bin/the-ledger.command
```

When starting a new server, `bin/ledger` stays in the foreground. In Codex, run it as a long-running terminal session, then open the URL. In a normal terminal where you want it detached, run `THE_LEDGER_BACKGROUND=1 bin/ledger`.

The browser loads immediately when a cached aggregate snapshot exists, then refreshes local records in the background. The cache stays local in `.ledger-cache/` and is ignored by git.

## What It Reads

- Codex roots such as `~/.codex` or `CODEX_HOME`
- Codex SQLite state and log databases when present
- Codex JSONL sessions and archived sessions
- Codex Swear Meter counts from direct user messages, returned as aggregate rates and term counters only
- Codex desktop app metadata and local automation database when present
- OpenCode CLI, app, SQLite session database, logs, prompt history, and auth presence when present
- Codex-linked local app folders discovered from bounded user-home scans
- Optional app databases such as `data/lattice.db` when present
- Local Hermes/Codex-agent roots bundled into Codex totals when available

## AI Agent Prompt

In a new thread, this is enough:

```text
Open The Ledger.
```

The expected action is:

```bash
cd /path/to/the-ledger
bin/ledger
```

Then open the printed URL in the browser.

## Test

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -S -m unittest discover -s tests -v
```

## Configuration

All configuration is optional.

- `CODEX_HOME`: explicit Codex root to scan.
- `THE_LEDGER_SCAN_ROOTS`: path-list of roots to scan for `.codex` folders and Codex-linked app records.
- `THE_LEDGER_EXTRA_APP_ROOTS`: additional roots to include in discovery.
- `THE_LEDGER_LATTICE_ROOT`: explicit app root containing `data/lattice.db`.
- `THE_LEDGER_HERMES_ROOTS`: explicit Hermes/Codex-agent runtime roots to include.
- `THE_LEDGER_BACKGROUND_REFRESH_SECONDS`: cached snapshot age before background refresh; default is `300`.
- `THE_LEDGER_DEEP_TEXT_SCAN`: set to `1` to also scan small project text files for marker strings.
- `THE_LEDGER_TIMEZONE`: IANA timezone label used by daily rundown commands when `--timezone` is not provided.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token used only by `server.py --send-telegram`.
- `TELEGRAM_CHAT_ID`: Telegram chat target used only by `server.py --send-telegram`.

Path lists use the operating system separator: `;` on Windows and `:` on macOS/Linux.

## Daily Rundown

Print a privacy-safe local message:

```bash
python3 -S server.py --daily-rundown --day YYYY-MM-DD --timezone Europe/Zurich
```

Send the same message through a Telegram bot:

```bash
TELEGRAM_BOT_TOKEN="..." TELEGRAM_CHAT_ID="..." python3 -S server.py --send-telegram --timezone Europe/Zurich
```

The Telegram token and chat ID are read from the environment only. They are not returned by the API, written to the cache, or printed by error messages.

## Agent Docs

Start with [AGENTS.md](AGENTS.md). It links the detailed install, discovery, design, and publishing instructions for AI coding agents adapting this app to a new machine.
