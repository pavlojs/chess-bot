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

        self.client = MagicMock()
        self.state = bot.BotState(
            client=self.client,
            username="Axiom_BOT",
            tracker=bot.ChallengeTracker(5),
        )

    def send(self, kind, **payload):
        bot.handle_event({"type": kind, **payload}, self.state)

    def start_game(self, game_id):
        self.send("gameStart", game={"id": game_id})
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

    def test_game_start_clears_the_pending_challenge_and_wakes_the_challenge_loop(self):
        self.state.pending_challenge.update(id="chal0001", opponent="otherbot", sent_at=0.0)

        self.start_game("game0001")

        self.assertEqual(self.state.pending_challenge, {})
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


def http_error(status):
    import requests
    import berserk
    response = requests.Response()
    response.status_code = status
    response.reason = "error"
    response._content = b'{"error":"x"}'
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

        self.client.bots.decline_challenge.assert_called_once_with("chal0001")
        self.client.bots.accept_challenge.assert_not_called()

    def test_a_variant_challenge_is_declined(self):
        self.send("challenge", challenge=incoming("chal0001", variant="chess960"))

        self.client.bots.decline_challenge.assert_called_once_with("chal0001")

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
            # start_game cleared the pending challenge as "accepted"; set it again
            self.state.pending_challenge.update(id="mine0001", opponent="slowbot", sent_at=0.0)
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


if __name__ == "__main__":
    unittest.main()
