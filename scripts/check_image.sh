#!/bin/bash
# Check a built image the way it is meant to run: as its unprivileged user, on
# a read-only root filesystem, with every capability dropped. Each check is
# something the image promises, tried from inside a container.
#
# Usage: scripts/check_image.sh <image>

set -euo pipefail

IMAGE="${1:?usage: check_image.sh <image>}"

# The options docker-compose.yml runs the bot with.
HARDENED=(--rm --read-only --tmpfs /tmp:size=1m,noexec,nosuid,nodev
          --cap-drop ALL --security-opt no-new-privileges --pids-limit 128)

pass() { echo "ok    $1"; }
fail() { echo "FAIL  $1" >&2; exit 1; }

# Run a Python snippet in the image under the hardened options.
inside() { docker run "${HARDENED[@]}" "${@:2}" --entrypoint python3 "$IMAGE" -c "$1"; }

# ── What must not be there ────────────────────────────────────────────────────

for tool in sh bash; do
    if docker run --rm --entrypoint "$tool" "$IMAGE" -c true >/dev/null 2>&1; then
        fail "the image has a shell ($tool)"
    fi
done
pass "no shell to start"

inside '
import importlib.util, os, shutil, sys

tools = ["sh", "bash", "apt", "apt-get", "dpkg", "pip", "pip3", "curl", "wget", "tar", "su", "sudo"]
found = [t for t in tools if shutil.which(t)]
assert not found, f"tools present: {found}"

modules = [m for m in ("pip", "pytest", "stockfish_updater") if importlib.util.find_spec(m)]
assert not modules, f"modules present: {modules}"

# The standard library can normally bootstrap pip; here it has nothing to do it with.
import subprocess
bootstrap = subprocess.run([sys.executable, "-m", "ensurepip", "--user"], capture_output=True)
assert bootstrap.returncode != 0 and importlib.util.find_spec("pip") is None, "pip can be bootstrapped"

leftovers = sorted(set(os.listdir("/app")) - {"bot.py", "config.py", "healthcheck.py", "logging_config.py", "deps", "logs"})
assert not leftovers, f"unexpected files in /app: {leftovers}"
' && pass "no package manager, no download tool, no test code, nothing but the bot in /app"

# ── Who it runs as and what it can write ──────────────────────────────────────

inside '
import os

assert os.getuid() == 65532 and os.getgid() == 65532, f"runs as {os.getuid()}:{os.getgid()}"

status = dict(line.split(":\t", 1) for line in open("/proc/self/status").read().splitlines() if ":\t" in line)
assert int(status["CapEff"], 16) == 0 and int(status["CapBnd"], 16) == 0, "capabilities are left"
assert status["NoNewPrivs"].strip() == "1", "privileges can still be gained"

def writable(path):
    try:
        with open(path, "w") as f:
            f.write("x")
        os.remove(path)
        return True
    except OSError:
        return False

for path in ("/app/bot.py.new", "/app/deps/x", "/usr/local/bin/x", "/etc/x", "/home/nonroot/x"):
    assert not writable(path), f"{path} is writable"
assert writable("/tmp/x"), "/tmp is not writable"
assert writable("/app/logs/x"), "/app/logs is not writable"
' --tmpfs /app/logs:size=1m,uid=65532,gid=65532 && pass "unprivileged, no capabilities, writes only to /tmp and /app/logs"

# Without the read-only flag the files still belong to root.
docker run --rm --entrypoint python3 "$IMAGE" -c '
import os
for path in ("/app/bot.py", "/app/config.py", "/app/deps", "/usr/local/bin/stockfish"):
    assert os.stat(path).st_uid == 0, f"{path} is not owned by root"
    assert not os.access(path, os.W_OK), f"{path} is writable by the bot"
assert os.stat("/app/logs").st_uid == 65532
' && pass "code and engine are owned by root, the log directory by the bot"

# ── What must work ────────────────────────────────────────────────────────────

inside '
import chess
from stockfish import Stockfish

engine = Stockfish("/usr/local/bin/stockfish", parameters={"Threads": 1, "Hash": 16})
move = engine.get_best_move_time(300)
assert chess.Move.from_uci(move) in chess.Board().legal_moves, move
print("      the engine played", move)
' && pass "the engine starts and finds a move under the hardened options"

inside '
import subprocess, sys
import healthcheck

check = lambda: subprocess.run([sys.executable, "/app/healthcheck.py"]).returncode
assert check() == 1, "healthy without a heartbeat"
healthcheck.beat()
assert check() == 0, "unhealthy right after a heartbeat"
' && pass "the health check fails without a heartbeat and passes with one"

docker inspect --format '{{json .Config.Healthcheck.Test}}' "$IMAGE" | grep -q 'healthcheck.py' \
    && pass "the image declares the health check" || fail "the image declares no health check"

# The bot itself, with a token Lichess does not know: it has to get as far as
# asking Lichess over TLS and stop on the refusal, not on anything of its own.
set +e
output=$(docker run "${HARDENED[@]}" --tmpfs /app/logs:size=1m,uid=65532,gid=65532 \
         -e TOKEN=lip_not_a_real_token "$IMAGE" 2>&1)
status=$?
set -e
echo "$output" | sed 's/^/      /' | tail -4
[ "$status" -ne 0 ] || fail "the bot exited cleanly with a token Lichess cannot know"
echo "$output" | grep -q "HTTP 401" || fail "the bot did not reach Lichess and get refused (expected HTTP 401)"
pass "the bot starts, reaches Lichess over TLS and stops on the refused token"

echo "All image checks passed for $IMAGE"
