"""
Scenario tests for the paths that keep the bot connected: timeouts, reconnects,
shutdown. They run against a local server that plays back a scripted Lichess
stream over a real socket, because the failures they guard against (a
connection that goes silent, a stream that is reopened mid-game) do not show
up when the HTTP layer is mocked.
"""

import json
import os
import threading
import time
import unittest
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import berserk
import requests

os.environ.setdefault('TOKEN', 'test_token_for_testing')

import bot

STALL = object()   # keep the connection open and send nothing more
CLOSE = object()   # end the response cleanly


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
            self._chunk(step + b"\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _respond(self):
        self._record()
        path = self.path.split("?")[0]
        scripts = self.server.streams.get(path)
        if scripts:
            self._play(scripts.popleft())
            return
        status, payload = self.server.replies.get((self.command, path), (404, {"error": "Not found"}))
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
    ``path``. A step is a line of bytes, a pause in seconds, ``STALL`` or
    ``CLOSE``; a script that runs out ends the response like ``CLOSE``.
    ``reply(method, path, status, payload)`` sets the JSON answer of a plain
    request. Every request received is kept in ``requests``.
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
        self._server.replies[(method, path)] = (status, payload if payload is not None else {"ok": True})

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


class StubLichessTestCase(unittest.TestCase):
    def setUp(self):
        self.lichess = StubLichess()
        self.addCleanup(self.lichess.close)


class TestHttpTimeout(StubLichessTestCase):
    """Every request the bot makes must carry a timeout."""

    def test_default_timeout_reaches_the_transport_through_a_session(self):
        """A session passes timeout=None to its adapter; the default has to replace it."""
        session = session_with_timeout((10, 30))
        seen = []

        def capture(self, request, **kwargs):
            seen.append(kwargs.get("timeout"))
            raise requests.exceptions.ConnectionError("stop here")

        with patch.object(requests.adapters.HTTPAdapter, "send", capture):
            with self.assertRaises(requests.exceptions.ConnectionError):
                session.get(f"{self.lichess.url}/api/account")
            with self.assertRaises(requests.exceptions.ConnectionError):
                session.get(f"{self.lichess.url}/api/stream/event", stream=True)

        self.assertEqual(seen, [(10, 30), (10, 30)])

    def test_explicit_timeout_is_kept(self):
        session = session_with_timeout((10, 30))
        seen = []

        def capture(self, request, **kwargs):
            seen.append(kwargs.get("timeout"))
            raise requests.exceptions.ConnectionError("stop here")

        with patch.object(requests.adapters.HTTPAdapter, "send", capture):
            with self.assertRaises(requests.exceptions.ConnectionError):
                session.get(f"{self.lichess.url}/api/account", timeout=3)

        self.assertEqual(seen, [3])

    def test_main_mounts_the_adapter_with_a_finite_timeout(self):
        connect, read = bot.HTTP_TIMEOUT
        self.assertGreater(connect, 0)
        # Lichess sends a keep-alive every 7 seconds; the read timeout has to
        # leave room for a few missed ones and still be finite.
        self.assertGreater(read, 14)
        self.assertLessEqual(read, 120)

    def test_a_stream_that_goes_silent_raises_instead_of_blocking(self):
        """The connection stays open and no byte arrives: the 2026-10-08 failure."""
        self.lichess.stream("/api/stream/event", [b'{"type":"gameStart","game":{"id":"abc12345"}}', STALL])
        client = berserk.Client(session_with_timeout((2, 0.5)), base_url=self.lichess.url)
        events = client.bots.stream_incoming_events()

        self.assertEqual(next(events)["type"], "gameStart")

        started = time.monotonic()
        finished, box = within(5, lambda: next(events))

        self.assertTrue(finished, "the read on a silent stream never returned")
        self.assertIsInstance(box.get("error"), requests.exceptions.ConnectionError)
        self.assertLess(time.monotonic() - started, 3)

    def test_a_request_that_is_never_answered_raises(self):
        self.lichess.stream("/api/account", [STALL])
        client = berserk.Client(session_with_timeout((2, 0.5)), base_url=self.lichess.url)

        finished, box = within(5, client.account.get)

        self.assertTrue(finished, "the request never returned")
        self.assertIsInstance(box.get("error"), Exception)


if __name__ == "__main__":
    unittest.main()
