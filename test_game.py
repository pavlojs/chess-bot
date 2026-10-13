"""
Scenario tests for a game thread: from the first line of the game stream to
the last move, through reconnects, refused moves, draw offers and an engine
that fails.

Lichess is the local stand-in from ``lichess_stub``. The engine is a fake that
plays the first legal move, except in the tests at the end, which run the real
Stockfish binary through the same code.
"""

import json
import os
import unittest
from unittest.mock import patch

import berserk
import chess
from stockfish import StockfishException

os.environ.setdefault('TOKEN', 'test_token_for_testing')

import bot
import config
from lichess_stub import Await, CLOSE, Refuse, STALL, StubLichess, session_with_timeout, within

GAME = "game0001"
STREAM = f"/api/bot/game/stream/{GAME}"
MOVE = f"/api/bot/game/{GAME}/move/"
ME = {"id": "axiom_bot", "name": "Axiom_BOT", "title": "BOT", "rating": 2000}


def opponent(rating=1500):
    return {"id": "opponent", "name": "Opponent", "title": "BOT", "rating": rating}


def first_legal(*moves):
    """The move the fake engine plays after ``moves``."""
    board = chess.Board()
    for move in moves:
        board.push_uci(move)
    return next(iter(board.legal_moves)).uci()


def game_full(moves=(), bot_is="white", rating=1500, status="started", wtime=300000, btime=300000, inc=3000):
    white, black = (ME, opponent(rating)) if bot_is == "white" else (opponent(rating), ME)
    return json.dumps({
        "type": "gameFull", "id": GAME, "rated": True, "speed": "blitz",
        "variant": {"key": "standard"}, "initialFen": "startpos",
        "clock": {"initial": 300000, "increment": inc},
        "white": white, "black": black,
        "state": {"type": "gameState", "moves": " ".join(moves), "status": status,
                  "wtime": wtime, "btime": btime, "winc": inc, "binc": inc},
    }).encode()


def game_state(moves, status="started", wtime=290000, btime=290000, inc=3000, **extra):
    return json.dumps({"type": "gameState", "moves": " ".join(moves), "status": status,
                       "wtime": wtime, "btime": btime, "winc": inc, "binc": inc, **extra}).encode()


class FakeEngine:
    """Stands in for the Stockfish wrapper: plays the first legal move, reports a set evaluation."""

    def __init__(self, score="cp 20"):
        self.score = score
        self.positions = []
        self.searches = []
        self.parameters = []
        self.dead = None        # set to an exception to make every search raise it
        self._stockfish = None
        self._fen = chess.STARTING_FEN

    def set_fen_position(self, fen):
        self._fen = fen
        self.positions.append(fen)

    def _best(self):
        if self.dead is not None:
            raise self.dead
        moves = list(chess.Board(self._fen).legal_moves)
        return moves[0].uci() if moves else None

    def get_best_move_time(self, time=1000):
        self.searches.append(("movetime", time))
        return self._best()

    def get_best_move(self, wtime=None, btime=None):
        raise AssertionError("the bot searches by move time or with its own clock command")

    def _put(self, command):
        self.searches.append(("uci", command))

    def _get_best_move_from_sf_popen_process(self, store_raw_output_for):
        return self._best()

    def raw_stockfish_output(self, func):
        return [f"info depth 10 score {self.score} pv e2e4 e7e5", "bestmove e2e4"]

    def update_engine_parameters(self, parameters):
        self.parameters.append(parameters)

    def get_evaluation(self):
        kind, value = self.score.split()
        return {"type": kind, "value": int(value)}


class GameTestCase(unittest.TestCase):
    def setUp(self):
        self.lichess = StubLichess()
        self.addCleanup(self.lichess.close)
        self.lichess.reply("POST", MOVE + "*")
        self.lichess.reply("POST", f"/api/bot/game/{GAME}/abort")
        self.client = berserk.Client(session_with_timeout((2, 1)), base_url=self.lichess.url)

        self.engines = []
        self.engine_ratings = []
        self.score = "cp 20"

        def new_engine(rating=None):
            self.engine_ratings.append(rating)
            self.engines.append(FakeEngine(self.score))
            return self.engines[-1]

        self.patch("bot.init_stockfish", new_engine)
        self.pauses = []
        self.patch("bot._pause", self.pauses.append)
        self.patch("bot.GAME_WATCHDOG_INTERVAL", 30)
        self.addCleanup(setattr, bot, "shutdown_requested", False)

    def patch(self, target, *args, **kwargs):
        patcher = patch(target, *args, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def stream(self, *steps):
        self.lichess.stream(STREAM, steps)

    def play(self, seconds=15):
        finished, box = within(seconds, lambda: bot.play_game(self.client, GAME, "Axiom_BOT"))
        self.assertTrue(finished, "the game thread did not end")
        self.assertNotIn("error", box)

    def moves_sent(self):
        return [path[len(MOVE):] for path in self.lichess.paths("POST") if path.startswith(MOVE)]

    def posted(self, path):
        return path in self.lichess.paths("POST")


class TestPlayingAGame(GameTestCase):
    def test_as_white_the_bot_opens_and_answers_each_move_until_the_game_ends(self):
        m1 = first_legal()
        m2 = first_legal(m1, "e7e5")
        self.stream(
            game_full(),
            Await("POST", MOVE, 1),
            game_state([m1, "e7e5"]),
            Await("POST", MOVE, 2),
            game_state([m1, "e7e5", m2], status="resign", winner="white"),
        )

        self.play()

        self.assertEqual(self.moves_sent(), [m1, m2])
        self.assertEqual(self.engine_ratings, [1500])

    def test_as_black_the_bot_waits_for_the_first_move(self):
        reply = first_legal("e2e4")
        self.stream(
            game_full(bot_is="black"),
            0.2,
            game_state(["e2e4"]),
            Await("POST", MOVE, 1),
            game_state(["e2e4", reply], status="aborted"),
        )

        self.play()

        self.assertEqual(self.moves_sent(), [reply])

    def test_a_game_joined_in_progress_continues_from_its_position(self):
        played = ["e2e4", "e7e5", "g1f3", "b8c6"]
        expected = first_legal(*played)
        self.stream(
            game_full(moves=played),
            Await("POST", MOVE, 1),
            game_state(played + [expected], status="draw"),
        )

        self.play()

        self.assertEqual(self.moves_sent(), [expected])

    def test_a_game_that_is_already_over_gets_no_move_and_no_engine(self):
        self.stream(game_full(moves=["e2e4", "e7e5"], status="mate"))

        self.play()

        self.assertEqual(self.moves_sent(), [])
        self.assertEqual(self.engines, [])

    def test_the_bots_own_move_echoed_by_lichess_is_not_answered_again(self):
        m1 = first_legal()
        self.stream(
            game_full(),
            Await("POST", MOVE, 1),
            game_state([m1]),                      # only the bot's own move so far
            0.3,
            game_state([m1], status="aborted"),
        )

        self.play()

        self.assertEqual(self.moves_sent(), [m1])

    def test_checkmate_on_the_board_ends_the_thread(self):
        # Fool's mate: after 1.f3 e5 2.g4 the bot, as black, mates with Qh4.
        board_moves = ["f2f3", "e7e5", "g2g4"]
        self.stream(game_full(moves=board_moves, bot_is="black"), Await("POST", MOVE, 1), STALL)
        self.patch("bot.init_stockfish", lambda rating=None: self.mating_engine())

        self.play()

        self.assertEqual(self.moves_sent(), ["d8h4"])

    def mating_engine(self):
        engine = FakeEngine()
        engine._best = lambda: "d8h4"
        self.engines.append(engine)
        return engine

    def test_shutdown_ends_the_thread_at_the_next_event(self):
        m1 = first_legal()
        self.stream(game_full(), Await("POST", MOVE, 1), 0.2, game_state([m1, "e7e5"]), STALL)

        def stop_after_first_move(seconds=None):
            bot.shutdown_requested = True

        with patch.object(self.client.bots, "make_move", side_effect=lambda g, m: (self.lichess_move(m), stop_after_first_move())):
            self.play()

        self.assertEqual(len(self.moves_sent()), 1)

    def lichess_move(self, move):
        berserk.clients.Bots.make_move(self.client.bots, GAME, move)


class TestClocksAndStrength(GameTestCase):
    def test_a_rated_opponent_gets_a_fixed_move_time_capped_by_the_clock(self):
        """Below the full-strength threshold the search is `go movetime`, never the game clock."""
        m1 = first_legal()
        self.stream(
            game_full(rating=1500, wtime=10000, btime=10000, inc=0),
            Await("POST", MOVE, 1),
            game_state([m1], status="aborted"),
        )
        with patch("bot.STOCKFISH_TIME", 3000), patch("bot.MOVETIME_CLOCK_SAFETY", 0.8), \
             patch("bot.MOVETIME_ESTIMATED_MOVES", 40), patch("bot.MOVETIME_MIN_MOVES_LEFT", 10), \
             patch("bot.MOVETIME_MIN_MS", 50), patch("bot.DYNAMIC_STRENGTH", True):
            self.play()

        kind, budget = self.engines[0].searches[0]
        self.assertEqual(kind, "movetime")
        # 40% of 3000 ms would be 1200; ten seconds on the clock over 40 moves allows 200.
        self.assertEqual(budget, int(10000 / 40 * 0.8))

    def test_the_clock_of_a_later_state_is_the_one_used(self):
        """Clocks in gameState lines arrive from berserk as timedeltas."""
        m1 = first_legal()
        m2 = first_legal(m1, "e7e5")
        self.stream(
            game_full(rating=1500, wtime=300000, btime=300000, inc=0),
            Await("POST", MOVE, 1),
            game_state([m1, "e7e5"], wtime=4000, btime=300000, inc=0),
            Await("POST", MOVE, 2),
            game_state([m1, "e7e5", m2], status="aborted"),
        )
        with patch("bot.STOCKFISH_TIME", 3000), patch("bot.MOVETIME_CLOCK_SAFETY", 0.8), \
             patch("bot.MOVETIME_ESTIMATED_MOVES", 40), patch("bot.MOVETIME_MIN_MOVES_LEFT", 10), \
             patch("bot.MOVETIME_MIN_MS", 50), patch("bot.DYNAMIC_STRENGTH", True):
            self.play()

        budgets = [ms for kind, ms in self.engines[0].searches if kind == "movetime"]
        self.assertEqual(budgets[0], 1200)                  # plenty of time: the rating budget
        self.assertEqual(budgets[1], int(4000 / 39 * 0.8))  # four seconds left: the clock decides

    def test_an_opponent_at_full_strength_is_played_on_the_game_clock(self):
        m1 = first_legal()
        self.stream(
            game_full(rating=2900, wtime=180000, btime=170000, inc=2000),
            Await("POST", MOVE, 1),
            game_state([m1], status="aborted"),
        )
        with patch("bot.FULL_STRENGTH_THRESHOLD", 2800), patch("bot.DYNAMIC_STRENGTH", True):
            self.play()

        # The very first move is searched with at most 15 s on the bot's own clock.
        self.assertEqual(self.engines[0].searches[0], ("uci", "go wtime 15000 btime 170000 winc 2000 binc 2000"))

    def test_an_opponent_without_a_rating_is_played_on_the_game_clock(self):
        """Lichess's own AI and anonymous players carry no rating."""
        m1 = first_legal()
        full = json.loads(game_full())
        full["black"] = {"aiLevel": 1}
        self.stream(json.dumps(full).encode(), Await("POST", MOVE, 1), game_state([m1], status="aborted"))

        self.play()

        self.assertEqual(self.engine_ratings, [None])
        self.assertEqual(self.engines[0].searches[0][0], "uci")
        self.assertEqual(self.moves_sent(), [m1])


class TestSpecialSearches(GameTestCase):
    """What the first search finds decides whether the move is searched again, and how."""

    def play_one_move(self, score, rating=1500):
        self.score = score
        m1 = first_legal()
        self.stream(game_full(rating=rating), Await("POST", MOVE, 1), game_state([m1], status="aborted"))
        with patch("bot.STOCKFISH_TIME", 3000), patch("bot.STRENGTH_ADVANTAGE", 100), \
             patch("bot.PREDICTION_RECOVER_THRESHOLD", 400), patch("bot.PREDICTION_RECOVER_ELO_BOOST", 200), \
             patch("bot.FULL_STRENGTH_THRESHOLD", 2800), patch("bot.LIMIT_STRENGTH_THRESHOLD", 1800), \
             patch("bot.DYNAMIC_STRENGTH", True), patch("bot.MOVETIME_MIN_MS", 50):
            self.play()
        self.assertEqual(self.moves_sent(), [m1])
        return self.engines[0]

    def test_an_ordinary_position_is_searched_once_at_the_limited_strength(self):
        engine = self.play_one_move("cp 20")

        self.assertEqual(engine.searches, [("movetime", 1200)])
        self.assertEqual(engine.parameters, [])

    def test_a_mate_for_the_bot_is_searched_again_at_full_strength(self):
        engine = self.play_one_move("mate 3")

        self.assertEqual(len(engine.searches), 2)
        self.assertEqual(engine.parameters, [
            {"UCI_LimitStrength": False},
            {"UCI_LimitStrength": True, "UCI_Elo": 1600},     # and the limit is put back
        ])

    def test_a_mate_against_the_bot_is_defended_at_full_strength(self):
        engine = self.play_one_move("mate -2")

        self.assertEqual(len(engine.searches), 2)
        self.assertEqual(engine.parameters, [
            {"UCI_LimitStrength": False},
            {"UCI_LimitStrength": True, "UCI_Elo": 1600},
        ])

    def test_a_losing_position_is_searched_again_longer_and_a_little_stronger(self):
        engine = self.play_one_move("cp -500")

        # 40% of the base time, then 40% of one and a half times the base time
        self.assertEqual(engine.searches, [("movetime", 1200), ("movetime", 1800)])
        self.assertEqual(engine.parameters, [
            {"UCI_LimitStrength": True, "UCI_Elo": 1800},
            {"UCI_LimitStrength": True, "UCI_Elo": 1600},
        ])

    def test_a_position_just_short_of_losing_is_not_searched_again(self):
        engine = self.play_one_move("cp -399")

        self.assertEqual(len(engine.searches), 1)
        self.assertEqual(engine.parameters, [])

    def test_recovery_against_a_near_elite_opponent_goes_to_full_strength(self):
        """The raised limit would reach the full-strength threshold, so there is nothing left to limit."""
        engine = self.play_one_move("cp -500", rating=2750)

        self.assertEqual(engine.parameters, [
            {"UCI_LimitStrength": False},
            {"UCI_LimitStrength": True, "UCI_Elo": 2850},
        ])


class TestFirstMove(GameTestCase):
    def test_as_black_at_full_strength_the_first_reply_is_capped_on_the_bots_clock(self):
        reply = first_legal("e2e4")
        self.stream(
            game_full(moves=["e2e4"], bot_is="black", rating=2900, wtime=900000, btime=900000, inc=0),
            Await("POST", MOVE, 1),
            game_state(["e2e4", reply], status="aborted"),
        )
        with patch("bot.FULL_STRENGTH_THRESHOLD", 2800), patch("bot.DYNAMIC_STRENGTH", True):
            self.play()

        self.assertEqual(self.engines[0].searches[0], ("uci", "go wtime 900000 btime 15000 winc 0 binc 0"))

    def test_later_moves_are_searched_on_the_real_clock(self):
        played = ["e2e4", "e7e5", "g1f3"]
        reply = first_legal(*played)
        self.stream(
            game_full(moves=played, bot_is="black", rating=2900, wtime=900000, btime=800000, inc=0),
            Await("POST", MOVE, 1),
            game_state(played + [reply], status="aborted"),
        )
        with patch("bot.FULL_STRENGTH_THRESHOLD", 2800), patch("bot.DYNAMIC_STRENGTH", True):
            self.play()

        self.assertEqual(self.engines[0].searches[0], ("uci", "go wtime 900000 btime 800000 winc 0 binc 0"))

    def test_no_abort_timer_runs_when_the_first_move_is_the_bots(self):
        timers = self.patch("bot.threading.Timer")
        m1 = first_legal()
        self.stream(game_full(), Await("POST", MOVE, 1), game_state([m1], status="aborted"))

        self.play()

        timers.assert_not_called()


class TestLosingTheConnection(GameTestCase):
    def test_a_stream_that_goes_silent_is_reopened_and_the_game_goes_on(self):
        m1 = first_legal()
        m2 = first_legal(m1, "e7e5")
        m3 = first_legal(m1, "e7e5", m2, "d7d5")
        self.stream(game_full(), Await("POST", MOVE, 1), game_state([m1, "e7e5"]), Await("POST", MOVE, 2), STALL)
        # Lichess sends the whole game again when the stream is reopened.
        self.stream(
            game_full(moves=[m1, "e7e5", m2, "d7d5"]),
            Await("POST", MOVE, 3),
            game_state([m1, "e7e5", m2, "d7d5", m3], status="outoftime"),
        )

        self.play()

        self.assertEqual(self.moves_sent(), [m1, m2, m3])
        self.assertEqual(self.lichess.paths("GET").count(STREAM), 2)
        self.assertEqual(self.pauses, [5])
        self.assertEqual(len(self.engines), 2)      # a fresh engine for the reread game

    def test_a_reopened_stream_on_the_opponents_turn_sends_no_move(self):
        m1 = first_legal()
        self.stream(game_full(), Await("POST", MOVE, 1), STALL)
        self.stream(game_full(moves=[m1]), 0.3, game_state([m1], status="aborted"))

        self.play()

        self.assertEqual(self.moves_sent(), [m1])

    def test_a_gateway_error_on_the_stream_is_retried(self):
        m1 = first_legal()
        self.stream(Refuse(502, {"error": "Bad gateway"}))
        self.stream(Refuse(503, {"error": "Unavailable"}))
        self.stream(game_full(), Await("POST", MOVE, 1), game_state([m1], status="aborted"))

        self.play()

        self.assertEqual(self.moves_sent(), [m1])
        self.assertEqual(self.pauses, [5, 5])

    def test_a_rate_limit_on_the_stream_waits_a_minute(self):
        self.stream(Refuse(429, {"error": "Too many requests"}))
        self.stream(game_full(moves=["e2e4"], status="aborted"))

        self.play()

        self.assertEqual(self.pauses, [60])

    def test_a_game_lichess_does_not_know_ends_the_thread(self):
        self.stream(Refuse(404, {"error": "No such game"}))

        self.play()

        self.assertEqual(self.lichess.paths("GET").count(STREAM), 1)
        self.assertEqual(self.pauses, [])

    def test_a_move_that_cannot_be_delivered_is_retried_then_the_game_is_reread(self):
        m1 = first_legal()
        self.lichess.stream(MOVE + m1, [STALL])      # three attempts that are never answered
        self.lichess.stream(MOVE + m1, [STALL])
        self.lichess.stream(MOVE + m1, [STALL])
        self.stream(game_full(), STALL)
        self.stream(game_full(), Await("POST", MOVE, 4), game_state([m1], status="aborted"))

        self.play(seconds=30)

        self.assertEqual(self.moves_sent(), [m1] * 4)
        self.assertEqual(self.pauses, [2, 4, 5])     # between attempts, then before rereading


class TestMoveRefused(GameTestCase):
    def refuse_moves(self, times, message="Not your turn, or game already over"):
        self.lichess._server.replies.pop(("POST", MOVE + "*"))
        for _ in range(times):
            self.lichess.reply("POST", MOVE + "*", 400, {"error": message})
        self.lichess.reply("POST", MOVE + "*")

    def test_a_refusal_because_the_game_ended_closes_the_thread_quietly(self):
        """The opponent resigned while the engine was thinking."""
        self.refuse_moves(1)
        self.stream(game_full(), STALL)
        self.stream(game_full(status="resign"))

        self.play()

        self.assertEqual(len(self.moves_sent()), 1)
        self.assertEqual(self.pauses, [1])

    def test_a_move_that_did_arrive_is_not_played_twice(self):
        """The answer to the first attempt was lost; the retry is refused; the game goes on."""
        m1 = first_legal()
        m2 = first_legal(m1, "e7e5")
        self.refuse_moves(1)
        self.stream(game_full(), STALL)
        self.stream(
            game_full(moves=[m1, "e7e5"]),          # Lichess has the move, and the reply to it
            Await("POST", MOVE, 2),
            game_state([m1, "e7e5", m2], status="aborted"),
        )

        self.play()

        self.assertEqual(self.moves_sent(), [m1, m2])

    def test_a_board_out_of_step_is_corrected_from_lichess(self):
        self.refuse_moves(1, "Piece on g1 cannot move to h3")
        true_position = ["d2d4", "d7d5"]
        expected = first_legal(*true_position)
        self.stream(game_full(), STALL)
        self.stream(game_full(moves=true_position), Await("POST", MOVE, 2), game_state(true_position + [expected], status="aborted"))

        self.play()

        self.assertEqual(self.moves_sent()[-1], expected)

    def test_refusal_after_refusal_gives_up_instead_of_hammering_lichess(self):
        self.refuse_moves(50)
        for _ in range(10):
            self.stream(game_full(), STALL)

        self.play()

        self.assertEqual(len(self.moves_sent()), bot.MAX_RESYNCS + 1)
        self.assertEqual(self.lichess.paths("GET").count(STREAM), bot.MAX_RESYNCS + 1)


class TestEngineTrouble(GameTestCase):
    def test_an_engine_that_cannot_start_aborts_a_game_with_no_moves(self):
        def broken(rating=None):
            raise FileNotFoundError("stockfish not found")

        self.patch("bot.init_stockfish", broken)
        self.stream(game_full(), STALL)

        self.play()

        self.assertEqual(self.moves_sent(), [])
        self.assertTrue(self.posted(f"/api/bot/game/{GAME}/abort"))

    def test_an_engine_that_cannot_start_leaves_a_game_under_way_alone(self):
        def broken(rating=None):
            raise FileNotFoundError("stockfish not found")

        self.patch("bot.init_stockfish", broken)
        self.stream(game_full(moves=["e2e4", "e7e5", "g1f3", "b8c6"]), STALL)

        self.play()

        self.assertFalse(self.posted(f"/api/bot/game/{GAME}/abort"))

    def test_an_engine_that_dies_mid_game_is_replaced_and_the_move_is_made(self):
        m1 = first_legal()
        self.stream(game_full(), STALL)
        self.stream(game_full(), Await("POST", MOVE, 1), game_state([m1], status="aborted"))

        def dying_then_fine(rating=None):
            engine = FakeEngine()
            if not self.engines:
                engine.dead = StockfishException("The Stockfish process has crashed")
            self.engines.append(engine)
            return engine

        self.patch("bot.init_stockfish", dying_then_fine)

        self.play()

        self.assertEqual(self.moves_sent(), [m1])
        self.assertEqual(len(self.engines), 2)
        self.assertEqual(self.pauses, [1])


class TestDrawOffersInAGame(GameTestCase):
    def offer_draw_after_first_move(self):
        m1 = first_legal()
        m2 = first_legal(m1, "e7e5")
        self.lichess.reply("POST", f"/api/bot/game/{GAME}/draw/yes")
        self.lichess.reply("POST", f"/api/bot/game/{GAME}/draw/no")
        self.stream(
            game_full(),
            Await("POST", MOVE, 1),
            game_state([m1, "e7e5"], bdraw=True),
            Await("POST", MOVE, 2),
            game_state([m1, "e7e5", m2], status="aborted"),
        )

    def test_a_draw_offered_in_a_level_position_is_accepted(self):
        self.score = "cp 20"
        self.offer_draw_after_first_move()

        self.play()

        self.assertTrue(self.posted(f"/api/bot/game/{GAME}/draw/yes"))

    def test_a_draw_offered_when_the_bot_is_ahead_is_declined(self):
        self.score = "cp 450"
        self.offer_draw_after_first_move()

        self.play()

        self.assertTrue(self.posted(f"/api/bot/game/{GAME}/draw/no"))
        self.assertFalse(self.posted(f"/api/bot/game/{GAME}/draw/yes"))

    def test_a_draw_offered_with_a_mate_on_the_board_is_declined(self):
        self.score = "mate 3"
        self.offer_draw_after_first_move()

        self.play()

        self.assertTrue(self.posted(f"/api/bot/game/{GAME}/draw/no"))

    def test_the_bots_own_draw_flag_is_not_an_offer_to_answer(self):
        m1 = first_legal()
        self.stream(game_full(), Await("POST", MOVE, 1), game_state([m1], wdraw=True), 0.2, game_state([m1], status="aborted"))

        self.play()

        self.assertFalse(any("/draw/" in path for path in self.lichess.paths("POST")))

    def test_a_standing_offer_is_answered_once(self):
        m1 = first_legal()
        m2 = first_legal(m1, "e7e5")
        self.lichess.reply("POST", f"/api/bot/game/{GAME}/draw/yes")
        self.stream(
            game_full(),
            Await("POST", MOVE, 1),
            game_state([m1, "e7e5"], bdraw=True),
            Await("POST", MOVE, 2),
            game_state([m1, "e7e5", m2], bdraw=True),
            0.2,
            game_state([m1, "e7e5", m2], status="aborted"),
        )

        self.play()

        self.assertEqual(sum("/draw/" in path for path in self.lichess.paths("POST")), 1)


class TestOpponentLeaving(GameTestCase):
    def test_the_win_is_claimed_once_lichess_allows_it(self):
        self.lichess.reply("POST", f"/api/bot/game/{GAME}/claim-victory")
        self.stream(
            game_full(moves=["e2e4"], bot_is="white"),
            json.dumps({"type": "opponentGone", "gone": True, "claimWinInSeconds": 0}).encode(),
            Await("POST", f"/api/bot/game/{GAME}/claim-victory"),
            game_state(["e2e4"], status="timeout"),
        )

        self.play()

        self.assertTrue(self.posted(f"/api/bot/game/{GAME}/claim-victory"))

    def test_an_opponent_who_comes_back_is_not_claimed_against(self):
        self.lichess.reply("POST", f"/api/bot/game/{GAME}/claim-victory")
        self.stream(
            game_full(moves=["e2e4"], bot_is="white"),
            json.dumps({"type": "opponentGone", "gone": True, "claimWinInSeconds": 1}).encode(),
            json.dumps({"type": "opponentGone", "gone": False}).encode(),
            2.5,
            game_state(["e2e4"], status="aborted"),
        )

        self.play()

        self.assertFalse(self.posted(f"/api/bot/game/{GAME}/claim-victory"))

    def test_a_game_the_opponent_never_starts_is_aborted(self):
        timers = []

        class ImmediateTimer:
            def __init__(self, interval, function):
                timers.append(interval)
                self.function = function
                self.daemon = True

            def start(self):
                self.function()

            def cancel(self):
                pass

        self.patch("bot.threading.Timer", ImmediateTimer)
        self.stream(game_full(bot_is="black"), Await("POST", f"/api/bot/game/{GAME}/abort"), game_state([], status="aborted"))

        self.play()

        self.assertEqual(timers, [120.0])
        self.assertTrue(self.posted(f"/api/bot/game/{GAME}/abort"))


@unittest.skipUnless(os.path.isfile(config.STOCKFISH_PATH) and os.access(config.STOCKFISH_PATH, os.X_OK),
                     "needs a Stockfish binary")
class TestWithTheRealEngine(unittest.TestCase):
    """The same game thread with the real Stockfish, so the wrapper calls the bot relies on are exercised."""

    def setUp(self):
        self.lichess = StubLichess()
        self.addCleanup(self.lichess.close)
        self.lichess.reply("POST", MOVE + "*")
        self.client = berserk.Client(session_with_timeout((2, 5)), base_url=self.lichess.url)
        for target, value in {
            "bot.UCI_OPTIONS": {"Threads": 1, "Hash": 16, "UCI_LimitStrength": False, "Move Overhead": 30, "Ponder": False},
            "bot.STOCKFISH_TIME": 250,
            "bot.DYNAMIC_STRENGTH": True,
            "bot._pause": lambda seconds: None,
        }.items():
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def play(self):
        finished, box = within(60, lambda: bot.play_game(self.client, GAME, "Axiom_BOT"))
        self.assertTrue(finished, "the game thread did not end")
        self.assertNotIn("error", box)

    def moves_sent(self):
        return [path[len(MOVE):] for path in self.lichess.paths("POST") if path.startswith(MOVE)]

    def assert_legal(self, played_before, move):
        board = chess.Board()
        for earlier in played_before:
            board.push_uci(earlier)
        self.assertIn(chess.Move.from_uci(move), board.legal_moves)

    def test_a_limited_strength_game_gets_a_legal_first_move(self):
        self.lichess.stream(STREAM, [game_full(rating=1500), Await("POST", MOVE, 1), 0.2, CLOSE])

        self.play()

        (move,) = self.moves_sent()
        self.assert_legal([], move)

    def test_a_full_strength_game_on_the_clock_gets_a_legal_reply(self):
        self.lichess.stream(STREAM, [
            game_full(moves=["e2e4"], bot_is="black", rating=2900, wtime=3000, btime=3000, inc=0),
            Await("POST", MOVE, 1), 0.2, CLOSE,
        ])

        self.play()

        (move,) = self.moves_sent()
        self.assert_legal(["e2e4"], move)

    def test_a_forced_mate_is_found_and_played(self):
        """Back-rank mate in one for white: Rd8#."""
        # 1.e4 e5 ... is not needed: a position is reached by moves, so use a short forced line instead.
        engine = bot.init_stockfish(1500)
        self.addCleanup(engine._stockfish.kill)
        engine.set_fen_position("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")

        move, mate, cp = bot.get_move_prediction(engine, GAME, move_time_ms=300)

        self.assertEqual(mate, 1)
        self.assertEqual(cp, 30000)
        full_power = bot._get_full_power_move(engine, GAME, 300, restore_elo=1650)
        self.assertEqual(full_power, "d1d8")

    def test_the_evaluation_of_the_last_search_can_be_read_back(self):
        engine = bot.init_stockfish(None)
        self.addCleanup(engine._stockfish.kill)
        engine.set_fen_position(chess.STARTING_FEN)

        move = bot._get_best_move_with_clocks(engine, 2000, 2000, 0, 0)
        cp = bot._get_last_eval_cp(engine)

        self.assertIn(chess.Move.from_uci(move), chess.Board().legal_moves)
        self.assertIsInstance(cp, int)
        self.assertLess(abs(cp), 300)

    def test_strength_limit_is_set_from_the_opponents_rating(self):
        with patch("bot.STRENGTH_ADVANTAGE", 100):
            weak = bot.init_stockfish(1000)       # below the engine's floor
            mid = bot.init_stockfish(2000)
            elite = bot.init_stockfish(2900)
        for engine in (weak, mid, elite):
            self.addCleanup(engine._stockfish.kill)

        self.assertEqual(weak.get_engine_parameters()["UCI_Elo"], 1320)
        self.assertEqual(mid.get_engine_parameters()["UCI_Elo"], 2100)
        self.assertTrue(mid.get_engine_parameters()["UCI_LimitStrength"])
        self.assertFalse(elite.get_engine_parameters()["UCI_LimitStrength"])


if __name__ == "__main__":
    unittest.main()
