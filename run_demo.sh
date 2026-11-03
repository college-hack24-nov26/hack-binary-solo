#!/bin/sh
# One-command demo launcher. Uses .venv if present, else python3. Extra args go to scripts/run_demo.py (e.g. --demo-mode).
cd "$(dirname "$0")" || exit 1
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
exec "$PY" scripts/run_demo.py "$@"
