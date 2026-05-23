# Install

The app is a standard-library Python web server. It does not require npm, a database server, Docker, cloud credentials, or third-party Python packages.

## Fast Path

From the repository root:

```bash
bin/ledger
```

Then open the printed URL:

```text
http://127.0.0.1:5177/
```

`bin/ledger` does all of the routine setup:

- Chooses `python3` when available.
- Runs Python with `-S` and `PYTHONDONTWRITEBYTECODE=1` for faster, cleaner startup.
- Reuses an existing healthy server on port `5177`.
- Starts the server in the foreground when it is not already running, which is the reliable mode for Codex and terminal agents.
- Applies the standard bounded scan roots: Desktop, `~/.codex`, `~/.hermes`, and `~/.local/state/hermes`.

For a detached shell process outside Codex, use:

```bash
THE_LEDGER_BACKGROUND=1 bin/ledger
```

Detached server logs go to `tmp/the-ledger-server.log`.

## Prerequisites

- Python 3.11 or newer
- A local Codex installation, if the user wants real usage records

## macOS

Double-click from Finder:

```text
bin/the-ledger.command
```

Or run from Terminal:

```bash
bin/ledger
```

## Windows

Use Python directly:

```powershell
python -S server.py --host 127.0.0.1 --port 5177
```

Open `http://127.0.0.1:5177/`.

Optional explicit roots:

```powershell
$env:CODEX_HOME="$env:USERPROFILE\.codex"
$env:THE_LEDGER_SCAN_ROOTS="$env:USERPROFILE\Desktop;$env:USERPROFILE\.codex;$env:USERPROFILE\.hermes"
python -S server.py --host 127.0.0.1 --port 5177
```

## Linux

```bash
bin/ledger
```

Optional explicit roots:

```bash
CODEX_HOME="$HOME/.codex" THE_LEDGER_SCAN_ROOTS="$HOME/Desktop:$HOME/.codex:$HOME/.hermes" bin/ledger
```

## Cache

The server stores the last aggregate snapshot in `.ledger-cache/snapshot.json`. This makes future opens immediate, then the server refreshes records in the background. The cache is local-only and ignored by git.

Use the dashboard Refresh button when you want a forced rescan.

## Test

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -S -m unittest discover -s tests -v
```

## Daily Telegram Rundown

Print the local daily rundown without sending anything:

```bash
python3 -S server.py --daily-rundown --day YYYY-MM-DD --timezone Europe/Zurich
```

Send through a Telegram bot:

```bash
TELEGRAM_BOT_TOKEN="..." TELEGRAM_CHAT_ID="..." python3 -S server.py --send-telegram --timezone Europe/Zurich
```

The bot token and chat ID are read from environment variables only.

## Troubleshooting

- If the dashboard loads but has no records, follow [DISCOVERY.md](DISCOVERY.md).
- If port `5177` is busy, set `THE_LEDGER_PORT`: `THE_LEDGER_PORT=5180 bin/ledger`.
- If startup fails, read `tmp/the-ledger-server.log`.
- If WSL/Hermes scanning fails on Windows, it is non-blocking. Codex and OpenCode records should still load.
