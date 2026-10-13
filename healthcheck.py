"""
Liveness of the bot, kept as a timestamp in a file.

The bot stamps the file each time Lichess sends a line on the event stream.
A live stream is never silent for more than 7 seconds, because Lichess sends an
empty keep-alive line when it has nothing else to say, so the age of the stamp
is the time since Lichess was last heard from. An idle bot stays healthy; a bot
whose connection has died does not.

Run as a script this is the container's health check: exit status 0 while the
stamp is fresh, 1 when it is stale or missing.
"""

import os
import sys
import time
from typing import Optional

HEARTBEAT_FILE = "/tmp/axiom_heartbeat"

# Seconds the stamp may age before the bot counts as unhealthy. Reopening a
# connection that went silent takes up to about 50 (30 to notice, 10 to wait,
# 10 to connect), so a single reconnect stays inside the limit.
MAX_AGE = 60


def beat(path: Optional[str] = None) -> None:
    """Record that Lichess was heard from just now."""
    path = path or HEARTBEAT_FILE
    scratch = f"{path}.{os.getpid()}"
    try:
        with open(scratch, "w") as f:
            f.write(str(time.time()))
        # Swapped in whole, so a check never reads a half-written stamp.
        os.replace(scratch, path)
    except OSError:
        # Nothing to do about it here: a stamp that cannot be written goes
        # stale, and the health check reports exactly that.
        pass


def clear(path: Optional[str] = None) -> None:
    """Drop the stamp, so a process that lingers after shutdown reads as unhealthy."""
    try:
        os.remove(path or HEARTBEAT_FILE)
    except OSError:
        # Already gone, which is the state being asked for.
        pass


def age(path: Optional[str] = None) -> Optional[float]:
    """Seconds since the last stamp, or None when there is no readable stamp."""
    try:
        with open(path or HEARTBEAT_FILE) as f:
            return time.time() - float(f.read())
    except (OSError, ValueError):
        return None


def is_healthy(path: Optional[str] = None, max_age: float = MAX_AGE) -> bool:
    stamp_age = age(path)
    return stamp_age is not None and stamp_age < max_age


if __name__ == "__main__":
    # An optional argument names another stamp file; the container check uses the default.
    sys.exit(0 if is_healthy(*sys.argv[1:2]) else 1)
