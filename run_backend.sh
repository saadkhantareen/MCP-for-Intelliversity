#!/usr/bin/env bash
# Start the Intelliversity Django backend.
#
# Why this script exists:
#   This project lives on an NTFS mount (/mnt/data), which cannot store
#   symlinks, so neither `uv sync` nor `python -m venv` can create `.venv/`
#   inside the project (both fail with "No such file or directory" while
#   symlinking python). The virtualenv therefore lives on the home drive and
#   is reused by this script.
#
# Usage:
#   ./run_backend.sh                 # 0.0.0.0:8000
#   ./run_backend.sh 127.0.0.1:8000  # custom address
#   VENV=/path/to/venv ./run_backend.sh
set -euo pipefail

VENV="${INTELLIVERSITY_VENV:-$HOME/.venvs/intelliversity}"
ADDR="${1:-0.0.0.0:8000}"

cd "$(dirname "$0")"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Virtualenv not found at $VENV" >&2
  echo "Create it with:  uv venv $VENV --python 3.12.3 && VIRTUAL_ENV=$VENV uv sync --active" >&2
  exit 1
fi

exec "$VENV/bin/python" manage.py runserver "$ADDR" --noreload
