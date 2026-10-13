#!/bin/bash
# Create the repository's virtual environment and install what the bot and
# its tests need.

set -euo pipefail

# The repo root is one level up from scripts/, wherever this is run from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -d "$ROOT/venv" ]; then
    python3 -m venv "$ROOT/venv"
fi

"$ROOT/venv/bin/python" -m pip install --upgrade pip
"$ROOT/venv/bin/python" -m pip install -r "$ROOT/requirements-dev.txt"

echo "Virtual environment ready in $ROOT/venv"
echo "To activate: source venv/bin/activate"
echo "To run the bot: ./scripts/run_bot.sh"
