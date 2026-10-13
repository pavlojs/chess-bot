"""
A local stand-in for Lichess, for the scenario tests.

It serves scripted streams and canned replies over a real socket, so the bot's
own HTTP stack (requests, urllib3, berserk, the timeout adapter) is exercised
exactly as it is against lichess.org. Mocking the HTTP layer hides the very
failures these tests exist for: a connection that goes silent, a stream that
is reopened in the middle of a game.
"""

import json
import socket
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import berserk

import bot

STALL = object()   # keep the connection open and send nothing more
CLOSE = object()   # end the response cleanly


class Refuse:
    """A script of this single step answers the connection with an HTTP error instead of a stream."""

    def __init__(self, status, payload=None):
        self.status = status
        self.payload = payload if payload is not None else {"error": "refused"}


class Await:
    """A step that holds the stream until the bot has made a matching request.

    ``Await("POST", "/api/bot/game/abc/move/")`` waits for the bot's next move,
    so a scripted game does not depend on timing. ``count`` is how many such
    requests must have been seen in total.
    """

    def __init__(self, method, path_prefix, count=1):
        self.method = method
        self.path_prefix = path_prefix
        self.count = count


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _record(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.requests.append((self.command, self.path, dict(self.headers), body))

    def _chunk(self, data: bytes):
        self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.flush()

    def _play(self, script):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for step in script:
            if step is STALL:
                self.server.stop.wait()
                return
            if step is CLOSE:
                break
            if isinstance(step, (int, float)):
                if self.server.stop.wait(step):
                    return
                continue
            if isinstance(step, Await):
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    seen = sum(1 for m, p, _, _ in list(self.server.requests)
                               if m == step.method and p.startswith(step.path_prefix))
                    if seen >= step.count or self.server.stop.wait(0.01):
                        break
                continue
            self._chunk(step + b"\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _respond(self):
        self._record()
        path = self.path.split("?")[0]
        scripts = self.server.streams.get(path)
        if scripts:
            script = scripts.popleft()
            if script and isinstance(script[0], Refuse):
                self._json(script[0].status, script[0].payload)
            else:
                self._play(script)
            return
        queue = self.server.replies.get((self.command, path))
        if queue is None:
            # a reply registered for "/some/prefix/*" answers every path under it
            for (method, pattern), candidate in self.server.replies.items():
                if method == self.command and pattern.endswith("*") and path.startswith(pattern[:-1]):
                    queue = candidate
                    break
        if not queue:
            status, payload = 404, {"error": "Not found"}
        elif len(queue) > 1:
            status, payload = queue.popleft()
        else:
            status, payload = queue[0]
        self._json(status, payload)

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _respond


class StubLichess:
    """A local HTTP server that plays back scripted streams and canned replies.

    ``stream(path, steps)`` queues one response for the next connection to
    ``path``; a step is a line of bytes, a pause in seconds, ``STALL``,
    ``CLOSE`` or an ``Await``.
    ``reply(method, path, status, payload)`` queues the JSON answer of a plain
    request; answers are given in order and the last one repeats, and a path
    ending in ``*`` answers everything under it. Every request received is
    kept in ``requests``.
    """

    def __init__(self):
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._server.streams = defaultdict(deque)
        self._server.replies = {}
        self._server.requests = []
        self._server.stop = threading.Event()
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stream(self, path, steps):
        self._server.streams[path].append(list(steps))

    def reply(self, method, path, status=200, payload=None):
        answer = (status, payload if payload is not None else {"ok": True})
        self._server.replies.setdefault((method, path), deque()).append(answer)

    @property
    def requests(self):
        return list(self._server.requests)

    def paths(self, method=None):
        return [p for m, p, _, _ in self._server.requests if method in (None, m)]

    def close(self):
        self._server.stop.set()
        self._server.shutdown()
        self._server.server_close()


def session_with_timeout(timeout):
    session = berserk.TokenSession("test-token")
    adapter = bot.TimeoutHTTPAdapter(timeout=timeout)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def within(seconds, fn):
    """Run ``fn`` in a thread and return (finished, result or exception).

    A regression here shows up as a call that never returns, so the test has
    to be able to give up on it instead of hanging the whole run.
    """
    box = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as exc:  # the exception is what most callers assert on
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(seconds)
    return (not thread.is_alive()), box


def refused_url():
    """Address of a port nothing listens on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


def event_line(kind, **payload):
    return json.dumps({"type": kind, **payload}).encode()


KEEP_ALIVE = b""
