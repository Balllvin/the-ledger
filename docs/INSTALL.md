# Install

The app is a standard-library Python web server. It does not require npm, a database server, Docker, or cloud credentials.

## Prerequisites

- Python 3.11 or newer
- Git, only if cloning or publishing the repository
- A local Codex installation, if the user wants real usage records

## Windows

```powershell
git clone https://github.com/<owner>/the-ledger.git
cd the-ledger
python -m unittest discover -s tests
python server.py --host 127.0.0.1 --port 5177
```

Open `http://127.0.0.1:5177`.

Optional explicit Codex root:

```powershell
$env:CODEX_HOME="$env:USERPROFILE\.codex"
python server.py --host 127.0.0.1 --port 5177
```

Optional bounded discovery roots:

```powershell
$env:THE_LEDGER_SCAN_ROOTS="$env:USERPROFILE\Desktop;$env:USERPROFILE\Documents"
python server.py --host 127.0.0.1 --port 5177
```

## macOS

Double-click from Finder:

```text
bin/the-ledger.command
```

Or run from Terminal:

```bash
git clone https://github.com/<owner>/the-ledger.git
cd the-ledger
python3 -m unittest discover -s tests
python3 server.py --host 127.0.0.1 --port 5177
```

Optional explicit Codex root:

```bash
CODEX_HOME="$HOME/.codex" python3 server.py --host 127.0.0.1 --port 5177
```

Optional bounded discovery roots:

```bash
THE_LEDGER_SCAN_ROOTS="$HOME/Projects:$HOME/Documents" python3 server.py --host 127.0.0.1 --port 5177
```

## Linux

```bash
git clone https://github.com/<owner>/the-ledger.git
cd the-ledger
python3 -m unittest discover -s tests
python3 server.py --host 127.0.0.1 --port 5177
```

Optional explicit Codex root:

```bash
CODEX_HOME="$HOME/.codex" python3 server.py --host 127.0.0.1 --port 5177
```

## Troubleshooting

- If the dashboard loads but has no records, follow [DISCOVERY.md](DISCOVERY.md).
- If port `5177` is busy, use another port: `python server.py --port 5180`.
- If WSL/Hermes scanning fails on Windows, it is non-blocking. Codex and app records should still load.
