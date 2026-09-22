#!/bin/bash
# Run the Axiom bot from the repository's virtual environment.

set -euo pipefail

# The repo root is one level up from scripts/.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "$ROOT/venv/bin/activate" ]; then
    echo "No virtual environment at $ROOT/venv — run ./scripts/setup_venv.sh first." >&2
    exit 1
fi

# shellcheck source=/dev/null
source "$ROOT/venv/bin/activate"

cd "$ROOT"
exec python bot.py
