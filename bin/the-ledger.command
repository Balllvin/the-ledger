#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
HOST=${THE_LEDGER_HOST:-127.0.0.1}
PORT=${THE_LEDGER_PORT:-5177}
URL="http://${HOST}:${PORT}"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "Python 3.11 or newer is required."
  exit 1
fi

cd "$ROOT"

if command -v open >/dev/null 2>&1; then
  (sleep 1 && open "$URL") >/dev/null 2>&1 &
fi

echo "The Ledger"
echo "Opening ${URL}"
echo "Press Ctrl-C to stop."
exec "$PYTHON_BIN" server.py --host "$HOST" --port "$PORT"
