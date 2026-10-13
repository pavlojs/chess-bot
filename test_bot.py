"""
Unit tests for Axiom Chess Bot
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import timedelta
import os
import threading

import chess

# Mock TOKEN before importing bot
os.environ.setdefault('TOKEN', 'test_token_for_testing')

from bot import should_accept_challenge, init_stockfish


class TestChallengeAcceptance(unittest.TestCase):
    """Test challenge acceptance logic."""
    
    def test_accept_challenge_valid_rating_and_timecontrol(self):
        """Test that valid challenges are accepted."""
        challenge = {
            'challenger': {'rating': 1500},
            'timeControl': {'limit': 180, 'increment': 0},
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            result = should_accept_challenge(challenge)
            self.assertTrue(result)
    
    def test_reject_challenge_rating_too_low(self):
        """Test that challenges below minimum rating are rejected."""
        challenge = {
            'challenger': {'rating': 900},
            'timeControl': {'limit': 180, 'increment': 0},
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            result = should_accept_challenge(challenge)
            self.assertFalse(result)
    
    def test_reject_challenge_rating_too_high(self):
        """Test that challenges above maximum rating are rejected."""
        challenge = {
            'challenger': {'rating': 2500},
            'timeControl': {'limit': 180, 'increment': 0},
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            result = should_accept_challenge(challenge)
            self.assertFalse(result)
    
    def test_reject_challenge_unsupported_timecontrol(self):
        """Test that unsupported time controls are rejected."""
        challenge = {
            'challenger': {'rating': 1500},
            'timeControl': {'limit': 60, 'increment': 0},
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            result = should_accept_challenge(challenge)
            self.assertFalse(result)
    
    def test_reject_when_challenges_disabled(self):
        """Test that challenges are rejected when ACCEPT_CHALLENGES is False."""
        challenge = {
            'challenger': {'rating': 1500},
            'timeControl': {'limit': 180, 'increment': 0},
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', False):
            result = should_accept_challenge(challenge)
            self.assertFalse(result)
    
    def test_handle_missing_rating(self):
        """Test that default rating is used when rating is missing."""
        challenge = {
            'challenger': {},
            'timeControl': {'limit': 180, 'increment': 0},
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            # Default rating is 1500, should be accepted
            result = should_accept_challenge(challenge)
            self.assertTrue(result)
    
    def test_accept_challenge_classical_timecontrol(self):
        """Test that classical time control challenges are accepted."""
        challenge = {
            'challenger': {'rating': 1800},
            'timeControl': {'limit': 1800, 'increment': 0},
            'speed': 'classical',
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            result = should_accept_challenge(challenge)
            self.assertTrue(result)
    
    def test_reject_correspondence_challenge(self):
        """Test that correspondence challenges are rejected."""
        challenge = {
            'challenger': {'rating': 1500},
            'timeControl': {'limit': 259200, 'increment': 0},
            'speed': 'correspondence',
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['bullet', 'blitz', 'rapid', 'classical']):
            result = should_accept_challenge(challenge)
            self.assertFalse(result)
    
    def test_reject_unlimited_time_challenge(self):
        """Test that unlimited time challenges are rejected."""
        challenge = {
            'challenger': {'rating': 1500},
            'timeControl': {'limit': 0, 'increment': 0},
            'speed': 'unlimited',
            'id': 'test123'
        }
        
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['bullet', 'blitz', 'rapid', 'classical']):
            result = should_accept_challenge(challenge)
            self.assertFalse(result)


class TestStockfishInitialization(unittest.TestCase):
    """Test Stockfish engine initialization."""
    
    @patch('bot.Stockfish')
    @patch('bot.STOCKFISH_PATH', '/usr/local/bin/stockfish')
    def test_stockfish_initialization_success(self, mock_stockfish_class):
        """Test successful Stockfish initialization without dynamic strength."""
        mock_sf_instance = Mock()
        mock_stockfish_class.return_value = mock_sf_instance
        
        with patch('bot.DYNAMIC_STRENGTH', False):
            result = init_stockfish()
        
        # Verify Stockfish was called with correct parameters
        mock_stockfish_class.assert_called_once()
        self.assertIsNotNone(result)
    
    @patch('bot.Stockfish')
    @patch('bot.STOCKFISH_PATH', '/usr/local/bin/stockfish')
    def test_stockfish_initialization_weak_opponent(self, mock_stockfish_class):
        """Test Stockfish initialization with weak opponent - uses UCI_LimitStrength."""
        mock_sf_instance = Mock()
        mock_stockfish_class.return_value = mock_sf_instance
        
        with patch('bot.DYNAMIC_STRENGTH', True), \
             patch('bot.LIMIT_STRENGTH_THRESHOLD', 1800), \
             patch('bot.STRENGTH_ADVANTAGE', 100):
            result = init_stockfish(opponent_rating=1500)
        
        # Verify that UCI_LimitStrength IS used for weak opponents
        mock_sf_instance.update_engine_parameters.assert_called_once_with({
            'UCI_LimitStrength': True,
            'UCI_Elo': 1600,
        })
        self.assertIsNotNone(result)
    
    @patch('bot.Stockfish')
    @patch('bot.STOCKFISH_PATH', '/usr/local/bin/stockfish')
    def test_stockfish_initialization_intermediate_opponent(self, mock_stockfish_class):
        """Test Stockfish init with intermediate opponent (1800-2799).
        
        UCI_LimitStrength must be set (go movetime is required with UCI_LimitStrength;
        native clocks would cause Stockfish to time-manage as a limited human
        and potentially hang 30+ seconds, triggering Lichess game abort).
        """
        mock_sf_instance = Mock()
        mock_stockfish_class.return_value = mock_sf_instance

        with patch('bot.DYNAMIC_STRENGTH', True), \
             patch('bot.LIMIT_STRENGTH_THRESHOLD', 1800), \
             patch('bot.FULL_STRENGTH_THRESHOLD', 2800), \
             patch('bot.STRENGTH_ADVANTAGE', 100):
            result = init_stockfish(opponent_rating=2200)

        # Intermediate opponents (1800-2799) should also get UCI_LimitStrength at opponent+100
        mock_sf_instance.update_engine_parameters.assert_called_once_with({
            'UCI_LimitStrength': True,
            'UCI_Elo': 2300,
        })
        self.assertIsNotNone(result)

    @patch('bot.Stockfish')
    @patch('bot.STOCKFISH_PATH', '/usr/local/bin/stockfish')
    def test_stockfish_initialization_elite_opponent(self, mock_stockfish_class):
        """Test Stockfish initialization with elite opponent (>= 2800) — full strength, no limit."""
        mock_sf_instance = Mock()
        mock_stockfish_class.return_value = mock_sf_instance

        with patch('bot.DYNAMIC_STRENGTH', True), \
             patch('bot.LIMIT_STRENGTH_THRESHOLD', 1800), \
             patch('bot.FULL_STRENGTH_THRESHOLD', 2800):
            result = init_stockfish(opponent_rating=3000)

        # Elite opponents (>= FULL_STRENGTH_THRESHOLD) get full power — no parameter changes
        mock_sf_instance.update_engine_parameters.assert_not_called()
        self.assertIsNotNone(result)


class TestMoveTimeCalculation(unittest.TestCase):
    """Test hybrid dynamic move time calculation based on opponent rating."""
    
    @patch('bot.STOCKFISH_TIME', 3000)
    @patch('bot.LIMIT_STRENGTH_THRESHOLD', 1800)
    @patch('bot.FULL_STRENGTH_THRESHOLD', 2200)
    def test_full_time_for_strong_opponents(self):
        """Test that strong opponents (2200+) get full thinking time."""
        from bot import calculate_move_time
        
        with patch('bot.DYNAMIC_STRENGTH', True):
            # Strong opponents should get 100% time
            time_2200 = calculate_move_time(2200, 3000)
            time_2500 = calculate_move_time(2500, 3000)
            time_2800 = calculate_move_time(2800, 3000)
            
            self.assertEqual(time_2200, 3000)
            self.assertEqual(time_2500, 3000)
            self.assertEqual(time_2800, 3000)
    
    @patch('bot.STOCKFISH_TIME', 3000)
    @patch('bot.LIMIT_STRENGTH_THRESHOLD', 1800)
    @patch('bot.FULL_STRENGTH_THRESHOLD', 2200)
    def test_reduced_time_for_weak_opponents(self):
        """Test that weak opponents (< 1800) get minimum time (UCI_LimitStrength handles fairness)."""
        from bot import calculate_move_time
        
        with patch('bot.DYNAMIC_STRENGTH', True):
            # Weak opponents get 40% time (UCI_LimitStrength makes it fair)
            time_1200 = calculate_move_time(1200, 3000)
            time_1500 = calculate_move_time(1500, 3000)
            time_1700 = calculate_move_time(1700, 3000)
            
            # All should get 40% = 1200ms
            self.assertEqual(time_1200, 1200)
            self.assertEqual(time_1500, 1200)
            self.assertEqual(time_1700, 1200)
    
    @patch('bot.STOCKFISH_TIME', 3000)
    @patch('bot.LIMIT_STRENGTH_THRESHOLD', 1800)
    @patch('bot.FULL_STRENGTH_THRESHOLD', 2200)
    def test_scaled_time_for_intermediate_opponents(self):
        """Test that intermediate opponents (1800-2199) get scaled time."""
        from bot import calculate_move_time
        
        with patch('bot.DYNAMIC_STRENGTH', True):
            # Intermediate opponents get 40-95% time with full strength
            time_1800 = calculate_move_time(1800, 3000)  # 40%
            time_2000 = calculate_move_time(2000, 3000)  # ~67.5%
            time_2100 = calculate_move_time(2100, 3000)  # ~81%
            
            self.assertEqual(time_1800, 1200)  # 40%
            self.assertGreater(time_2000, 1900)  # More than 63%
            self.assertLess(time_2000, 2100)  # Less than 70%
            self.assertGreater(time_2100, 2300)  # More than 76%
            self.assertLess(time_2100, 2500)  # Less than 83%
    
    @patch('bot.STOCKFISH_TIME', 3000)
    def test_disabled_dynamic_strength(self):
        """Test that dynamic strength can be disabled."""
        from bot import calculate_move_time
        
        with patch('bot.DYNAMIC_STRENGTH', False):
            # Should always return base time when disabled
            time_1500 = calculate_move_time(1500, 3000)
            time_2500 = calculate_move_time(2500, 3000)
            
            self.assertEqual(time_1500, 3000)
            self.assertEqual(time_2500, 3000)


class TestGameEndReason(unittest.TestCase):
    """Test game end reason detection."""
    
    def test_checkmate_white_wins(self):
        """Test checkmate detection - white wins."""
        from bot import get_game_end_reason
        
        # Fool's mate: 1. f3 e6 2. g4 Qh4# - Black wins
        board = chess.Board()
        moves = ['f2f3', 'e7e6', 'g2g4', 'd8h4']
        for move in moves:
            board.push_uci(move)
        
        reason = get_game_end_reason(board)
        self.assertIn("checkmate", reason.lower())
        self.assertIn("black wins", reason.lower())
    
    def test_stalemate(self):
        """Test stalemate detection."""
        from bot import get_game_end_reason
        
        # Create a proper stalemate position:
        # White King on h6, White Queen on g6
        # Black King on h8 - Black to move is stalemate
        board = chess.Board()
        board.clear()
        board.set_piece_at(chess.H6, chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(chess.G6, chess.Piece(chess.QUEEN, chess.WHITE))
        board.set_piece_at(chess.H8, chess.Piece(chess.KING, chess.BLACK))
        board.turn = chess.BLACK
        
        # Verify it's stalemate
        self.assertTrue(board.is_stalemate(), f"Position is not stalemate. Legal moves: {list(board.legal_moves)}")
        
        reason = get_game_end_reason(board)
        self.assertEqual(reason, "draw by stalemate")
    
    def test_insufficient_material(self):
        """Test insufficient material detection."""
        from bot import get_game_end_reason
        
        # King vs King
        board = chess.Board()
        board.clear()
        board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
        
        # Verify insufficient material
        self.assertTrue(board.is_insufficient_material())
        
        reason = get_game_end_reason(board)
        self.assertEqual(reason, "draw by insufficient material")
    
    def test_threefold_repetition(self):
        """Test threefold repetition detection."""
        from bot import get_game_end_reason
        
        board = chess.Board()
        
        # Repeat moves 3 times to trigger threefold repetition
        # White knight moves: Nf3-g1-f3-g1-f3-g1
        moves = ['g1f3', 'g8f6', 'f3g1', 'f6g8', 
                 'g1f3', 'g8f6', 'f3g1', 'f6g8',
                 'g1f3', 'g8f6', 'f3g1', 'f6g8']
        
        for move in moves:
            board.push_uci(move)
        
        # Should be able to claim threefold repetition
        if board.can_claim_threefold_repetition():
            reason = get_game_end_reason(board)
            self.assertIn("threefold repetition", reason.lower())
    
    def test_fifty_move_rule(self):
        """Test fifty-move rule detection."""
        from bot import get_game_end_reason
        
        board = chess.Board()
        # Manually set halfmove clock to 100 (50 moves by each side)
        board.halfmove_clock = 100
        
        if board.can_claim_fifty_moves():
            reason = get_game_end_reason(board)
            self.assertIn("fifty-move rule", reason.lower())


class TestLogging(unittest.TestCase):
    """Test logging configuration."""
    
    def test_logger_setup(self):
        """Test that logger is properly configured."""
        from logging_config import setup_logger
        
        logger = setup_logger(__name__)
        
        # Verify logger exists and has handlers
        self.assertIsNotNone(logger)
        self.assertGreater(len(logger.handlers), 0)


class TestChallengeTracker(unittest.TestCase):
    """Test challenge tracker functionality."""
    
    def setUp(self):
        self.now = 10_000.0

    def tracker(self, per_hour=3, per_day=100):
        from bot import ChallengeTracker
        return ChallengeTracker(max_per_hour=per_hour, max_per_day=per_day, clock=lambda: self.now)

    def test_initial_state(self):
        tracker = self.tracker()

        self.assertTrue(tracker.can_challenge())
        self.assertEqual(tracker.get_remaining_challenges(), 3)
        self.assertEqual(tracker.seconds_until_free(), 0)
        self.assertEqual(tracker.counts(), (0, 0))

    def test_hourly_limit(self):
        tracker = self.tracker(per_hour=3)
        for expected_left in (2, 1, 0):
            tracker.record_challenge()
            self.assertEqual(tracker.get_remaining_challenges(), expected_left)
            self.now += 60

        self.assertFalse(tracker.can_challenge())
        # Three attempts at t, t+60, t+120; now t+180. The first leaves the hour at t+3600.
        self.assertEqual(tracker.seconds_until_free(), 3600 - 180)

    def test_an_attempt_leaves_the_hour_after_sixty_minutes(self):
        tracker = self.tracker(per_hour=1)
        tracker.record_challenge()

        self.now += 3599
        self.assertFalse(tracker.can_challenge())
        self.now += 1
        self.assertTrue(tracker.can_challenge())
        self.assertEqual(tracker.counts(), (0, 1))

    def test_daily_limit_holds_when_the_hourly_one_does_not(self):
        """10 an hour is 240 a day: the daily limit has to stop it at its own number."""
        tracker = self.tracker(per_hour=10, per_day=180)
        sent = 0
        for minute in range(24 * 60):      # one day, minute by minute
            if tracker.can_challenge():
                tracker.record_challenge()
                sent += 1
            if minute < 24 * 60 - 1:
                self.now += 60

        # 23h59 after the first attempt: all 180 are still inside the day.
        self.assertEqual(sent, 180)
        self.assertFalse(tracker.can_challenge())
        self.assertEqual(tracker.seconds_until_free(), 60)

    def test_no_window_of_a_day_ever_exceeds_the_daily_limit(self):
        tracker = self.tracker(per_hour=10, per_day=180)
        times = []
        for _ in range(3 * 24 * 60):       # three days
            if tracker.can_challenge():
                tracker.record_challenge()
                times.append(self.now)
            self.now += 60

        worst = max(sum(1 for t in times if start <= t < start + 86400) for start in times)
        self.assertLessEqual(worst, 180)
        self.assertGreater(len(times), 360)    # and it does keep going on later days

    def test_wait_time_is_exact_for_the_daily_limit(self):
        tracker = self.tracker(per_hour=100, per_day=2)
        tracker.record_challenge()
        self.now += 100
        tracker.record_challenge()
        self.now += 100

        # Two attempts at t and t+100; now t+200. The first leaves the day at t+86400.
        self.assertEqual(tracker.seconds_until_free(), 86400 - 200)
        self.now += 86400 - 200
        self.assertTrue(tracker.can_challenge())

    def test_a_limit_of_zero_never_allows_a_challenge(self):
        tracker = self.tracker(per_hour=0)

        self.assertFalse(tracker.can_challenge())
        self.assertGreater(tracker.seconds_until_free(), 0)


class TestFilterSuitableBots(unittest.TestCase):
    """Opponents are chosen by their rating in the kind of game being offered."""

    def names(self, bots, speed, low=1500, high=2900, me="Axiom_BOT"):
        from bot import filter_suitable_bots
        return [b["username"] for b in filter_suitable_bots(bots, low, high, me, speed)]

    def bot(self, name, **ratings):
        return {"username": name, "perfs": {speed: {"rating": rating} for speed, rating in ratings.items()}}

    def test_rating_range_is_inclusive(self):
        bots = [
            self.bot("low", blitz=1499),
            self.bot("floor", blitz=1500),
            self.bot("mid", blitz=2200),
            self.bot("ceiling", blitz=2900),
            self.bot("high", blitz=2901),
        ]

        self.assertEqual(self.names(bots, "blitz"), ["floor", "mid", "ceiling"])

    def test_the_bot_never_picks_itself(self):
        bots = [self.bot("axiom_bot", blitz=2000), self.bot("other", blitz=2000)]

        self.assertEqual(self.names(bots, "blitz"), ["other"])

    def test_only_the_rating_of_the_speed_being_played_counts(self):
        """Rated 2000 in blitz and 900 in bullet: a 900 opponent in a bullet game."""
        bots = [self.bot("specialist", blitz=2000, bullet=900, rapid=1700)]

        self.assertEqual(self.names(bots, "blitz"), ["specialist"])
        self.assertEqual(self.names(bots, "rapid"), ["specialist"])
        self.assertEqual(self.names(bots, "bullet"), [])

    def test_a_bot_without_a_rating_at_that_speed_is_skipped(self):
        bots = [self.bot("blitz_only", blitz=2000), {"username": "no_perfs"}]

        self.assertEqual(self.names(bots, "classical"), [])

    def test_the_speed_follows_the_time_control_that_was_drawn(self):
        """try_challenge_random_bot must look at the rating for the game it offers."""
        import bot
        client = Mock()
        client.bots.get_online_bots.return_value = iter([
            self.bot("BulletWeak", blitz=2000, bullet=900),
            self.bot("BulletFine", blitz=1000, bullet=2000),
        ])
        client.challenges.create.return_value = {"id": "chal0001"}
        tracker = bot.ChallengeTracker(5, 100)

        with patch("bot.ENABLE_AUTO_CHALLENGE", True), \
             patch("bot.CHALLENGE_TIME_CONTROLS", [{"limit": 60, "increment": 0}]), \
             patch("bot.CHALLENGE_MIN_RATING", 1500), patch("bot.CHALLENGE_MAX_RATING", 2900):
            result = bot.try_challenge_random_bot(client, "Axiom_BOT", tracker)

        self.assertEqual(result, ("chal0001", "BulletFine"))
        self.assertEqual(client.challenges.create.call_args.args[0], "BulletFine")


class TestDrawOffers(unittest.TestCase):
    """When the bot takes a draw, and how it reads the position from its own side."""

    def engine(self, kind, value):
        engine = Mock()
        engine.get_evaluation.return_value = {"type": kind, "value": value}
        return engine

    def test_level_positions_are_accepted_up_to_the_window(self):
        from bot import should_accept_draw
        for cp in (0, 50, -50, 200, -200):
            self.assertTrue(should_accept_draw(cp), cp)

    def test_anything_beyond_the_window_is_declined(self):
        from bot import should_accept_draw
        for cp in (201, -201, 921, -915, 30000, -30000):
            self.assertFalse(should_accept_draw(cp), cp)

    def test_the_evaluation_of_the_bots_last_search_is_used_as_it_is(self):
        """It was made with the bot to move, so it is the bot's score whatever its colour."""
        from bot import evaluation_for_bot
        engine = self.engine("cp", 999)
        board = chess.Board()

        self.assertEqual(evaluation_for_bot(engine, board, bot_is_white=False, last_eval_cp=-340), -340)
        self.assertEqual(evaluation_for_bot(engine, board, bot_is_white=True, last_eval_cp=120), 120)
        engine.get_evaluation.assert_not_called()

    def test_without_a_search_the_engine_is_asked_about_the_current_position(self):
        from bot import evaluation_for_bot
        engine = self.engine("cp", 80)
        board = chess.Board()
        board.push_uci("e2e4")

        evaluation_for_bot(engine, board, bot_is_white=False, last_eval_cp=None)

        engine.set_fen_position.assert_called_once_with(board.fen())

    def test_the_engines_answer_is_kept_when_the_bot_is_to_move(self):
        from bot import evaluation_for_bot
        board = chess.Board()                      # white to move

        self.assertEqual(evaluation_for_bot(self.engine("cp", 300), board, bot_is_white=True, last_eval_cp=None), 300)

        board.push_uci("e2e4")                     # black to move
        self.assertEqual(evaluation_for_bot(self.engine("cp", 300), board, bot_is_white=False, last_eval_cp=None), 300)

    def test_the_engines_answer_is_turned_round_when_the_opponent_is_to_move(self):
        """The engine speaks for the side to move; +300 for the opponent is -300 for the bot."""
        from bot import evaluation_for_bot
        board = chess.Board()                      # white to move, bot is black

        self.assertEqual(evaluation_for_bot(self.engine("cp", 300), board, bot_is_white=False, last_eval_cp=None), -300)

    def test_a_forced_mate_becomes_a_score_no_draw_window_reaches(self):
        from bot import evaluation_for_bot, should_accept_draw
        board = chess.Board()

        winning = evaluation_for_bot(self.engine("mate", 3), board, bot_is_white=True, last_eval_cp=None)
        losing = evaluation_for_bot(self.engine("mate", -2), board, bot_is_white=True, last_eval_cp=None)
        mated_opponent_to_move = evaluation_for_bot(self.engine("mate", 2), board, bot_is_white=False, last_eval_cp=None)

        self.assertEqual((winning, losing, mated_opponent_to_move), (30000, -30000, -30000))
        self.assertFalse(should_accept_draw(winning) or should_accept_draw(losing))


class TestStockfishUpdater(unittest.TestCase):
    """Test Stockfish auto-updater functionality."""
    
    def test_get_binary_name(self):
        """Test that correct binary name is determined for the platform."""
        from stockfish_updater import get_binary_name
        
        binary_name = get_binary_name()
        
        # Should return a valid binary name
        self.assertIsInstance(binary_name, str)
        self.assertTrue(binary_name.startswith("stockfish-"))
    
    def test_get_installed_version(self):
        """Test version detection of installed Stockfish."""
        from stockfish_updater import get_installed_version
        
        version = get_installed_version()
        
        # Should return either None or a version string
        if version is not None:
            self.assertIsInstance(version, str)
    
    def test_get_latest_release_info(self):
        """Test fetching latest release info from GitHub."""
        from stockfish_updater import get_latest_release_info
        
        try:
            info = get_latest_release_info()
            
            # Should have required fields
            self.assertIn("tag_name", info)
            self.assertIn("assets", info)
            self.assertIsInstance(info["assets"], list)
        except Exception as e:
            # Network errors are acceptable in tests
            self.skipTest(f"Network request failed: {e}")

    def test_binary_name_is_a_universal_build(self):
        """Stockfish 19+ only ships universal builds; the old per-microarch
        assets (stockfish-ubuntu-x86-64) are the generic SSE2 build and no
        longer exist in the release."""
        from stockfish_updater import get_binary_name

        binary_name = get_binary_name()

        self.assertTrue(
            binary_name.endswith("-universal"),
            f"{binary_name} is not a universal build",
        )
        self.assertNotIn("ubuntu", binary_name)

    def test_binary_name_per_platform(self):
        """Each supported platform maps to its published universal asset."""
        import stockfish_updater

        cases = [
            ("Linux", "x86_64", "stockfish-linux-x86-64-universal"),
            ("Linux", "AMD64", "stockfish-linux-x86-64-universal"),
            ("Linux", "aarch64", "stockfish-linux-arm64-universal"),
            ("Linux", "riscv64", "stockfish-linux-riscv64-universal"),
            ("Darwin", "x86_64", "stockfish-macos-universal"),
            ("Darwin", "arm64", "stockfish-macos-universal"),
        ]
        for system, machine, expected in cases:
            with self.subTest(system=system, machine=machine):
                with patch("platform.system", return_value=system), \
                     patch("platform.machine", return_value=machine):
                    self.assertEqual(stockfish_updater.get_binary_name(), expected)

    def test_binary_name_rejects_unknown_platform(self):
        """An unsupported OS or architecture fails loudly."""
        import stockfish_updater

        with patch("platform.system", return_value="Linux"), \
             patch("platform.machine", return_value="mips"):
            with self.assertRaises(RuntimeError):
                stockfish_updater.get_binary_name()

        with patch("platform.system", return_value="Plan9"), \
             patch("platform.machine", return_value="x86_64"):
            with self.assertRaises(RuntimeError):
                stockfish_updater.get_binary_name()

    def test_download_url_matches_gzipped_asset(self):
        """The asset lookup uses the .tar.gz name the release actually
        publishes, not the old uncompressed .tar."""
        import stockfish_updater

        release = {
            "tag_name": "sf_19",
            "assets": [
                {"name": "stockfish-linux-arm64-universal.tar.gz",
                 "browser_download_url": "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/arm.tar.gz"},
                {"name": "stockfish-linux-x86-64-universal.tar.gz",
                 "browser_download_url": "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/x86.tar.gz"},
            ],
        }
        with patch.object(stockfish_updater, "get_latest_release_info", return_value=release):
            url = stockfish_updater.get_download_url("stockfish-linux-x86-64-universal")

        self.assertTrue(url.endswith("x86.tar.gz"))

    def test_download_url_reports_available_assets_when_missing(self):
        """A missing asset names what the release does contain, so the failure
        is diagnosable rather than a bare lookup error."""
        import stockfish_updater

        release = {"tag_name": "sf_19", "assets": [{"name": "stockfish-macos-universal.tar.gz",
                                                    "browser_download_url": "https://github.com/x"}]}
        with patch.object(stockfish_updater, "get_latest_release_info", return_value=release):
            with self.assertRaises(RuntimeError) as ctx:
                stockfish_updater.get_download_url("stockfish-linux-x86-64-universal")

        self.assertIn("stockfish-macos-universal.tar.gz", str(ctx.exception))

    def test_download_url_rejects_unexpected_host(self):
        """The download URL comes out of an API response and is made
        executable, so a non-GitHub host is refused."""
        import stockfish_updater

        release = {
            "tag_name": "sf_19",
            "assets": [{"name": "stockfish-linux-x86-64-universal.tar.gz",
                        "browser_download_url": "https://evil.example.com/payload.tar.gz"}],
        }
        with patch.object(stockfish_updater, "get_latest_release_info", return_value=release):
            with self.assertRaises(RuntimeError) as ctx:
                stockfish_updater.get_download_url("stockfish-linux-x86-64-universal")

        self.assertIn("unexpected host", str(ctx.exception))

    def test_download_url_accepts_github_hosts(self):
        """Both hosts GitHub serves release assets from are allowed."""
        import stockfish_updater

        for host in ("github.com", "objects.githubusercontent.com"):
            with self.subTest(host=host):
                url = f"https://{host}/official-stockfish/x.tar.gz"
                self.assertEqual(stockfish_updater._check_download_url(url), url)

    def test_log_build_info_reports_compilation_settings(self):
        """The installed build's code path is logged, so a generic build on a
        CPU that supports AVX2 is visible instead of silently costing speed."""
        import stockfish_updater

        completed = MagicMock()
        completed.stdout = (
            "Stockfish 19 by the Stockfish developers\n"
            "Compilation settings       : 64bit AVX2 SSE41 SSSE3 SSE2 POPCNT\n"
            "Compiler __VERSION__ macro : 15.2.0\n"
        )
        with patch("subprocess.run", return_value=completed):
            settings = stockfish_updater.log_build_info("/usr/local/bin/stockfish")

        self.assertIn("AVX2", settings)

    def test_log_build_info_survives_a_missing_binary(self):
        """Build logging is diagnostic only and never breaks startup."""
        import stockfish_updater

        with patch("subprocess.run", side_effect=FileNotFoundError):
            self.assertIsNone(stockfish_updater.log_build_info("/nonexistent/stockfish"))


class TestParseTimeToMilliseconds(unittest.TestCase):
    """Test parse_time_to_milliseconds utility for all Lichess API time formats."""

    def setUp(self):
        from bot import parse_time_to_milliseconds
        self.parse = parse_time_to_milliseconds

    def test_none_returns_none(self):
        self.assertIsNone(self.parse(None))

    def test_integer_passthrough(self):
        self.assertEqual(self.parse(120000), 120000)
        self.assertEqual(self.parse(0), 0)

    def test_float_truncated(self):
        self.assertEqual(self.parse(120000.9), 120000)
        self.assertEqual(self.parse(0.0), 0)

    def test_string_integer(self):
        self.assertEqual(self.parse("120000"), 120000)
        self.assertEqual(self.parse("0"), 0)

    def test_timedelta_string_minutes_seconds(self):
        # "0:01:00.000000" = 60 seconds = 60000 ms
        self.assertEqual(self.parse("0:01:00.000000"), 60000)

    def test_timedelta_string_hours_minutes_seconds_microseconds(self):
        # "0:08:44.640000" = 8*60000 + 44*1000 + 640 = 524640 ms
        self.assertEqual(self.parse("0:08:44.640000"), 524640)

    def test_timedelta_string_no_microseconds(self):
        # "0:03:00" = 180000 ms
        self.assertEqual(self.parse("0:03:00"), 180000)

    def test_timedelta_object(self):
        td = timedelta(minutes=3)
        self.assertEqual(self.parse(td), 180000)

    def test_timedelta_object_with_microseconds(self):
        td = timedelta(minutes=8, seconds=44, microseconds=640000)
        self.assertEqual(self.parse(td), 524640)

    def test_invalid_string_returns_none(self):
        self.assertIsNone(self.parse("not_a_time"))
        self.assertIsNone(self.parse("abc:def:ghi"))


class TestExtractCpFromInfo(unittest.TestCase):
    """Test _extract_cp_from_info helper."""

    def setUp(self):
        from bot import _extract_cp_from_info
        self.extract = _extract_cp_from_info

    def test_positive_cp(self):
        line = "info depth 20 score cp 42 nodes 500000 pv e2e4 e7e5"
        self.assertEqual(self.extract(line), 42)

    def test_negative_cp(self):
        line = "info depth 15 score cp -130 nodes 400000 pv d2d4"
        self.assertEqual(self.extract(line), -130)

    def test_cp_with_bound_token(self):
        # upperbound/lowerbound appear between 'cp' and the next token
        line = "info depth 18 seldepth 30 score cp -30 upperbound wdl 7 928 65 pv f8c5"
        self.assertEqual(self.extract(line), -30)

    def test_mate_positive(self):
        line = "info depth 10 score mate 3 nodes 1000 pv e1g1"
        self.assertEqual(self.extract(line), 30000)

    def test_mate_negative(self):
        line = "info depth 10 score mate -2 nodes 1000 pv e8g8"
        self.assertEqual(self.extract(line), -30000)

    def test_empty_string_returns_none(self):
        self.assertIsNone(self.extract(""))

    def test_no_score_returns_none(self):
        self.assertIsNone(self.extract("info depth 5 nodes 100 pv e2e4"))


class TestParsePvFromInfo(unittest.TestCase):
    """Test _parse_pv_from_info helper."""

    def setUp(self):
        from bot import _parse_pv_from_info
        self.parse_pv = _parse_pv_from_info

    def test_cp_eval_and_pv(self):
        line = "info depth 20 score cp 42 nodes 500000 pv e2e4 e7e5 g1f3"
        eval_str, pv = self.parse_pv(line, depth=10)
        self.assertEqual(eval_str, " (+42 cp)")
        self.assertEqual(pv, "e2e4 e7e5 g1f3")

    def test_negative_cp_eval(self):
        line = "info depth 15 score cp -130 pv d2d4 d7d5"
        eval_str, _ = self.parse_pv(line, depth=10)
        self.assertEqual(eval_str, " (-130 cp)")

    def test_mate_eval(self):
        line = "info depth 10 score mate 2 pv e1g1 f7f8"
        eval_str, _ = self.parse_pv(line, depth=10)
        self.assertEqual(eval_str, " (Mate in 2)")

    def test_pv_truncated_to_depth(self):
        line = "info depth 20 score cp 10 pv e2e4 e7e5 g1f3 g8f6 f1c4 f8c5"
        _, pv = self.parse_pv(line, depth=3)
        self.assertEqual(pv, "e2e4 e7e5 g1f3")

    def test_no_pv_section(self):
        line = "info depth 5 score cp 10 nodes 1000"
        _, pv = self.parse_pv(line, depth=10)
        self.assertEqual(pv, "")

    def test_empty_line(self):
        eval_str, pv = self.parse_pv("", depth=10)
        self.assertEqual(eval_str, "")
        self.assertEqual(pv, "")


class TestBulletChallengeAcceptance(unittest.TestCase):
    """Test that bullet time controls are accepted."""

    def _challenge(self, limit, increment, speed=None):
        c = {
            'challenger': {'rating': 1500},
            'timeControl': {'limit': limit, 'increment': increment},
            'id': 'test_bullet',
        }
        if speed:
            c['speed'] = speed
        return c

    def test_accept_bullet_1_0(self):
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['bullet', 'blitz', 'rapid', 'classical']):
            self.assertTrue(should_accept_challenge(self._challenge(60, 0)))

    def test_accept_bullet_1_1(self):
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['bullet', 'blitz', 'rapid', 'classical']):
            self.assertTrue(should_accept_challenge(self._challenge(60, 1)))

    def test_accept_bullet_2_1(self):
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['bullet', 'blitz', 'rapid', 'classical']):
            self.assertTrue(should_accept_challenge(self._challenge(120, 1)))

    def test_reject_bullet_when_not_in_time_control(self):
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            self.assertFalse(should_accept_challenge(self._challenge(60, 0)))


class TestExtractMateFromInfo(unittest.TestCase):
    """Test _extract_mate_from_info helper."""

    def setUp(self):
        from bot import _extract_mate_from_info
        self.extract = _extract_mate_from_info

    def test_positive_mate(self):
        """Positive mate value = mate for side to move."""
        line = "info depth 10 score mate 3 nodes 1000 pv e1g1 f7f8"
        self.assertEqual(self.extract(line), 3)

    def test_negative_mate(self):
        """Negative mate value = being mated."""
        line = "info depth 10 score mate -2 nodes 1000 pv e8g8"
        self.assertEqual(self.extract(line), -2)

    def test_mate_in_one(self):
        line = "info depth 5 score mate 1 pv d1h5"
        self.assertEqual(self.extract(line), 1)

    def test_no_mate_returns_none(self):
        line = "info depth 20 score cp 42 nodes 500000 pv e2e4 e7e5"
        self.assertIsNone(self.extract(line))

    def test_empty_string_returns_none(self):
        self.assertIsNone(self.extract(""))

    def test_cp_only_returns_none(self):
        line = "info depth 15 score cp -130 pv d2d4"
        self.assertIsNone(self.extract(line))


class TestGetMovePredictionSignature(unittest.TestCase):
    """get_move_prediction returns the move with the mate distance and the evaluation."""

    def _make_stockfish_mock(self, info_line: str, best_move: str = "e2e4"):
        sf = Mock()
        sf.get_best_move_time.return_value = best_move
        # stockfish >= 5.0: raw_stockfish_output(func) returns list of output lines;
        # the penultimate line ([-2]) is the last info line before "bestmove".
        sf.raw_stockfish_output.return_value = [info_line, f"bestmove {best_move}"]
        return sf

    def test_returns_three_tuple_with_cp(self):
        from bot import get_move_prediction
        sf = self._make_stockfish_mock("info depth 20 score cp 42 pv e2e4 e7e5")
        move, mate_val, cp_val = get_move_prediction(sf, "test_game", move_time_ms=100)
        self.assertEqual(move, "e2e4")
        self.assertIsNone(mate_val)
        self.assertEqual(cp_val, 42)

    def test_returns_three_tuple_with_mate(self):
        from bot import get_move_prediction
        sf = self._make_stockfish_mock("info depth 5 score mate 3 pv d1h5 h8h7 d1h7")
        move, mate_val, cp_val = get_move_prediction(sf, "test_game", move_time_ms=100)
        self.assertEqual(move, "e2e4")
        self.assertEqual(mate_val, 3)
        # _extract_cp_from_info converts mate to ±30000
        self.assertEqual(cp_val, 30000)

    def test_returns_three_nones_on_no_move(self):
        from bot import get_move_prediction
        sf = Mock()
        sf.get_best_move_time.return_value = None
        result = get_move_prediction(sf, "test_game", move_time_ms=100)
        self.assertEqual(result, (None, None, None))

    def test_returns_three_nones_on_exception(self):
        from bot import get_move_prediction
        sf = Mock()
        sf.get_best_move_time.side_effect = Exception("engine crash")
        result = get_move_prediction(sf, "test_game", move_time_ms=100)
        self.assertEqual(result, (None, None, None))

    def test_negative_mate_returns_negative_mate_val(self):
        from bot import get_move_prediction
        sf = self._make_stockfish_mock("info depth 8 score mate -2 pv e8g8")
        move, mate_val, cp_val = get_move_prediction(sf, "test_game", move_time_ms=100)
        self.assertEqual(mate_val, -2)
        self.assertEqual(cp_val, -30000)


class TestFullPowerMateMove(unittest.TestCase):
    """Test _get_full_power_move helper — disables UCI_LimitStrength, restores after."""

    def _make_stockfish_mock(self, best_move: str = "e2e4"):
        mock_sf = MagicMock()
        mock_sf.get_best_move_time.return_value = best_move
        return mock_sf

    def test_disables_limit_strength_before_search(self):
        """UCI_LimitStrength must be set to False before get_best_move_time is called."""
        from bot import _get_full_power_move
        mock_sf = self._make_stockfish_mock("d1h5")
        call_order = []
        mock_sf.update_engine_parameters.side_effect = lambda p: call_order.append(("update", p))
        mock_sf.get_best_move_time.side_effect = lambda t: call_order.append(("search", t)) or "d1h5"

        _get_full_power_move(mock_sf, "game1", 1000, restore_elo=1600)

        # First call must disable UCI_LimitStrength
        self.assertEqual(call_order[0], ("update", {"UCI_LimitStrength": False}))
        # Second call is the actual search
        self.assertEqual(call_order[1][0], "search")

    def test_restores_limit_strength_after_search(self):
        """UCI_LimitStrength must be restored with the original ELO after the search."""
        from bot import _get_full_power_move
        mock_sf = self._make_stockfish_mock("d1h5")
        restore_calls = []
        mock_sf.update_engine_parameters.side_effect = lambda p: restore_calls.append(p)

        _get_full_power_move(mock_sf, "game1", 1000, restore_elo=2300)

        # Last update_engine_parameters call must restore UCI_LimitStrength
        last_call = restore_calls[-1]
        self.assertEqual(last_call, {"UCI_LimitStrength": True, "UCI_Elo": 2300})

    def test_restores_even_on_search_exception(self):
        """UCI_LimitStrength must be restored even if get_best_move_time raises."""
        from bot import _get_full_power_move
        mock_sf = self._make_stockfish_mock()
        mock_sf.get_best_move_time.side_effect = Exception("engine crashed")
        restore_calls = []
        mock_sf.update_engine_parameters.side_effect = lambda p: restore_calls.append(p)

        result = _get_full_power_move(mock_sf, "game1", 1000, restore_elo=1800)

        self.assertIsNone(result)
        last_call = restore_calls[-1]
        self.assertEqual(last_call, {"UCI_LimitStrength": True, "UCI_Elo": 1800})

    def test_no_restore_when_restore_elo_is_none(self):
        """When restore_elo is None, UCI_LimitStrength is only disabled, never re-enabled."""
        from bot import _get_full_power_move
        mock_sf = self._make_stockfish_mock("e2e4")
        calls = []
        mock_sf.update_engine_parameters.side_effect = lambda p: calls.append(p)

        _get_full_power_move(mock_sf, "game1", 500, restore_elo=None)

        # Only one call: disabling
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], {"UCI_LimitStrength": False})

    def test_returns_best_move(self):
        """Should return the move from get_best_move_time."""
        from bot import _get_full_power_move
        mock_sf = self._make_stockfish_mock("h7h8q")

        result = _get_full_power_move(mock_sf, "game1", 1000)

        self.assertEqual(result, "h7h8q")


class TestClockAdjustedSecondarySearch(unittest.TestCase):
    """A second search in the same move is budgeted from the clock left after the first."""

    def test_clock_aware_uses_adjusted_remaining(self):
        """clock_aware_move_time respects remaining_after_pred, not original remaining."""
        from bot import clock_aware_move_time
        original_remaining = 10_000   # 10 s
        pred_elapsed = 2_000          # 2 s consumed by prediction
        remaining_after = max(0, original_remaining - pred_elapsed)  # 8 s

        # With 8 s remaining and 10 moves left, clock cap ≈ (8000/10) * 0.8 = 640 ms
        budget_adjusted = clock_aware_move_time(None, 5000, remaining_after, 0, 10)
        # With original 10 s remaining same formula gives 800 ms
        budget_original = clock_aware_move_time(None, 5000, original_remaining, 0, 10)

        self.assertLess(budget_adjusted, budget_original,
                        "Adjusted-clock budget must be smaller than original-clock budget")


class TestAbortStaleGames(unittest.TestCase):
    """What the bot does on startup with games left over from its previous run."""

    STARTED = {"id": 20, "name": "started"}

    def client(self, ongoing, exports=None):
        """Games as Lichess lists them; each gets the status of a game in progress unless it has one."""
        client = Mock()
        client.games.get_ongoing.return_value = [{"status": self.STARTED, **game} for game in ongoing]
        client.games.export.side_effect = lambda gid: (exports or {})[gid]
        return client

    def run_cleanup(self, client):
        from bot import abort_stale_games
        abort_stale_games(client)

    def test_nothing_ongoing_asks_nothing_more(self):
        client = self.client([])

        self.run_cleanup(client)

        client.games.export.assert_not_called()
        client.bots.abort_game.assert_not_called()

    def test_a_game_nobody_has_moved_in_is_aborted(self):
        client = self.client([{"gameId": "stuck001", "opponent": {"username": "gone"}}],
                             {"stuck001": {"moves": ""}})

        self.run_cleanup(client)

        client.bots.abort_game.assert_called_once_with("stuck001")

    def test_a_game_with_one_move_can_still_be_aborted(self):
        client = self.client([{"gameId": "stuck001", "opponent": {"username": "gone"}}],
                             {"stuck001": {"moves": "e2e4"}})

        self.run_cleanup(client)

        client.bots.abort_game.assert_called_once_with("stuck001")

    def test_a_listing_without_a_status_is_treated_as_a_game_in_progress(self):
        client = Mock()
        client.games.get_ongoing.return_value = [{"gameId": "stuck001", "opponent": {"username": "gone"}}]
        client.games.export.return_value = {"moves": ""}

        self.run_cleanup(client)

        client.bots.abort_game.assert_called_once_with("stuck001")

    def test_a_game_under_way_is_left_for_the_event_stream(self):
        client = self.client([{"gameId": "live0001", "opponent": {"username": "rival"}}],
                             {"live0001": {"moves": "e2e4 e7e5 g1f3"}})

        self.run_cleanup(client)

        client.bots.abort_game.assert_not_called()
        client.bots.resign_game.assert_not_called()

    def test_a_game_that_is_already_over_is_not_looked_up(self):
        for status in ({"name": "aborted"}, "mate"):
            with self.subTest(status=status):
                client = self.client([{"gameId": "done0001", "status": status, "opponent": {"username": "x"}}])

                self.run_cleanup(client)

                client.games.export.assert_not_called()
                client.bots.abort_game.assert_not_called()

    def test_each_game_is_judged_on_its_own(self):
        client = self.client(
            [{"gameId": "stuck001", "opponent": {"username": "a"}},
             {"gameId": "live0001", "opponent": {"username": "b"}},
             {"id": "stuck002", "opponent": {"username": "c"}}],
            {"stuck001": {"moves": ""}, "live0001": {"moves": "d2d4 d7d5"}, "stuck002": {"moves": "c2c4"}},
        )

        self.run_cleanup(client)

        self.assertEqual([c.args[0] for c in client.bots.abort_game.call_args_list], ["stuck001", "stuck002"])

    def test_a_refused_abort_does_not_stop_the_cleanup(self):
        client = self.client(
            [{"gameId": "stuck001", "opponent": {"username": "a"}}, {"gameId": "stuck002", "opponent": {"username": "b"}}],
            {"stuck001": {"moves": ""}, "stuck002": {"moves": ""}},
        )
        client.bots.abort_game.side_effect = [RuntimeError("too late"), None]

        self.run_cleanup(client)

        self.assertEqual(client.bots.abort_game.call_count, 2)

    def test_lichess_being_unreachable_does_not_stop_the_start(self):
        client = Mock()
        client.games.get_ongoing.side_effect = RuntimeError("no network")

        self.run_cleanup(client)      # must not raise

        client.bots.abort_game.assert_not_called()


class TestStreamWithWatchdog(unittest.TestCase):
    """Test _stream_with_watchdog handles idle streams and terminal games."""

    def test_yields_events_from_stream(self):
        """Normal stream events are yielded through the watchdog."""
        from bot import _stream_with_watchdog
        events = [{"type": "gameState", "moves": "e2e4"}, {"type": "gameState", "moves": "e2e4 e7e5"}]
        mock_client = Mock()
        result = list(_stream_with_watchdog(iter(events), mock_client, "test123", check_interval=5))
        self.assertEqual(result, events)

    def test_watchdog_checks_api_on_idle(self):
        """When stream is idle, watchdog polls the API."""
        from bot import _stream_with_watchdog, _GameStuck

        # Create a stream that blocks forever
        block = threading.Event()
        def slow_stream():
            block.wait(timeout=10)
            return
            yield  # make it a generator

        mock_client = Mock()
        mock_client.games.export.return_value = {"status": "aborted"}

        with self.assertRaises(_GameStuck):
            # Very short interval so test is fast
            for _ in _stream_with_watchdog(slow_stream(), mock_client, "test123", check_interval=0.1):
                pass

        mock_client.games.export.assert_called_with("test123")
        block.set()  # cleanup

    def test_watchdog_continues_if_game_active(self):
        """Watchdog does not break if API says game is still active."""
        from bot import _stream_with_watchdog

        call_count = 0
        event_ready = threading.Event()

        def delayed_stream():
            # First, delay to trigger watchdog
            event_ready.wait(timeout=5)
            yield {"type": "gameState", "moves": "e2e4"}

        mock_client = Mock()
        # First API call: game active → continue. Then stream delivers event.
        def export_side_effect(gid):
            nonlocal call_count
            call_count += 1
            event_ready.set()  # wake up the stream after first watchdog check
            return {"status": "started"}

        mock_client.games.export.side_effect = export_side_effect

        result = list(_stream_with_watchdog(delayed_stream(), mock_client, "test123", check_interval=0.1))
        self.assertEqual(len(result), 1)
        self.assertGreaterEqual(call_count, 1)

    def test_watchdog_re_raises_stream_exceptions(self):
        """Exceptions from the underlying stream are re-raised."""
        from bot import _stream_with_watchdog

        def failing_stream():
            raise ConnectionError("lost connection")
            yield  # make it a generator

        mock_client = Mock()
        with self.assertRaises(ConnectionError):
            for _ in _stream_with_watchdog(failing_stream(), mock_client, "x", check_interval=1):
                pass


class TestWatchdogConsecutiveFailures(unittest.TestCase):
    """Test that watchdog escalates after consecutive API failures."""

    def test_watchdog_raises_after_max_failures(self):
        """After N consecutive API failures, watchdog force-ends the game."""
        from bot import _stream_with_watchdog, _GameStuck

        block = threading.Event()
        def slow_stream():
            block.wait(timeout=10)
            return
            yield

        mock_client = Mock()
        mock_client.games.export.side_effect = Exception("API unavailable")

        with self.assertRaises(_GameStuck) as ctx:
            for _ in _stream_with_watchdog(slow_stream(), mock_client, "fail_test", check_interval=0.05):
                pass

        self.assertIn("could not verify game status", str(ctx.exception))
        block.set()

    def test_watchdog_failure_count_resets_on_success(self):
        """Successful API check resets the consecutive failure counter."""
        from bot import _stream_with_watchdog

        call_count = 0
        event_ready = threading.Event()

        def delayed_stream():
            event_ready.wait(timeout=5)
            yield {"type": "gameState", "moves": "e2e4"}

        mock_client = Mock()
        def export_side_effect(gid):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("temporary failure")
            # Third call succeeds → stream event arrives
            event_ready.set()
            return {"status": "started"}

        mock_client.games.export.side_effect = export_side_effect

        result = list(_stream_with_watchdog(delayed_stream(), mock_client, "reset_test", check_interval=0.05))
        self.assertEqual(len(result), 1)
        # Should NOT have raised _GameStuck — failures reset on success
        self.assertGreaterEqual(call_count, 3)


class TestGetLastInfoLine(unittest.TestCase):
    """Tests for _get_last_info_line helper (stockfish 5.0 compat)."""

    def test_returns_penultimate_line(self):
        from bot import _get_last_info_line
        sf = Mock()
        sf.raw_stockfish_output.return_value = [
            "info depth 10 score cp 42 pv e2e4 e7e5",
            "bestmove e2e4",
        ]
        result = _get_last_info_line(sf, sf.get_best_move_time)
        self.assertEqual(result, "info depth 10 score cp 42 pv e2e4 e7e5")

    def test_returns_empty_on_exception(self):
        from bot import _get_last_info_line
        sf = Mock()
        sf.raw_stockfish_output.side_effect = Exception("no data")
        result = _get_last_info_line(sf, sf.get_best_move_time)
        self.assertEqual(result, "")

    def test_returns_empty_on_short_output(self):
        from bot import _get_last_info_line
        sf = Mock()
        sf.raw_stockfish_output.return_value = ["bestmove e2e4"]
        result = _get_last_info_line(sf, sf.get_best_move_time)
        self.assertEqual(result, "")

    def test_returns_empty_on_empty_output(self):
        from bot import _get_last_info_line
        sf = Mock()
        sf.raw_stockfish_output.return_value = []
        result = _get_last_info_line(sf, sf.get_best_move_time)
        self.assertEqual(result, "")


class TestGetLastEvalCp(unittest.TestCase):
    """Tests for _get_last_eval_cp helper."""

    def test_returns_cp_from_movetime_search(self):
        from bot import _get_last_eval_cp
        sf = Mock()
        sf.raw_stockfish_output.return_value = [
            "info depth 15 score cp -120 pv d7d5",
            "bestmove d7d5",
        ]
        result = _get_last_eval_cp(sf)
        self.assertEqual(result, -120)

    def test_returns_mate_as_30000(self):
        from bot import _get_last_eval_cp
        sf = Mock()
        sf.raw_stockfish_output.return_value = [
            "info depth 10 score mate 3 pv d1h5",
            "bestmove d1h5",
        ]
        result = _get_last_eval_cp(sf)
        self.assertEqual(result, 30000)

    def test_returns_none_when_no_eval(self):
        from bot import _get_last_eval_cp
        sf = Mock()
        sf.raw_stockfish_output.return_value = []
        result = _get_last_eval_cp(sf)
        self.assertIsNone(result)

    def test_returns_none_on_exception(self):
        from bot import _get_last_eval_cp
        sf = Mock()
        sf.raw_stockfish_output.side_effect = Exception("crash")
        result = _get_last_eval_cp(sf)
        self.assertIsNone(result)


class TestStreamWithWatchdogAbort(unittest.TestCase):
    """Tests for _stream_with_watchdog stuck-game abort logic."""

    @patch('bot.GAME_WATCHDOG_ABORT_TIMEOUT', 0)  # immediate abort for fast test
    def test_stuck_started_game_triggers_abort(self):
        """Watchdog should raise _GameStuck when game is in 'started' too long."""
        from bot import _stream_with_watchdog, _GameStuck
        import threading as _threading

        mock_client = Mock()
        mock_client.games.export.return_value = {"status": "started"}
        mock_client.bots.abort_game.return_value = None

        # Iterator that blocks on next() so reader thread never puts sentinel
        block = _threading.Event()

        class _BlockingIter:
            def __iter__(self):
                return self
            def __next__(self):
                block.wait()
                raise StopIteration

        gen = _stream_with_watchdog(_BlockingIter(), mock_client, "test123", check_interval=0.05)

        try:
            with self.assertRaises(_GameStuck):
                for _ in gen:
                    pass
        finally:
            block.set()  # unblock reader thread so it can exit cleanly


class TestVariantRejection(unittest.TestCase):
    """Tests for rejecting non-standard chess variants."""

    def _base_challenge(self, variant=None):
        c = {
            'challenger': {'rating': 1500},
            'timeControl': {'limit': 180, 'increment': 0},
            'id': 'test_variant',
        }
        if variant is not None:
            c['variant'] = variant
        return c

    def _patches(self):
        return [
            patch('bot.ACCEPT_CHALLENGES', True),
            patch('bot.MIN_RATING', 1000),
            patch('bot.MAX_RATING', 2400),
            patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']),
        ]

    def test_accept_standard_variant_dict(self):
        """Standard variant (dict format) should be accepted."""
        c = self._base_challenge(variant={'key': 'standard', 'name': 'Standard'})
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            self.assertTrue(should_accept_challenge(c))

    def test_accept_no_variant_field(self):
        """Missing variant field should default to standard and be accepted."""
        c = self._base_challenge()
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            self.assertTrue(should_accept_challenge(c))

    def test_reject_chess960(self):
        """Chess960 variant should be rejected."""
        c = self._base_challenge(variant={'key': 'chess960', 'name': 'Chess960'})
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            self.assertFalse(should_accept_challenge(c))

    def test_reject_antichess(self):
        """Antichess variant should be rejected."""
        c = self._base_challenge(variant={'key': 'antichess', 'name': 'Antichess'})
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            self.assertFalse(should_accept_challenge(c))

    def test_reject_atomic(self):
        """Atomic variant should be rejected."""
        c = self._base_challenge(variant={'key': 'atomic', 'name': 'Atomic'})
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            self.assertFalse(should_accept_challenge(c))

    def test_reject_kingOfTheHill(self):
        """King of the Hill variant should be rejected."""
        c = self._base_challenge(variant={'key': 'kingOfTheHill', 'name': 'King of the Hill'})
        with patch('bot.ACCEPT_CHALLENGES', True), \
             patch('bot.MIN_RATING', 1000), \
             patch('bot.MAX_RATING', 2400), \
             patch('bot.TIME_CONTROL', ['blitz', 'rapid', 'classical']):
            self.assertFalse(should_accept_challenge(c))


class TestTimeCategoryClassification(unittest.TestCase):
    """Tests for determine_time_category boundary conditions."""

    def test_15_plus_10_is_rapid(self):
        """15+10 should be classified as rapid (total=1300 < 1500)."""
        from bot import determine_time_category
        self.assertEqual(determine_time_category(900, 10), "rapid")

    def test_20_plus_10_is_classical(self):
        """20+10 should be classified as classical (total=1600 >= 1500)."""
        from bot import determine_time_category
        self.assertEqual(determine_time_category(1200, 10), "classical")

    def test_30_plus_0_is_classical(self):
        """30+0 should be classified as classical (total=1800 >= 1500)."""
        from bot import determine_time_category
        self.assertEqual(determine_time_category(1800, 0), "classical")

    def test_unlimited_returns_none(self):
        """0+0 (unlimited) should return None."""
        from bot import determine_time_category
        self.assertIsNone(determine_time_category(0, 0))

    def test_speed_boundaries_follow_lichess(self):
        """Estimated length is the initial time plus 40 increments."""
        from bot import determine_time_category
        cases = {
            (60, 0): "bullet", (120, 1): "bullet", (179, 0): "bullet",
            (180, 0): "blitz", (180, 2): "blitz", (300, 3): "blitz", (479, 0): "blitz",
            (480, 0): "rapid", (600, 5): "rapid", (900, 10): "rapid", (1499, 0): "rapid",
            (1500, 0): "classical", (1800, 0): "classical", (0, 40): "classical",
        }
        for (limit, increment), speed in cases.items():
            self.assertEqual(determine_time_category(limit, increment), speed, f"{limit}+{increment}")

    def test_a_challenge_without_a_clock_has_no_speed(self):
        """Correspondence and unlimited challenges carry no limit and no increment."""
        with patch('bot.ACCEPT_CHALLENGES', True), patch('bot.MIN_RATING', 1000), patch('bot.MAX_RATING', 3000):
            for time_control in ({"type": "correspondence", "daysPerTurn": 3}, {"type": "unlimited"}):
                challenge = {"id": "c", "challenger": {"rating": 1800}, "variant": {"key": "standard"},
                             "timeControl": time_control}
                self.assertFalse(should_accept_challenge(challenge), time_control)


if __name__ == '__main__':
    unittest.main()
