#!/bin/bash
# Install the latest Stockfish from the official GitHub releases to
# /usr/local/bin/stockfish, or update the one that is there.
#
# The work is done by stockfish_updater.py, the same code the bot runs at
# startup when AUTO_UPDATE_STOCKFISH is on: it checks the archive against the
# SHA-256 the release publishes before installing, and asks for sudo if
# /usr/local/bin is not writable.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

exec python3 "$ROOT/stockfish_updater.py"
