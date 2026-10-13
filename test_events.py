"""
Scenario tests for what the bot does with the events Lichess sends: games
starting and finishing, challenges arriving, being declined or expiring.

The Lichess client is a recording fake and ``play_game`` is replaced by a
stand-in that stays "in a game" until released, so each test drives the real
event handling through a sequence of events and checks what it asked Lichess
to do.
"""

import os
import threading
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('TOKEN', 'test_token_for_testing')

import bot


class RunningGames:
    """Stand-in for play_game: every game runs until ``finish`` is called for it."""

    def __init__(self):
        self.started = []
        self._done = {}
        self._lock = threading.Lock()

    def __call__(self, client, game_id, username):
        with self._lock:
            self.started.append(game_id)
            done = self._done[game_id] = threading.Event()
        done.wait(10)

    def finish(self, game_id):
        with self._lock:
            self._done[game_id].set()

    def finish_all(self):
        with self._lock:
            for done in self._done.values():
                done.set()


class EventTestCase(unittest.TestCase):
    def setUp(self):
        self.games = RunningGames()
        patcher = patch("bot.play_game", self.games)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.games.finish_all)

        # The heartbeat file belongs to a running bot, not to a test run.
        beat = patch("healthcheck.beat")
        beat.start()
        self.addCleanup(beat.stop)

        self.client = MagicMock()
        self.state = bot.BotState(
            client=self.client,
            username="Axiom_BOT",
            tracker=bot.ChallengeTracker(5),
        )

    def send(self, kind, **payload):
        bot.handle_event({"type": kind, **payload}, self.state)

    def start_game(self, game_id, **game):
        self.send("gameStart", game={"id": game_id, **game})
        thread = self.state.active_games[game_id]
        self.wait_until(lambda: game_id in self.games.started)
        return thread

    def end_game(self, game_id):
        thread = self.state.active_games.get(game_id)
        self.games.finish(game_id)
        if thread is not None:
            thread.join(5)

    def wait_until(self, condition, seconds=5):
        deadline = threading.Event()
        for _ in range(int(seconds / 0.01)):
            if condition():
                return
            deadline.wait(0.01)
        self.fail("condition was not met in time")

    def alive(self):
        return sorted(gid for gid, t in self.state.active_games.items() if t.is_alive())


class TestGameStart(EventTestCase):
    def test_a_new_game_gets_a_thread(self):
        self.start_game("game0001")

        self.assertEqual(self.alive(), ["game0001"])
        self.client.bots.abort_game.assert_not_called()

    def test_reopened_stream_announcing_running_games_changes_nothing(self):
        """Lichess repeats gameStart for every game in progress when the stream reopens."""
        first = self.start_game("game0001")
        second = self.start_game("game0002")

        with patch("bot.MAX_CONCURRENT_GAMES", 2):
            self.send("gameStart", game={"id": "game0001"})
            self.send("gameStart", game={"id": "game0002"})

        self.assertIs(self.state.active_games["game0001"], first)
        self.assertIs(self.state.active_games["game0002"], second)
        self.assertEqual(self.games.started, ["game0001", "game0002"])
        self.client.bots.abort_game.assert_not_called()
        self.client.bots.resign_game.assert_not_called()

    def test_repeated_announcement_of_a_single_game_does_not_start_a_second_engine(self):
        thread = self.start_game("game0001")

        self.send("gameStart", game={"id": "game0001"})

        self.assertIs(self.state.active_games["game0001"], thread)
        self.assertEqual(self.games.started, ["game0001"])

    def test_a_game_whose_thread_died_is_picked_up_again(self):
        self.start_game("game0001")
        self.end_game("game0001")

        self.send("gameStart", game={"id": "game0001"})
        self.wait_until(lambda: self.games.started.count("game0001") == 2)

        self.assertEqual(self.alive(), ["game0001"])

    def test_a_game_beyond_the_limit_is_aborted(self):
        with patch("bot.MAX_CONCURRENT_GAMES", 1):
            self.start_game("game0001")
            self.send("gameStart", game={"id": "game0002"})

        self.client.bots.abort_game.assert_called_once_with("game0002")
        self.client.bots.resign_game.assert_not_called()
        self.assertEqual(self.alive(), ["game0001"])

    def test_a_game_beyond_the_limit_is_resigned_when_abort_is_refused(self):
        self.client.bots.abort_game.side_effect = RuntimeError("too late to abort")
        with patch("bot.MAX_CONCURRENT_GAMES", 1):
            self.start_game("game0001")
            self.send("gameStart", game={"id": "game0002"})

        self.client.bots.resign_game.assert_called_once_with("game0002")

    def test_a_finished_game_frees_its_slot(self):
        with patch("bot.MAX_CONCURRENT_GAMES", 1):
            self.start_game("game0001")
            self.end_game("game0001")
            self.send("gameFinish", game={"id": "game0001"})
            self.start_game("game0002")

        self.assertEqual(self.alive(), ["game0002"])
        self.client.bots.abort_game.assert_not_called()

    def test_the_game_of_the_bots_own_challenge_clears_it_and_wakes_the_challenge_loop(self):
        self.state.pending_challenge.update(id="chal0001", opponent="otherbot", sent_at=0.0)

        self.start_game("chal0001")     # a game has the id of its challenge

        self.assertEqual(self.state.pending_challenge, {})
        self.assertTrue(self.state.retry_event.is_set())

    def test_another_game_starting_leaves_the_bots_own_challenge_open(self):
        self.state.pending_challenge.update(id="chal0001", opponent="otherbot", sent_at=0.0)

        self.start_game("game0001")

        self.assertEqual(self.state.pending_challenge["id"], "chal0001")
        self.assertTrue(self.state.retry_event.is_set())


def incoming(challenge_id, rating=1800, limit=300, increment=0, variant="standard", to="Axiom_BOT", sender="otherbot"):
    """A challenge event as Lichess sends it."""
    return {
        "id": challenge_id,
        "challenger": {"id": sender.lower(), "name": sender, "rating": rating, "title": "BOT"},
        "destUser": {"id": to.lower(), "name": to, "rating": 2000, "title": "BOT"},
        "variant": {"key": variant},
        "rated": True,
        "speed": "blitz",
        "timeControl": {"type": "clock", "limit": limit, "increment": increment},
    }


def http_error(status, payload=None):
    """The error berserk raises for an HTTP answer with this status and JSON body."""
    import json
    import requests
    import berserk
    response = requests.Response()
    response.status_code = status
    response.reason = "error"
    response._content = json.dumps(payload if payload is not None else {"error": "x"}).encode()
    return berserk.exceptions.ResponseError(response)


class TestIncomingChallenge(EventTestCase):
    def test_a_suitable_challenge_is_accepted_and_holds_a_slot(self):
        with patch("bot.MAX_CONCURRENT_GAMES", 2):
            self.send("challenge", challenge=incoming("chal0001"))
            free = bot.free_game_slots(self.state)

        self.client.bots.accept_challenge.assert_called_once_with("chal0001")
        self.client.bots.decline_challenge.assert_not_called()
        self.assertEqual(free, 1)

    def test_a_challenge_outside_the_rating_range_is_declined(self):
        self.send("challenge", challenge=incoming("chal0001", rating=900))

        self.client.bots.decline_challenge.assert_called_once_with("chal0001", reason="generic")
        self.client.bots.accept_challenge.assert_not_called()

    def test_a_variant_challenge_is_declined_as_standard_only(self):
        self.send("challenge", challenge=incoming("chal0001", variant="chess960"))

        self.client.bots.decline_challenge.assert_called_once_with("chal0001", reason="standard")

    def test_a_speed_the_bot_does_not_play_is_declined_with_the_direction_to_go(self):
        cases = {
            (60, 0): "tooFast",        # bullet, when blitz and rapid are played
            (1800, 0): "tooSlow",      # classical
        }
        with patch("bot.TIME_CONTROL", ["blitz", "rapid"]):
            for (limit, increment), reason in cases.items():
                with self.subTest(clock=f"{limit}+{increment}"):
                    self.client.reset_mock()
                    self.send("challenge", challenge=incoming("chal0001", limit=limit, increment=increment))
                    self.client.bots.decline_challenge.assert_called_once_with("chal0001", reason=reason)

    def test_a_speed_left_out_in_the_middle_is_declined_as_a_time_control(self):
        with patch("bot.TIME_CONTROL", ["bullet", "classical"]):
            self.send("challenge", challenge=incoming("chal0001", limit=300, increment=0))

        self.client.bots.decline_challenge.assert_called_once_with("chal0001", reason="timeControl")

    def test_a_game_without_a_clock_is_declined_as_a_time_control(self):
        challenge = incoming("chal0001")
        challenge["timeControl"] = {"type": "correspondence", "daysPerTurn": 3}
        challenge["speed"] = "correspondence"

        self.send("challenge", challenge=challenge)

        self.client.bots.decline_challenge.assert_called_once_with("chal0001", reason="timeControl")

    def test_a_challenge_is_declined_for_later_while_every_slot_is_playing(self):
        with patch("bot.MAX_CONCURRENT_GAMES", 2):
            self.start_game("game0001")
            self.start_game("game0002")
            self.send("challenge", challenge=incoming("chal0001"))

        self.client.bots.accept_challenge.assert_not_called()
        self.client.bots.decline_challenge.assert_called_once_with("chal0001", reason="later")

    def test_two_challenges_arriving_together_cannot_both_take_the_last_slot(self):
        """The second arrives before the first has turned into a game."""
        with patch("bot.MAX_CONCURRENT_GAMES", 2):
            self.start_game("game0001")
            self.send("challenge", challenge=incoming("chal0001"))
            self.send("challenge", challenge=incoming("chal0002", sender="thirdbot"))

        self.client.bots.accept_challenge.assert_called_once_with("chal0001")
        self.client.bots.decline_challenge.assert_called_once_with("chal0002", reason="later")

    def test_the_slot_of_an_accepted_challenge_becomes_the_game(self):
        with patch("bot.MAX_CONCURRENT_GAMES", 2):
            self.send("challenge", challenge=incoming("chal0001"))
            self.start_game("chal0001")     # the game has the id of the challenge
            free = bot.free_game_slots(self.state)

        self.assertEqual(self.state.accepted_challenges, {})
        self.assertEqual(free, 1)

    def test_an_accepted_challenge_that_never_starts_gives_its_slot_back(self):
        with patch("bot.MAX_CONCURRENT_GAMES", 1):
            with patch("bot.time.monotonic", return_value=1000.0):
                self.send("challenge", challenge=incoming("chal0001"))
                self.assertEqual(bot.free_game_slots(self.state), 0)
            with patch("bot.time.monotonic", return_value=1000.0 + bot.ACCEPTED_CHALLENGE_TTL + 1):
                self.assertEqual(bot.free_game_slots(self.state), 1)

    def test_a_challenge_that_is_gone_when_answered_takes_no_slot(self):
        self.client.bots.accept_challenge.side_effect = http_error(404)
        with patch("bot.MAX_CONCURRENT_GAMES", 2):
            self.send("challenge", challenge=incoming("chal0001"))
            free = bot.free_game_slots(self.state)

        self.assertEqual(free, 2)

    def test_taking_the_last_slot_withdraws_the_bots_own_open_challenge(self):
        self.state.pending_challenge.update(id="mine0001", opponent="slowbot", sent_at=0.0)
        with patch("bot.MAX_CONCURRENT_GAMES", 2):
            self.start_game("game0001")
            self.send("challenge", challenge=incoming("chal0001"))

        self.client.bots.accept_challenge.assert_called_once_with("chal0001")
        self.client.challenges.cancel.assert_called_once_with("mine0001")
        self.assertEqual(self.state.pending_challenge, {})

    def test_an_open_challenge_is_kept_while_a_slot_remains(self):
        self.state.pending_challenge.update(id="mine0001", opponent="slowbot", sent_at=0.0)
        with patch("bot.MAX_CONCURRENT_GAMES", 3):
            self.send("challenge", challenge=incoming("chal0001"))

        self.client.challenges.cancel.assert_not_called()
        self.assertEqual(self.state.pending_challenge["id"], "mine0001")


class TestOutgoingChallenge(EventTestCase):
    def test_the_event_for_the_bots_own_challenge_names_the_opponent(self):
        self.state.pending_challenge.update(id="mine0001", opponent="unknown", sent_at=0.0)

        self.send("challenge", challenge=incoming("mine0001", to="SlowBot", sender="Axiom_BOT"))

        self.assertEqual(self.state.pending_challenge["opponent"], "slowbot")
        self.client.bots.accept_challenge.assert_not_called()
        self.client.bots.decline_challenge.assert_not_called()

    def test_a_decline_of_the_bots_challenge_clears_it(self):
        self.state.pending_challenge.update(id="mine0001", opponent="slowbot", sent_at=0.0)

        with patch("bot.threading.Timer") as timer:
            self.send("challengeDeclined", challenge={"id": "mine0001", "destUser": {"name": "SlowBot"}, "declineReasonKey": "later"})

        self.assertEqual(self.state.pending_challenge, {})
        timer.assert_called_once_with(30, self.state.retry_event.set)
        self.assertTrue(timer.return_value.daemon)

    def test_a_cancel_of_the_bots_challenge_wakes_the_challenge_loop(self):
        self.state.pending_challenge.update(id="mine0001", opponent="slowbot", sent_at=0.0)

        self.send("challengeCanceled", challenge={"id": "mine0001", "challenger": {"name": "Axiom_BOT"}})

        self.assertEqual(self.state.pending_challenge, {})
        self.assertTrue(self.state.retry_event.is_set())

    def test_withdrawing_a_challenge_survives_lichess_refusing(self):
        self.state.pending_challenge.update(id="mine0001", opponent="slowbot", sent_at=0.0)
        self.client.challenges.cancel.side_effect = http_error(404)

        bot.cancel_pending_challenge(self.state, "test")

        self.assertEqual(self.state.pending_challenge, {})

    def test_withdrawing_without_an_open_challenge_calls_nothing(self):
        bot.cancel_pending_challenge(self.state, "test")

        self.client.challenges.cancel.assert_not_called()


class LoopClock:
    """The clock the challenge loop reads, moved by the waits it makes."""

    def __init__(self):
        self.now = bot.time.monotonic()

    def __call__(self):
        return self.now


class StoppingEvent:
    """Stands in for the challenge loop's wake-up event: records every wait and ends the loop after a set number.

    With a clock, each wait takes the time it asked for, or ``woken_after``
    seconds when something is to wake the loop early.
    """

    def __init__(self, waits, clock=None, woken_after=None):
        self.timeouts = []
        self._waits = waits
        self._clock = clock
        self._woken_after = woken_after

    def wait(self, timeout=None):
        self.timeouts.append(timeout)
        if self._clock is not None:
            self._clock.now += timeout if self._woken_after is None else min(timeout, self._woken_after)
        if len(self.timeouts) >= self._waits:
            bot.shutdown_requested = True
        return False

    def set(self):
        pass

    def clear(self):
        pass


def online_bot(name, **ratings):
    return {"username": name, "perfs": {speed: {"rating": rating} for speed, rating in ratings.items()}}


class ChallengeLoopTestCase(EventTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, bot, "shutdown_requested", False)
        for name, value in {
            "bot.ENABLE_AUTO_CHALLENGE": True,
            "bot.MAX_CONCURRENT_GAMES": 2,
            "bot.CHALLENGE_CHECK_INTERVAL": 60,
            "bot.CHALLENGE_MIN_RATING": 1500,
            "bot.CHALLENGE_MAX_RATING": 2900,
            "bot.CHALLENGE_TIME_CONTROLS": [{"limit": 300, "increment": 3}],
            "bot.random.choice": lambda options: options[0],      # the first suitable bot, every time
        }.items():
            patcher = patch(name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.online = [online_bot("OtherBot", blitz=2000)]
        self.client.bots.get_online_bots.side_effect = lambda limit=None: iter(self.online)
        self.client.challenges.create.return_value = {"id": "chal0001"}
        self.stream_connected = True           # Lichess is being heard from

    def run_loop(self, waits, woken_after=None):
        """Run the challenge loop until it has waited ``waits`` times; return the waits it asked for.

        Time passes as the loop waits. ``woken_after`` cuts every wait short,
        the way a game starting or ending does.
        """
        clock = LoopClock()
        self.state.retry_event = StoppingEvent(waits, clock, woken_after)
        self.state.stream = bot.StreamMonitor(clock) if self.stream_connected else bot.StreamMonitor()
        if self.stream_connected:
            self.state.stream._last_line = float("inf")      # heard from, however long the loop waits
        with patch("bot.time.monotonic", clock):
            bot.challenge_loop(self.state)
        return [round(t) for t in self.state.retry_event.timeouts]


class TestChallengeLoop(ChallengeLoopTestCase):
    def test_an_idle_bot_challenges_a_suitable_bot_and_waits_for_the_answer(self):
        waits = self.run_loop(1)

        self.client.challenges.create.assert_called_once_with(
            "OtherBot", rated=True, clock_limit=300, clock_increment=3, color="random", variant="standard",
        )
        self.assertEqual(waits, [90])
        self.assertEqual(self.state.pending_challenge["id"], "chal0001")
        self.assertEqual(self.state.pending_challenge["opponent"], "OtherBot")
        self.assertEqual(self.state.tracker.counts(), (1, 1))

    def test_nothing_is_sent_while_the_event_stream_is_down(self):
        """With the stream down an accepted challenge would start a game nobody plays."""
        self.stream_connected = False

        waits = self.run_loop(3)

        self.assertEqual(waits, [5, 5, 5])       # a look at the stream, not a call to Lichess
        self.client.bots.get_online_bots.assert_not_called()
        self.client.challenges.create.assert_not_called()
        self.assertEqual(self.state.tracker.counts(), (0, 0))

    def test_challenging_resumes_when_the_stream_is_back(self):
        clock = LoopClock()
        self.state.stream = bot.StreamMonitor(clock)            # not heard from yet
        event = StoppingEvent(2, clock)
        waited = event.wait

        def wait_then_reconnect(timeout=None):
            result = waited(timeout)
            self.state.stream._last_line = float("inf")         # the stream is back
            return result

        event.wait = wait_then_reconnect
        self.state.retry_event = event
        with patch("bot.time.monotonic", clock):
            bot.challenge_loop(self.state)

        self.assertEqual(event.timeouts, [5, 90])
        self.client.challenges.create.assert_called_once()

    def test_nothing_is_sent_once_the_hourly_limit_is_used_up(self):
        self.state.tracker = bot.ChallengeTracker(max_per_hour=2, max_per_day=100)
        self.state.tracker.record_challenge()
        self.state.tracker.record_challenge()

        waits = self.run_loop(1)

        self.assertAlmostEqual(waits[0], 3600, delta=5)
        self.client.bots.get_online_bots.assert_not_called()
        self.client.challenges.create.assert_not_called()

    def test_nothing_is_sent_once_the_daily_limit_is_used_up(self):
        self.state.tracker = bot.ChallengeTracker(max_per_hour=100, max_per_day=3)
        for _ in range(3):
            self.state.tracker.record_challenge()

        waits = self.run_loop(1)

        self.assertAlmostEqual(waits[0], 86400, delta=5)
        self.client.challenges.create.assert_not_called()

    def test_a_refused_attempt_still_counts_against_the_limits(self):
        """Lichess counts the request whether or not a challenge comes of it."""
        self.client.challenges.create.side_effect = http_error(400, {"error": "OtherBot does not accept challenges"})

        waits = self.run_loop(1)

        self.assertEqual(waits, [60])
        self.assertEqual(self.state.pending_challenge, {})
        self.assertEqual(self.state.tracker.counts(), (1, 1))

    def test_a_429_backs_off_longer_each_time(self):
        self.client.challenges.create.side_effect = http_error(429, {"error": "Too many requests. Try again later."})

        waits = self.run_loop(4)

        self.assertEqual(waits, [300, 600, 1200, 2400])
        self.assertEqual(self.client.challenges.create.call_count, 4)

    def test_backoff_stops_growing_at_an_hour(self):
        self.client.challenges.create.side_effect = http_error(429, {"error": "Too many requests. Try again later."})
        self.state.tracker = bot.ChallengeTracker(max_per_hour=100, max_per_day=100)

        waits = self.run_loop(7)

        self.assertEqual(waits, [300, 600, 1200, 2400, 3600, 3600, 3600])

    def test_a_429_that_names_its_end_is_waited_out_exactly(self):
        """The limit on games between bots says how many seconds are left."""
        self.client.challenges.create.side_effect = http_error(429, {
            "error": "You played 100 games against other bots today, please wait before challenging another bot.",
            "ratelimit": {"key": "bot.vsBot.day", "seconds": 5000},
        })

        waits = self.run_loop(2)

        self.assertEqual(waits, [5060, 5060])

    def test_backoff_starts_over_after_a_challenge_that_worked(self):
        self.online = [online_bot("OtherBot", blitz=2000), online_bot("NextBot", blitz=2000)]
        self.client.challenges.create.side_effect = [
            http_error(429), http_error(429), {"id": "chal0001"}, http_error(429),
        ]

        waits = self.run_loop(5)

        # two refusals, then a challenge nobody answers (90s, withdrawn, 30s), then a refusal again
        self.assertEqual(waits, [300, 600, 90, 30, 300])

    def test_a_refusal_is_waited_out_however_often_the_loop_is_woken(self):
        """Games starting and ending wake the loop; none of that may reach Lichess before the wait is over."""
        self.client.challenges.create.side_effect = http_error(429, {"error": "Too many requests. Try again later."})

        waits = self.run_loop(10, woken_after=30)       # woken every 30 seconds

        self.assertEqual(self.client.challenges.create.call_count, 1)
        self.assertEqual(waits, [300, 270, 240, 210, 180, 150, 120, 90, 60, 30])

    def test_the_next_attempt_comes_when_the_wait_is_over(self):
        self.client.challenges.create.side_effect = http_error(429)

        waits = self.run_loop(12, woken_after=100)

        # 300s in three waits, then the second attempt; its 600s in six; then the third
        self.assertEqual(waits, [300, 200, 100, 600, 500, 400, 300, 200, 100, 1200, 1100, 1000])
        self.assertEqual(self.client.challenges.create.call_count, 3)

    def test_nothing_is_sent_while_every_slot_is_playing(self):
        self.start_game("game0001")
        self.start_game("game0002")

        waits = self.run_loop(2)

        self.assertEqual(waits, [60, 60])
        self.client.challenges.create.assert_not_called()

    def test_a_slot_held_by_an_accepted_challenge_counts_as_taken(self):
        self.start_game("game0001")
        self.send("challenge", challenge=incoming("chal0009"))

        waits = self.run_loop(1)

        self.assertEqual(waits, [60])
        self.client.challenges.create.assert_not_called()

    def test_an_open_challenge_is_given_its_time(self):
        self.state.pending_challenge.update(id="mine0001", opponent="SlowBot", sent_at=bot.time.monotonic() - 10)

        waits = self.run_loop(1)

        self.assertEqual(waits[0], 80)
        self.client.challenges.create.assert_not_called()
        self.client.challenges.cancel.assert_not_called()

    def test_an_unanswered_challenge_is_withdrawn_before_the_next_one(self):
        self.state.pending_challenge.update(id="mine0001", opponent="SlowBot", speed="blitz",
                                            sent_at=bot.time.monotonic() - 100)

        waits = self.run_loop(2)

        self.client.challenges.cancel.assert_called_once_with("mine0001")
        self.assertEqual(waits, [30, 90])
        self.assertEqual(self.state.pending_challenge["id"], "chal0001")

    def test_a_challenge_accepted_before_the_loop_notes_it_is_not_left_pending(self):
        def create_and_get_accepted(*args, **kwargs):
            self.start_game("chal0001")      # the game starts while the request returns
            return {"id": "chal0001"}

        self.client.challenges.create.side_effect = create_and_get_accepted

        self.run_loop(1)

        self.assertEqual(self.state.pending_challenge, {})

    def test_no_bot_in_the_rating_range_means_no_challenge(self):
        self.online = [online_bot("WeakBot", blitz=900), online_bot("Axiom_BOT", blitz=2000)]

        waits = self.run_loop(1)

        self.assertEqual(waits, [60])
        self.client.challenges.create.assert_not_called()
        self.assertEqual(self.state.tracker.counts(), (0, 0))

    def test_switching_auto_challenge_off_sends_nothing(self):
        with patch("bot.ENABLE_AUTO_CHALLENGE", False):
            waits = self.run_loop(2)

        self.assertEqual(waits, [60, 60])
        self.client.bots.get_online_bots.assert_not_called()

    def test_an_unexpected_error_does_not_end_the_loop(self):
        calls = []

        def boom(limit=None):
            calls.append(limit)
            if len(calls) == 1:
                raise RuntimeError("bug")
            return iter(self.online)

        self.client.bots.get_online_bots.side_effect = boom
        with patch("bot.time.sleep"):
            waits = self.run_loop(2)

        self.assertEqual(self.client.challenges.create.call_count, 1)
        self.assertEqual(waits[-1], 90)


def declined(challenge_id, by, reason, speed="blitz", challenger="Axiom_BOT"):
    """The challenge of a challengeDeclined event. Lichess writes the reason's key in lower case."""
    return {
        "id": challenge_id,
        "status": "declined",
        "challenger": {"id": challenger.lower(), "name": challenger, "title": "BOT"},
        "destUser": {"id": by.lower(), "name": by, "title": "BOT"},
        "speed": speed,
        "declineReasonKey": reason,
        "declineReason": f"text Lichess shows for {reason}",
    }


class TestLeavingBotsAlone(ChallengeLoopTestCase):
    """A challenge is not spent on a bot that just showed it will not play."""

    def challenged(self):
        return [call.args[0] for call in self.client.challenges.create.call_args_list]

    def test_a_bot_that_does_not_answer_is_passed_over_next_time(self):
        self.online = [online_bot("AwayBot", blitz=2000), online_bot("NextBot", blitz=2000)]

        waits = self.run_loop(3)

        self.assertEqual(waits, [90, 30, 90])
        self.assertEqual(self.challenged(), ["AwayBot", "NextBot"])
        self.assertTrue(self.state.rests.resting("AwayBot", "blitz"))

    def test_with_every_suitable_bot_resting_nothing_is_sent_or_counted(self):
        self.state.rests.declined("OtherBot", "blitz", "nobot")

        waits = self.run_loop(2)

        self.assertEqual(waits, [60, 60])
        self.client.challenges.create.assert_not_called()
        self.assertEqual(self.state.tracker.counts(), (0, 0))

    def test_a_bot_that_asks_for_later_is_asked_again_after_a_quarter_of_an_hour(self):
        with patch("bot.threading.Timer"):
            self.send("challengeDeclined", challenge=declined("old00001", "OtherBot", "later"))
        self.assertTrue(self.state.rests.resting("OtherBot", "blitz"))

        clock = [bot.time.time()]
        self.state.rests._clock = lambda: clock[0]
        clock[0] += 15 * 60 + 1

        self.run_loop(1)

        self.assertEqual(self.challenged(), ["OtherBot"])

    def test_a_bot_that_takes_no_bots_is_left_alone_for_a_week(self):
        with patch("bot.threading.Timer"):
            self.send("challengeDeclined", challenge=declined("old00001", "LeelaQueenOdds", "nobot"))

        until, _ = self.state.rests.export()["leelaqueenodds"]
        self.assertAlmostEqual(until - bot.time.time(), 7 * 86400, delta=5)

    def test_a_decline_of_one_speed_leaves_the_other_speeds_open(self):
        with patch("bot.threading.Timer"):
            self.send("challengeDeclined", challenge=declined("old00001", "OtherBot", "toofast", speed="bullet"))

        self.assertTrue(self.state.rests.resting("OtherBot", "bullet"))
        self.run_loop(1)                        # the loop offers 5+3, which is blitz

        self.assertEqual(self.challenged(), ["OtherBot"])

    def test_a_decline_is_recorded_even_after_the_bot_has_moved_on(self):
        """The answer can come after the 90 seconds; it still says something about that bot."""
        self.state.pending_challenge.update(id="newer001", opponent="NextBot", speed="blitz", sent_at=0.0)

        with patch("bot.threading.Timer"):
            self.send("challengeDeclined", challenge=declined("old00001", "OtherBot", "nobot"))

        self.assertTrue(self.state.rests.resting("OtherBot", "blitz"))
        self.assertEqual(self.state.pending_challenge["id"], "newer001")

    def test_a_bot_that_accepts_is_cleared(self):
        self.state.rests.unanswered("OtherBot")
        self.state.pending_challenge.update(id="chal0001", opponent="OtherBot", speed="blitz", sent_at=0.0)

        self.start_game("chal0001", speed="blitz", opponent={"id": "otherbot", "username": "OtherBot", "rating": 2000})

        self.assertFalse(self.state.rests.resting("OtherBot", "blitz"))

    def test_a_bot_that_comes_with_a_challenge_of_its_own_is_cleared_too(self):
        self.state.rests.unanswered("OtherBot")

        self.start_game("theirs01", speed="rapid", opponent={"id": "otherbot", "username": "OtherBot", "rating": 2000})

        self.assertFalse(self.state.rests.resting("OtherBot", "blitz"))

    def test_a_game_against_the_lichess_computer_changes_nothing(self):
        self.state.rests.unanswered("OtherBot")

        self.start_game("ai000001", speed="blitz", opponent={"id": None, "username": "Stockfish level 3", "ai": 3})

        self.assertTrue(self.state.rests.resting("OtherBot", "blitz"))

    def test_the_bots_own_decline_coming_back_is_held_against_nobody(self):
        """Lichess reports a decline to both sides: this is the bot's own answer to a challenge it got."""
        with patch("bot.threading.Timer") as timer:
            self.send("challengeDeclined",
                      challenge=declined("theirs01", "Axiom_BOT", "later", challenger="OtherBot"))

        self.assertEqual(self.state.rests.export(), {})
        timer.assert_not_called()                # and the challenge loop is not woken for it

    def test_silence_while_the_event_stream_is_down_is_held_against_nobody(self):
        """The answer comes over the event stream, so without it there is nothing to conclude."""
        self.state.pending_challenge.update(id="mine0001", opponent="OtherBot", speed="blitz",
                                            sent_at=bot.time.monotonic() - 100)
        self.stream_connected = False

        self.run_loop(1)

        self.client.challenges.cancel.assert_called_once_with("mine0001")
        self.assertFalse(self.state.rests.resting("OtherBot", "blitz"))

    def test_a_bot_at_its_daily_limit_is_left_alone_until_lichess_says(self):
        """Lichess refuses to create the challenge and says for how long."""
        self.client.challenges.create.side_effect = http_error(400, {
            "error": "OtherBot played 100 games against other bots today, please wait until tomorrow to challenge them.",
            "ratelimit": {"key": "bot.vsBot.day", "seconds": 5000},
        })

        waits = self.run_loop(1)

        self.assertEqual(waits, [60])
        until, _ = self.state.rests.export()["otherbot"]
        self.assertAlmostEqual(until - bot.time.time(), 5000, delta=5)
        self.assertEqual(self.state.tracker.counts(), (1, 1))        # Lichess counted the request

    def test_a_bot_that_takes_no_challenges_is_left_alone_for_six_hours(self):
        self.client.challenges.create.side_effect = http_error(400, {"error": "OtherBot does not accept challenges."})

        self.run_loop(1)

        until, _ = self.state.rests.export()["otherbot"]
        self.assertAlmostEqual(until - bot.time.time(), 6 * 3600, delta=5)

    def test_a_bot_that_is_gone_is_left_alone_as_well(self):
        self.client.challenges.create.side_effect = http_error(404, {"error": "Not found"})

        self.run_loop(1)

        self.assertTrue(self.state.rests.resting("OtherBot", "blitz"))

    def test_a_refusal_that_is_about_this_account_is_not_held_against_the_bot_that_was_asked(self):
        for status in (401, 403, 429):
            with self.subTest(status=status):
                self.client.challenges.create.side_effect = http_error(status)

                self.run_loop(1)

                self.assertFalse(self.state.rests.resting("OtherBot", "blitz"))


class TestRemembering(ChallengeLoopTestCase):
    """What the bot writes down, and what the next run makes of it."""

    def setUp(self):
        super().setUp()
        import tempfile
        directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        self.path = os.path.join(directory, "state.json")
        self.state.store = bot.StateFile(self.path)

    def next_run(self):
        state = bot.BotState(client=MagicMock(), username="Axiom_BOT", tracker=bot.ChallengeTracker(5, 100),
                             store=bot.StateFile(self.path))
        state.recall()
        return state

    def test_a_challenge_is_written_down_when_it_is_made(self):
        self.run_loop(1)

        self.assertEqual(len(bot.StateFile(self.path).load()["challenges"]), 1)

    def test_a_refused_attempt_is_written_down_too(self):
        self.client.challenges.create.side_effect = http_error(429)

        self.run_loop(1)

        self.assertEqual(len(bot.StateFile(self.path).load()["challenges"]), 1)

    def test_a_decline_is_written_down_when_it_arrives(self):
        with patch("bot.threading.Timer"):
            self.send("challengeDeclined", challenge=declined("old00001", "OtherBot", "nobot"))

        self.assertIn("otherbot", bot.StateFile(self.path).load()["rests"])

    def test_the_next_run_starts_where_this_one_stopped(self):
        self.run_loop(1)
        with patch("bot.threading.Timer"):
            self.send("challengeDeclined", challenge=declined("chal0001", "OtherBot", "nobot"))

        after_restart = self.next_run()

        self.assertEqual(after_restart.tracker.counts(), (1, 1))
        self.assertTrue(after_restart.rests.resting("OtherBot", "blitz"))

    def test_a_first_run_starts_with_nothing(self):
        state = self.next_run()

        self.assertEqual(state.tracker.counts(), (0, 0))
        self.assertEqual(state.rests.export(), {})

    def test_a_bot_without_a_state_file_just_does_not_remember(self):
        self.state.store = None

        self.run_loop(1)                    # must not raise
        self.state.recall()

        self.assertFalse(os.path.exists(self.path))


class TestRetryAfter(unittest.TestCase):
    def test_seconds_are_read_from_a_named_limit(self):
        exc = http_error(429, {"error": "x", "ratelimit": {"key": "bot.vsBot.day", "seconds": 1234}})
        self.assertEqual(bot._retry_after(exc), 1234)

    def test_the_general_limiter_names_no_time(self):
        self.assertIsNone(bot._retry_after(http_error(429, {"error": "Too many requests. Try again later."})))

    def test_odd_answers_name_no_time(self):
        self.assertIsNone(bot._retry_after(http_error(429, {"error": "x", "ratelimit": {"seconds": 0}})))
        self.assertIsNone(bot._retry_after(http_error(429, {"error": "x", "ratelimit": "soon"})))
        self.assertIsNone(bot._retry_after(http_error(429, ["not", "an", "object"])))
        self.assertIsNone(bot._retry_after(ValueError("not an http answer")))

    def test_challenge_bot_passes_the_time_on(self):
        client = MagicMock()
        client.challenges.create.side_effect = http_error(429, {"error": "x", "ratelimit": {"key": "bot.vsBot.day", "seconds": 77}})

        with self.assertRaises(bot.RateLimitError) as caught:
            bot.challenge_bot(client, "OtherBot", {"limit": 300, "increment": 0})

        self.assertEqual(caught.exception.retry_after, 77)


if __name__ == "__main__":
    unittest.main()
