"""
Scenario tests for the paths that keep the bot connected: timeouts, reconnects,
shutdown. They run against a local server that plays back a scripted Lichess
stream over a real socket, because the failures they guard against (a
connection that goes silent, a stream that is reopened mid-game) do not show
up when the HTTP layer is mocked.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import berserk
import requests

os.environ.setdefault('TOKEN', 'test_token_for_testing')

import bot
import healthcheck

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
        queue = self.server.replies.get((self.command, path))
        if not queue:
            status, payload = 404, {"error": "Not found"}
        elif len(queue) > 1:
            status, payload = queue.popleft()
        else:
            status, payload = queue[0]
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
    ``reply(method, path, status, payload)`` queues the JSON answer of a plain
    request; answers are given in order and the last one repeats. Every
    request received is kept in ``requests``.
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


class TestErrorClassification(StubLichessTestCase):
    """Errors are told apart by what Lichess answered, on real responses."""

    def client(self):
        return berserk.Client(session_with_timeout((2, 2)), base_url=self.lichess.url)

    def failure(self, status):
        self.lichess.reply("GET", "/api/account", status, {"error": "nope"})
        with self.assertRaises(berserk.exceptions.ResponseError) as caught:
            self.client().account.get()
        return caught.exception

    def test_status_is_read_from_a_real_error_response(self):
        for status in (401, 404, 429, 502, 503, 504):
            with self.subTest(status=status):
                self.lichess = StubLichess()
                self.addCleanup(self.lichess.close)
                exc = self.failure(status)
                # Why the status must not be reached through `exc.response and ...`.
                self.assertFalse(exc.response)
                self.assertEqual(bot._http_status(exc), status)

    def test_status_of_something_that_is_not_an_http_answer(self):
        self.assertIsNone(bot._http_status(ValueError("boom")))
        self.assertIsNone(bot._http_status(requests.exceptions.ConnectionError("down")))

    def test_retry_with_backoff_retries_gateway_errors_until_lichess_answers(self):
        self.lichess.reply("GET", "/api/account", 502, {"error": "bad gateway"})
        self.lichess.reply("GET", "/api/account", 503, {"error": "unavailable"})
        self.lichess.reply("GET", "/api/account", 200, {"username": "Axiom_BOT", "title": "BOT"})
        client = self.client()

        with patch("bot.time.sleep") as sleep:
            account = bot.retry_with_backoff(client.account.get, max_retries=5, base_delay=2, description="Get account")

        self.assertEqual(account["username"], "Axiom_BOT")
        self.assertEqual(self.lichess.paths("GET"), ["/api/account"] * 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])

    def test_retry_with_backoff_does_not_retry_a_rejected_token(self):
        self.lichess.reply("GET", "/api/account", 401, {"error": "No such token"})
        client = self.client()

        with patch("bot.time.sleep") as sleep:
            with self.assertRaises(berserk.exceptions.ResponseError):
                bot.retry_with_backoff(client.account.get, max_retries=5, description="Get account")

        self.assertEqual(len(self.lichess.paths("GET")), 1)
        sleep.assert_not_called()

    def test_retry_with_backoff_stops_after_the_last_attempt(self):
        self.lichess.reply("GET", "/api/account", 504, {"error": "timeout"})
        client = self.client()

        with patch("bot.time.sleep"):
            with self.assertRaises(berserk.exceptions.ResponseError):
                bot.retry_with_backoff(client.account.get, max_retries=3, description="Get account")

        self.assertEqual(len(self.lichess.paths("GET")), 3)


def refused_url():
    """Address of a port nothing listens on."""
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


class TestNetworkErrors(StubLichessTestCase):
    """A connection that fails is a network error, whichever library reports it."""

    def test_refused_connection_arrives_wrapped_by_berserk(self):
        client = berserk.Client(session_with_timeout((1, 1)), base_url=refused_url())
        with self.assertRaises(berserk.exceptions.ApiError) as caught:
            client.account.get()

        # Not one of the requests classes the bot used to catch.
        self.assertNotIsInstance(caught.exception, requests.exceptions.RequestException)
        self.assertTrue(bot._is_network_error(caught.exception))

    def test_read_timeout_on_a_stream_is_a_network_error(self):
        self.lichess.stream("/api/stream/event", [STALL])
        client = berserk.Client(session_with_timeout((1, 0.3)), base_url=self.lichess.url)

        finished, box = within(5, lambda: next(client.bots.stream_incoming_events()))

        self.assertTrue(finished)
        self.assertTrue(bot._is_network_error(box["error"]))

    def test_an_answer_from_lichess_is_not_a_network_error(self):
        self.lichess.reply("GET", "/api/account", 404, {"error": "Not found"})
        client = berserk.Client(session_with_timeout((1, 1)), base_url=self.lichess.url)
        with self.assertRaises(berserk.exceptions.ResponseError) as caught:
            client.account.get()

        self.assertFalse(bot._is_network_error(caught.exception))

    def test_unrelated_errors_are_not_network_errors(self):
        self.assertFalse(bot._is_network_error(ValueError("boom")))
        self.assertFalse(bot._is_network_error(berserk.exceptions.ApiError(ValueError("boom"))))

    def test_retry_with_backoff_retries_until_the_network_is_back(self):
        self.lichess.reply("GET", "/api/account", 200, {"username": "Axiom_BOT"})
        down = berserk.Client(session_with_timeout((1, 1)), base_url=refused_url())
        up = berserk.Client(session_with_timeout((1, 1)), base_url=self.lichess.url)
        attempts = iter([down.account.get, down.account.get, up.account.get])

        with patch("bot.time.sleep") as sleep:
            account = bot.retry_with_backoff(lambda: next(attempts)(), max_retries=10, base_delay=2, description="Get account")

        self.assertEqual(account["username"], "Axiom_BOT")
        self.assertEqual(sleep.call_count, 2)

    def test_event_stream_retry_delay_by_kind_of_failure(self):
        def status_error(status):
            stub = StubLichess()
            self.addCleanup(stub.close)
            stub.reply("GET", "/api/account", status, {"error": "x"})
            try:
                berserk.Client(session_with_timeout((1, 1)), base_url=stub.url).account.get()
            except berserk.exceptions.ResponseError as exc:
                return exc

        try:
            berserk.Client(session_with_timeout((1, 1)), base_url=refused_url()).account.get()
        except berserk.exceptions.ApiError as exc:
            refused = exc

        self.assertEqual(bot._event_stream_retry_delay(refused), 10)
        self.assertEqual(bot._event_stream_retry_delay(requests.exceptions.ChunkedEncodingError("cut")), 10)
        self.assertEqual(bot._event_stream_retry_delay(status_error(503)), 15)
        self.assertEqual(bot._event_stream_retry_delay(status_error(429)), 60)
        self.assertEqual(bot._event_stream_retry_delay(status_error(401)), 30)
        self.assertEqual(bot._event_stream_retry_delay(RuntimeError("bug")), 10)


class TestHeartbeat(unittest.TestCase):
    """The stamp file and the check that reads it."""

    def setUp(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        self.path = os.path.join(directory, "heartbeat")

    def write(self, text):
        with open(self.path, "w") as f:
            f.write(text)

    def check(self):
        """Run the check the way the container does and return its exit status."""
        script = os.path.join(os.path.dirname(os.path.abspath(healthcheck.__file__)), "healthcheck.py")
        return subprocess.run([sys.executable, script, self.path], timeout=20).returncode

    def test_no_stamp_is_unhealthy(self):
        self.assertIsNone(healthcheck.age(self.path))
        self.assertFalse(healthcheck.is_healthy(self.path))
        self.assertEqual(self.check(), 1)

    def test_a_fresh_stamp_is_healthy(self):
        healthcheck.beat(self.path)

        self.assertLess(healthcheck.age(self.path), 5)
        self.assertTrue(healthcheck.is_healthy(self.path))
        self.assertEqual(self.check(), 0)

    def test_a_stale_stamp_is_unhealthy(self):
        self.write(str(time.time() - healthcheck.MAX_AGE - 1))

        self.assertFalse(healthcheck.is_healthy(self.path))
        self.assertEqual(self.check(), 1)

    def test_a_stamp_just_inside_the_limit_is_healthy(self):
        self.write(str(time.time() - healthcheck.MAX_AGE + 5))

        self.assertTrue(healthcheck.is_healthy(self.path))

    def test_an_unreadable_stamp_is_unhealthy(self):
        self.write("not a number")

        self.assertFalse(healthcheck.is_healthy(self.path))
        self.assertEqual(self.check(), 1)

    def test_clear_removes_the_stamp_and_tolerates_its_absence(self):
        healthcheck.beat(self.path)
        healthcheck.clear(self.path)
        healthcheck.clear(self.path)

        self.assertFalse(os.path.exists(self.path))

    def test_beat_leaves_no_scratch_file_behind(self):
        healthcheck.beat(self.path)

        self.assertEqual(os.listdir(os.path.dirname(self.path)), ["heartbeat"])

    def test_the_limit_outlasts_one_reconnect(self):
        connect, read = bot.HTTP_TIMEOUT
        # notice the silence, wait before reopening, connect again
        self.assertGreater(healthcheck.MAX_AGE, read + 10 + connect)


def event_line(kind, **payload):
    return json.dumps({"type": kind, **payload}).encode()


KEEP_ALIVE = b""


class EventLoopTestCase(StubLichessTestCase):
    """Runs the real event loop against the stub until the test has seen enough."""

    def setUp(self):
        super().setUp()
        directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        self.heartbeat = os.path.join(directory, "heartbeat")
        self.patch("healthcheck.HEARTBEAT_FILE", self.heartbeat)

        self.state = bot.BotState(client=MagicMock(), username="Axiom_BOT", tracker=bot.ChallengeTracker(5))
        self.session = session_with_timeout((2, 0.5))
        self.pauses = []
        self.addCleanup(setattr, bot, "shutdown_requested", False)

    def patch(self, target, *args, **kwargs):
        patcher = patch(target, *args, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def run_loop(self, pauses):
        """Run the loop until it has paused ``pauses`` times: once per stream that ended."""
        def pause(seconds):
            self.pauses.append(seconds)
            if len(self.pauses) >= pauses:
                bot.shutdown_requested = True

        self.patch("bot._pause", pause)
        finished, box = within(20, lambda: bot.run_event_loop(self.session, self.state, self.lichess.url))
        self.assertTrue(finished, "the event loop did not come back")
        self.assertNotIn("error", box)


class TestEventLoop(EventLoopTestCase):
    def setUp(self):
        super().setUp()
        self.handled = []
        self.patch("bot.handle_event", lambda event, state: self.handled.append(event))

    def test_keep_alives_keep_an_idle_bot_healthy(self):
        """No event for the whole connection: the state the bot is in between games."""
        self.lichess.stream("/api/stream/event", [KEEP_ALIVE, 0.2, KEEP_ALIVE, 0.2, KEEP_ALIVE])
        self.assertFalse(healthcheck.is_healthy(self.heartbeat))

        with patch("healthcheck.beat", wraps=healthcheck.beat) as beat:
            self.run_loop(pauses=1)

        self.assertEqual(self.handled, [])
        self.assertEqual(beat.call_count, 3)
        self.assertTrue(healthcheck.is_healthy(self.heartbeat))
        self.assertTrue(self.state.stream.alive())

    def test_events_reach_the_handler_and_keep_alives_do_not(self):
        self.lichess.stream("/api/stream/event", [
            event_line("gameStart", game={"id": "game0001"}),
            KEEP_ALIVE,
            event_line("gameFinish", game={"id": "game0001"}),
        ])

        self.run_loop(pauses=1)

        self.assertEqual([e["type"] for e in self.handled], ["gameStart", "gameFinish"])
        self.assertEqual(self.pauses, [10])

    def test_the_request_asks_for_ndjson_with_the_token(self):
        self.lichess.stream("/api/stream/event", [KEEP_ALIVE])

        self.run_loop(pauses=1)

        method, path, headers, _ = self.lichess.requests[0]
        self.assertEqual((method, path), ("GET", "/api/stream/event"))
        self.assertEqual(headers["Accept"], "application/x-ndjson")
        self.assertEqual(headers["Authorization"], "Bearer test-token")

    def test_a_connection_that_goes_silent_is_replaced(self):
        self.lichess.stream("/api/stream/event", [event_line("gameStart", game={"id": "game0001"}), STALL])
        self.lichess.stream("/api/stream/event", [event_line("gameStart", game={"id": "game0001"}), KEEP_ALIVE])

        self.run_loop(pauses=2)

        self.assertEqual(self.lichess.paths("GET"), ["/api/stream/event"] * 2)
        self.assertEqual(len(self.handled), 2)
        # A read timeout is a network failure (10s), and so is a stream that ends.
        self.assertEqual(self.pauses, [10, 10])
        self.assertTrue(healthcheck.is_healthy(self.heartbeat))

    def test_a_stream_lichess_refuses_is_retried_later(self):
        self.lichess.reply("GET", "/api/stream/event", 429, {"error": "Too many requests"})

        self.run_loop(pauses=1)

        self.assertEqual(self.pauses, [60])
        self.assertFalse(healthcheck.is_healthy(self.heartbeat))
        self.assertFalse(self.state.stream.alive())

    def test_a_failing_handler_does_not_end_the_stream(self):
        def explode_once(event, state):
            self.handled.append(event)
            if len(self.handled) == 1:
                raise RuntimeError("bug in a handler")

        self.patch("bot.handle_event", explode_once)
        self.lichess.stream("/api/stream/event", [
            event_line("gameStart", game={"id": "game0001"}),
            event_line("gameStart", game={"id": "game0002"}),
        ])

        self.run_loop(pauses=1)

        self.assertEqual(len(self.handled), 2)
        self.assertEqual(self.lichess.paths("GET"), ["/api/stream/event"])

    def test_a_line_that_is_not_json_reopens_the_stream(self):
        self.lichess.stream("/api/stream/event", [b"{not json", STALL])
        self.lichess.stream("/api/stream/event", [event_line("gameStart", game={"id": "game0001"})])

        self.run_loop(pauses=2)

        self.assertEqual(len(self.handled), 1)
        self.assertEqual(self.pauses[0], 10)

    def test_shutdown_is_noticed_on_the_next_line(self):
        def stop_on_first_event(event, state):
            self.handled.append(event)
            bot.shutdown_requested = True

        self.patch("bot.handle_event", stop_on_first_event)
        self.lichess.stream("/api/stream/event", [
            event_line("gameStart", game={"id": "game0001"}),
            0.2,
            KEEP_ALIVE,
            STALL,
        ])

        finished, _ = within(5, lambda: bot.run_event_loop(self.session, self.state, self.lichess.url))

        self.assertTrue(finished)
        self.assertEqual(len(self.handled), 1)


class TestReconnectDuringGames(EventLoopTestCase):
    """The connection drops silently while games are being played: the 2026-10-08 failure, end to end."""

    def setUp(self):
        super().setUp()
        self.release = threading.Event()
        self.started = []
        self.addCleanup(self.release.set)

        def play(client, game_id, username):
            self.started.append(game_id)
            self.release.wait(10)

        self.patch("bot.play_game", play)

    def test_games_in_progress_survive_the_reconnect_untouched(self):
        both = [event_line("gameStart", game={"id": "game0001"}), event_line("gameStart", game={"id": "game0002"})]
        self.lichess.stream("/api/stream/event", both + [STALL])
        # Lichess announces every game in progress again when the stream reopens.
        self.lichess.stream("/api/stream/event", both + [KEEP_ALIVE])

        with patch("bot.MAX_CONCURRENT_GAMES", 2):
            self.run_loop(pauses=2)

        self.assertEqual(sorted(self.started), ["game0001", "game0002"])
        self.assertEqual(sorted(self.state.active_games), ["game0001", "game0002"])
        self.state.client.bots.abort_game.assert_not_called()
        self.state.client.bots.resign_game.assert_not_called()


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TestStallWatchdog(EventLoopTestCase):
    """The last resort: an event loop that has stopped moving ends the process."""

    def setUp(self):
        super().setUp()
        self.exits = []

    def watch(self, monitor, limit):
        """Run the watchdog until it exits the "process" or the test shuts it down."""
        return within(5, lambda: bot.watch_event_loop(monitor, limit=limit, interval=0.02, exit_process=self.exits.append))

    def test_monitor_measures_time_since_the_loop_last_moved(self):
        clock = FakeClock()
        monitor = bot.StreamMonitor(clock)

        clock.now += 40
        self.assertEqual(monitor.stalled_for(), 40)
        self.assertFalse(monitor.alive())

        monitor.progress()          # a reconnect attempt: moving, but nothing heard
        self.assertEqual(monitor.stalled_for(), 0)
        self.assertFalse(monitor.alive())

        monitor.line_received()     # a line from Lichess
        clock.now += 20
        self.assertEqual(monitor.stalled_for(), 20)
        self.assertTrue(monitor.alive())

        clock.now += 20
        self.assertFalse(monitor.alive())

    def test_a_loop_that_stops_moving_ends_the_process_with_a_failure_status(self):
        clock = FakeClock()
        monitor = bot.StreamMonitor(clock)
        clock.now += 301

        finished, _ = self.watch(monitor, limit=300)

        self.assertTrue(finished)
        self.assertEqual(self.exits, [1])

    def test_a_loop_that_keeps_reconnecting_is_left_alone(self):
        """Lichess unreachable for most of an hour: the loop is busy, not stuck."""
        clock = FakeClock()
        monitor = bot.StreamMonitor(clock)
        rounds = []

        def pause(seconds):
            clock.now += 40         # a connection attempt that fails...
            monitor.progress()      # ...and the loop comes round to try again
            clock.now += 20
            rounds.append(seconds)
            if len(rounds) == 50:
                bot.shutdown_requested = True

        self.patch("bot._pause", pause)
        bot.watch_event_loop(monitor, limit=300, interval=15, exit_process=self.exits.append)

        self.assertEqual(len(rounds), 50)
        self.assertEqual(self.exits, [])

    def test_shutdown_stops_the_watchdog_without_an_exit(self):
        clock = FakeClock()
        monitor = bot.StreamMonitor(clock)
        bot.shutdown_requested = True
        clock.now += 1000

        finished, _ = self.watch(monitor, limit=300)

        self.assertTrue(finished)
        self.assertEqual(self.exits, [])

    def test_a_handler_that_never_returns_is_caught(self):
        """The event loop is alive but stuck inside one event."""
        stuck = threading.Event()
        self.addCleanup(stuck.set)
        self.patch("bot.handle_event", lambda event, state: stuck.wait(30))
        self.lichess.stream("/api/stream/event", [event_line("gameStart", game={"id": "game0001"}), KEEP_ALIVE, STALL])

        threading.Thread(target=bot.run_event_loop, args=(self.session, self.state, self.lichess.url), daemon=True).start()
        finished, _ = self.watch(self.state.stream, limit=0.3)
        bot.shutdown_requested = True

        self.assertTrue(finished)
        self.assertEqual(self.exits, [1])

    def test_the_limit_is_far_above_any_wait_of_a_healthy_loop(self):
        connect, read = bot.HTTP_TIMEOUT
        longest_healthy_gap = max(read, 60)   # a silent read, or the pause after a 429
        self.assertGreater(bot.STALL_EXIT_AFTER, 3 * longest_healthy_gap)


class TestShutdown(unittest.TestCase):
    """Signals sent to a real process whose main thread is blocked, as it is on the event stream."""

    DRIVER = """
import os, sys, threading, time
import bot, healthcheck

healthcheck.HEARTBEAT_FILE = sys.argv[1]
healthcheck.beat()
bot.install_signal_handlers()
{setup}
print("ready", flush=True)
time.sleep(60)
print("the main thread was never interrupted", flush=True)
"""

    def setUp(self):
        directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        self.heartbeat = os.path.join(directory, "heartbeat")

    def start(self, setup=""):
        process = subprocess.Popen(
            [sys.executable, "-c", self.DRIVER.format(setup=setup), self.heartbeat],
            cwd=os.path.dirname(os.path.abspath(bot.__file__)),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        self.addCleanup(process.kill)
        self.addCleanup(process.stdout.close)
        for line in process.stdout:
            if line.strip() == "ready":
                return process
        self.fail("the process did not start")

    def stop(self, process, signals=1, gap=0.3, timeout=10):
        import signal
        started = time.monotonic()
        for n in range(signals):
            if n:
                time.sleep(gap)
            process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout)
        except subprocess.TimeoutExpired:
            self.fail(f"still running {timeout}s after SIGTERM: the process ignores shutdown")
        return time.monotonic() - started, process.stdout.read()

    GAME = """
state = bot.BotState(client=None, username="Axiom_BOT", tracker=bot.ChallengeTracker(1))
bot._running_state = state

def game():
    while not bot.shutdown_requested:
        time.sleep(0.02)
    time.sleep({cleanup})
    print("game thread finished", flush=True)

thread = threading.Thread(target=game, daemon=True)
state.active_games["game0001"] = thread
thread.start()
bot.SHUTDOWN_TIMEOUT = {timeout}
"""

    def test_sigterm_ends_an_idle_bot_cleanly(self):
        process = self.start()
        self.assertTrue(healthcheck.is_healthy(self.heartbeat))

        elapsed, output = self.stop(process)

        self.assertEqual(process.returncode, 0)
        self.assertLess(elapsed, 5)
        self.assertIn("Graceful shutdown complete", output)
        self.assertNotIn("never interrupted", output)
        self.assertFalse(os.path.exists(self.heartbeat))

    def test_sigint_does_the_same(self):
        import signal
        process = self.start()

        process.send_signal(signal.SIGINT)
        process.wait(10)

        self.assertEqual(process.returncode, 0)

    def test_shutdown_waits_for_a_game_thread_to_wind_down(self):
        process = self.start(self.GAME.format(cleanup=0.8, timeout=10))

        elapsed, output = self.stop(process)

        self.assertEqual(process.returncode, 0)
        self.assertGreaterEqual(elapsed, 0.8)
        self.assertLess(elapsed, 6)
        self.assertIn("game thread finished", output)

    def test_shutdown_does_not_wait_past_its_limit(self):
        process = self.start(self.GAME.format(cleanup=30, timeout=1))

        elapsed, output = self.stop(process)

        self.assertEqual(process.returncode, 0)
        self.assertLess(elapsed, 6)
        self.assertNotIn("game thread finished", output)

    def test_a_second_signal_ends_the_process_at_once(self):
        process = self.start(self.GAME.format(cleanup=30, timeout=30))

        elapsed, output = self.stop(process, signals=2)

        self.assertEqual(process.returncode, 1)
        self.assertLess(elapsed, 5)
        self.assertIn("Force shutdown", output)

    def test_importing_the_bot_installs_no_signal_handler(self):
        import signal
        self.assertIsNot(signal.getsignal(signal.SIGTERM), bot.handle_shutdown)


if __name__ == "__main__":
    unittest.main()
