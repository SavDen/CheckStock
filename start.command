#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN=python3.12
  elif [ -x /opt/homebrew/bin/python3.12 ]; then
    PYTHON_BIN=/opt/homebrew/bin/python3.12
  elif [ -x /usr/local/bin/python3.12 ]; then
    PYTHON_BIN=/usr/local/bin/python3.12
  else
    PYTHON_BIN=python3
  fi
  "$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3,12), "Нужен Python 3.12 или новее"'
  "$PYTHON_BIN" -m venv .venv
fi
if ! .venv/bin/python -c 'import fastapi, psycopg, alembic' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python scripts/local.py
