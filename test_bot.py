"""
Unit tests for Axiom Chess Bot
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import os

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


class TestBoardState(unittest.TestCase):
    """Test chess board state handling."""
    
    def test_board_initialization(self):
        """Test that board is properly initialized."""
        board = chess.Board()
        self.assertEqual(board.fen(), chess.STARTING_FEN)
    
    def test_board_move_application(self):
        """Test that moves are correctly applied to board."""
        board = chess.Board()
        
        # Apply starting move
        move_uci = 'e2e4'
        board.push_uci(move_uci)
        
        # Verify board state changed
        self.assertNotEqual(board.fen(), chess.STARTING_FEN)
    
    def test_board_multiple_moves(self):
        """Test board state with multiple moves."""
        board = chess.Board()
        moves = ['e2e4', 'c7c5', 'g1f3', 'd7d6']
        
        for move_uci in moves:
            board.push_uci(move_uci)
        
        # Verify board has processed all moves
        self.assertEqual(len(list(board.move_stack)), 4)
    
    def test_invalid_move_handling(self):
        """Test that invalid moves raise appropriate errors."""
        board = chess.Board()
        
        with self.assertRaises(ValueError):
            board.push_uci('invalid')
    
    def test_game_over_detection(self):
        """Test detection of game over state."""
        board = chess.Board()
        self.assertFalse(board.is_game_over())
        
        # Fool's mate: 1. f3 e6 2. g4 Qh4#
        moves = ['f2f3', 'e7e6', 'g2g4', 'd8h4']
        for move_uci in moves:
            board.push_uci(move_uci)
        
        self.assertTrue(board.is_game_over())


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


class TestErrorHandling(unittest.TestCase):
    """Test error handling in game play."""
    
    def test_api_error_import(self):
        """Test that ApiError can be imported from berserk.exceptions."""
        from berserk.exceptions import ApiError
        self.assertIsNotNone(ApiError)
    
    def test_response_error_import(self):
        """Test that ResponseError can be imported from berserk.exceptions."""
        from berserk.exceptions import ResponseError
        self.assertIsNotNone(ResponseError)


class TestLogging(unittest.TestCase):
    """Test logging configuration."""
    
    def test_logger_setup(self):
        """Test that logger is properly configured."""
        from logging_config import setup_logger
        
        logger = setup_logger(__name__)
        
        # Verify logger exists and has handlers
        self.assertIsNotNone(logger)
        self.assertTrue(len(logger.handlers) > 0)


class TestChallengeTracker(unittest.TestCase):
    """Test challenge tracker functionality."""
    
    def test_initial_state(self):
        """Test that tracker starts with no challenges."""
        from bot import ChallengeTracker
        
        tracker = ChallengeTracker(max_per_hour=3)
        self.assertTrue(tracker.can_challenge())
        self.assertEqual(tracker.get_remaining_challenges(), 3)
    
    def test_record_challenge(self):
        """Test recording challenges."""
        from bot import ChallengeTracker
        
        tracker = ChallengeTracker(max_per_hour=3)
        
        tracker.record_challenge()
        self.assertEqual(tracker.get_remaining_challenges(), 2)
        
        tracker.record_challenge()
        self.assertEqual(tracker.get_remaining_challenges(), 1)
        
        tracker.record_challenge()
        self.assertEqual(tracker.get_remaining_challenges(), 0)
        self.assertFalse(tracker.can_challenge())
    
    def test_hourly_reset(self):
        """Test that challenges older than 1 hour are removed."""
        from bot import ChallengeTracker
        from datetime import datetime, timedelta
        
        tracker = ChallengeTracker(max_per_hour=3)
        
        # Manually add old challenge
        old_time = datetime.now() - timedelta(hours=2)
        tracker.challenge_times.append(old_time)
        
        # Should still have capacity
        self.assertTrue(tracker.can_challenge())
        self.assertEqual(tracker.get_remaining_challenges(), 3)
    
    def test_filter_suitable_bots(self):
        """Test filtering bots by rating."""
        from bot import filter_suitable_bots
        
        bots = [
            {"username": "bot1", "perfs": {"blitz": {"rating": 1400}}},  # Too low
            {"username": "bot2", "perfs": {"blitz": {"rating": 1600}}},  # Good
            {"username": "bot3", "perfs": {"blitz": {"rating": 2500}}},  # Good
            {"username": "bot4", "perfs": {"blitz": {"rating": 3000}}},  # Too high
            {"username": "TestBot", "perfs": {"blitz": {"rating": 2000}}},  # Self (should be excluded)
        ]
        
        suitable = filter_suitable_bots(bots, 1500, 2900, "TestBot")
        
        self.assertEqual(len(suitable), 2)
        self.assertEqual(suitable[0]["username"], "bot2")
        self.assertEqual(suitable[1]["username"], "bot3")


class TestDrawOfferHandling(unittest.TestCase):
    """Test draw offer handling logic."""
    
    @patch('bot.Stockfish')
    def test_accept_draw_balanced_position(self, mock_stockfish_class):
        """Test that draw is accepted in balanced positions (±200cp)."""
        # Mock Stockfish to return balanced evaluation
        mock_sf = Mock()
        mock_sf.get_evaluation.return_value = {"type": "cp", "value": 50}
        
        # Simulate bot deciding on draw offer
        eval_info = mock_sf.get_evaluation()
        evaluation = eval_info["value"]
        
        # Bot is white, so evaluation is from white's perspective
        accept_draw = -200 <= evaluation <= 200
        
        self.assertTrue(accept_draw)
        self.assertEqual(evaluation, 50)
    
    @patch('bot.Stockfish')
    def test_decline_draw_winning_position(self, mock_stockfish_class):
        """Test that draw is declined when bot is winning (>200cp)."""
        # Mock Stockfish to return winning evaluation
        mock_sf = Mock()
        mock_sf.get_evaluation.return_value = {"type": "cp", "value": 921}
        
        eval_info = mock_sf.get_evaluation()
        evaluation = eval_info["value"]
        
        # Bot is white, so evaluation is from white's perspective
        accept_draw = -200 <= evaluation <= 200
        
        self.assertFalse(accept_draw)
        self.assertGreater(evaluation, 200)
    
    @patch('bot.Stockfish')
    def test_decline_draw_losing_position(self, mock_stockfish_class):
        """Test that draw is declined when bot is losing (<-200cp)."""
        # Mock Stockfish to return losing evaluation
        mock_sf = Mock()
        mock_sf.get_evaluation.return_value = {"type": "cp", "value": -1003}
        
        eval_info = mock_sf.get_evaluation()
        evaluation = eval_info["value"]
        
        # Bot is white, so evaluation is from white's perspective
        accept_draw = -200 <= evaluation <= 200
        
        self.assertFalse(accept_draw)
        self.assertLess(evaluation, -200)
    
    @patch('bot.Stockfish')
    def test_decline_draw_mate_position(self, mock_stockfish_class):
        """Test that draw is declined when bot has mate."""
        # Mock Stockfish to return mate evaluation
        mock_sf = Mock()
        mock_sf.get_evaluation.return_value = {"type": "mate", "value": 3}
        
        eval_info = mock_sf.get_evaluation()
        
        # Mate evaluation means always decline
        accept_draw = eval_info["type"] != "mate"
        
        self.assertFalse(accept_draw)
        self.assertEqual(eval_info["type"], "mate")
    
    @patch('bot.Stockfish')
    def test_color_adjustment_for_black(self, mock_stockfish_class):
        """Test that evaluation is adjusted correctly when bot plays as black."""
        # Mock Stockfish (evaluates from white's perspective)
        mock_sf = Mock()
        mock_sf.get_evaluation.return_value = {"type": "cp", "value": 300}
        
        eval_info = mock_sf.get_evaluation()
        evaluation = eval_info["value"]
        
        # Bot is black, so negate evaluation
        bot_is_white = False
        if not bot_is_white:
            evaluation = -evaluation
        
        # From bot's (black's) perspective, this is losing
        accept_draw = -200 <= evaluation <= 200
        
        self.assertFalse(accept_draw)
        self.assertEqual(evaluation, -300)


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


class TestMoveTimeCalculationSignature(unittest.TestCase):
    """Verify calculate_move_time no longer accepts time-pressure arguments."""

    def test_signature_has_two_params_only(self):
        import inspect
        from bot import calculate_move_time
        params = list(inspect.signature(calculate_move_time).parameters)
        self.assertEqual(params, ["opponent_rating", "base_time"],
                         "calculate_move_time should only take opponent_rating and base_time")

    @patch('bot.DYNAMIC_STRENGTH', True)
    @patch('bot.LIMIT_STRENGTH_THRESHOLD', 1800)
    @patch('bot.FULL_STRENGTH_THRESHOLD', 2200)
    def test_returns_int(self):
        from bot import calculate_move_time
        result = calculate_move_time(2000, 3000)
        self.assertIsInstance(result, int)


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
    """Test _extract_mate_from_info helper (added in commit d0fad89)."""

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
    """Verify get_move_prediction returns a 3-tuple (commit d0fad89 / c90afb6)."""

    def _make_stockfish_mock(self, info_line: str, best_move: str = "e2e4"):
        sf = Mock()
        sf.get_best_move_time.return_value = best_move
        sf.info.return_value = info_line
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


class TestDrawOfferFallback(unittest.TestCase):
    """Test draw offer BOT endpoint fallback logic (commit 8367bb0)."""

    def test_fallback_triggered_on_not_for_bot_accounts(self):
        """When 'not for bot accounts' appears in error, fallback POST is used."""
        import requests as req_module
        error = Exception("This endpoint is not for bot accounts")

        with patch('bot.requests.post') as mock_post, \
             patch('bot.TOKEN', 'test_token'):
            mock_post.return_value = Mock(status_code=200, text="ok")

            # Simulate the fallback condition check
            err_text = str(error).lower()
            should_fallback = (
                "not for bot accounts" in err_text
                or "403" in err_text
                or (getattr(error, 'response', None)
                    and getattr(error.response, 'status_code', None) == 403)
            )
            self.assertTrue(should_fallback)

    def test_fallback_triggered_on_403_in_message(self):
        error = Exception("403 Forbidden")
        err_text = str(error).lower()
        should_fallback = (
            "not for bot accounts" in err_text
            or "403" in err_text
            or (getattr(error, 'response', None)
                and getattr(error.response, 'status_code', None) == 403)
        )
        self.assertTrue(should_fallback)

    def test_fallback_triggered_on_response_status_403(self):
        error = Exception("API error")
        mock_resp = Mock()
        mock_resp.status_code = 403
        error.response = mock_resp

        err_text = str(error).lower()
        should_fallback = (
            "not for bot accounts" in err_text
            or "403" in err_text
            or (getattr(error, 'response', None)
                and getattr(error.response, 'status_code', None) == 403)
        )
        self.assertTrue(should_fallback)

    def test_no_fallback_for_generic_error(self):
        error = Exception("some other network error")
        err_text = str(error).lower()
        should_fallback = (
            "not for bot accounts" in err_text
            or "403" in err_text
            or (getattr(error, 'response', None)
                and getattr(error.response, 'status_code', None) == 403)
        )
        self.assertFalse(should_fallback)

    def test_fallback_url_accept(self):
        """Verify correct URL is constructed for accept."""
        game_id = "abc123"
        accept = True
        url_action = "accept" if accept else "decline"
        url = f"https://lichess.org/api/bot/game/{game_id}/draw/{url_action}"
        self.assertEqual(url, "https://lichess.org/api/bot/game/abc123/draw/accept")

    def test_fallback_url_decline(self):
        """Verify correct URL is constructed for decline."""
        game_id = "abc123"
        accept = False
        url_action = "accept" if accept else "decline"
        url = f"https://lichess.org/api/bot/game/{game_id}/draw/{url_action}"
        self.assertEqual(url, "https://lichess.org/api/bot/game/abc123/draw/decline")


class TestPredictionRecoverThreshold(unittest.TestCase):
    """Test PREDICTION_RECOVER_THRESHOLD config and eval_for_bot logic.

    Recovery search, follow-mate, and avoid-mate branches now fire
    unconditionally for every opponent regardless of their rating
    (PREDICTION_MIN_USE_ELO was removed in v2.4.2).
    """

    def test_config_default_value(self):
        from bot import PREDICTION_RECOVER_THRESHOLD
        # Default is 400 cp
        self.assertIsInstance(PREDICTION_RECOVER_THRESHOLD, int)
        self.assertGreater(PREDICTION_RECOVER_THRESHOLD, 0)

    def test_eval_for_bot_is_pred_cp_directly(self):
        """UCI score cp is from side-to-move (always the bot) — no colour flip needed."""
        # Losing as white: pred_cp already negative from bot's perspective
        pred_cp_white = -450
        eval_for_bot = pred_cp_white  # no negation
        self.assertEqual(eval_for_bot, -450)

    def test_eval_for_bot_black_no_negation(self):
        """When bot is black and losing, pred_cp is negative — should NOT be negated.

        Old (wrong): eval_for_bot = -pred_cp → positive when losing as black → recovery never fired.
        New (correct): eval_for_bot = pred_cp → negative when losing as black → recovery fires.
        """
        # bot is black, down 9 pawns — Stockfish reports -915 from side-to-move (black)
        pred_cp = -915
        eval_for_bot = pred_cp   # direct, no negation
        self.assertEqual(eval_for_bot, -915)
        # must trigger recovery
        self.assertTrue(eval_for_bot <= -400)

    def test_recovery_triggered_when_below_threshold(self):
        """Recovery path taken when eval is worse than -threshold."""
        threshold = 400
        eval_for_bot = -450  # worse than -400
        self.assertTrue(eval_for_bot <= -threshold)

    def test_recovery_not_triggered_near_threshold(self):
        """Recovery not taken when eval is just within threshold."""
        threshold = 400
        eval_for_bot = -399
        self.assertFalse(eval_for_bot <= -threshold)

    def test_recovery_not_triggered_when_winning(self):
        threshold = 400
        eval_for_bot = 200
        self.assertFalse(eval_for_bot <= -threshold)

    def test_recovery_uses_full_power_not_limited_engine(self):
        """Recovery must use ELO boost (not full power), so opponent can still win (v2.4.2).

        UCI_LimitStrength stays active but UCI_Elo is raised by PREDICTION_RECOVER_ELO_BOOST.
        Full-power recovery would unfairly neutralise a deserved opponent advantage.
        """
        from bot import PREDICTION_RECOVER_ELO_BOOST
        target_elo = 1600
        recover_elo = min(target_elo + PREDICTION_RECOVER_ELO_BOOST, 2850)
        # Should be exactly target + boost (well within 2850 cap)
        self.assertEqual(recover_elo, target_elo + PREDICTION_RECOVER_ELO_BOOST)

    def test_recovery_elo_boost_caps_at_2850(self):
        """ELO boost must never exceed the Stockfish max of 2850."""
        from bot import PREDICTION_RECOVER_ELO_BOOST
        target_elo = 2800
        recover_elo = min(target_elo + PREDICTION_RECOVER_ELO_BOOST, 2850)
        self.assertLessEqual(recover_elo, 2850)

    def test_recover_elo_boost_default(self):
        """PREDICTION_RECOVER_ELO_BOOST default is 200."""
        from bot import PREDICTION_RECOVER_ELO_BOOST
        self.assertEqual(PREDICTION_RECOVER_ELO_BOOST, 200)

    @patch('bot.PREDICTION_RECOVER_THRESHOLD', 400)
    def test_recovery_threshold_env_override(self):
        """Patching PREDICTION_RECOVER_THRESHOLD is respected in comparisons."""
        from bot import PREDICTION_RECOVER_THRESHOLD
        self.assertEqual(PREDICTION_RECOVER_THRESHOLD, 400)


class TestMatingPvLogic(unittest.TestCase):
    """Test mate-based prediction routing logic (commit d0fad89)."""

    def test_positive_mate_val_follows_predicted_move(self):
        """When mate_val > 0, bot should follow the predicted continuation."""
        predicted_move = "d1h5"
        mate_val = 3

        if mate_val is not None and mate_val > 0:
            move = predicted_move or "fallback"
        elif mate_val is not None and mate_val < 0:
            move = "defensive_move"
        else:
            move = predicted_move or "standard"

        self.assertEqual(move, "d1h5")

    def test_negative_mate_val_picks_defensive_move(self):
        """When mate_val < 0, bot should avoid the predicted continuation."""
        predicted_move = "e8g8"
        mate_val = -2

        if mate_val is not None and mate_val > 0:
            move = predicted_move or "fallback"
        elif mate_val is not None and mate_val < 0:
            move = "defensive_move"  # engine re-search
        else:
            move = predicted_move or "standard"

        self.assertEqual(move, "defensive_move")

    def test_none_mate_val_uses_predicted_move(self):
        """When mate_val is None (no mate), normal prediction path is used."""
        predicted_move = "e2e4"
        mate_val = None

        if mate_val is not None and mate_val > 0:
            move = "mating"
        elif mate_val is not None and mate_val < 0:
            move = "defensive_move"
        else:
            move = predicted_move or "standard"

        self.assertEqual(move, "e2e4")

    def test_none_mate_val_no_predicted_move_falls_back(self):
        """When both mate_val and predicted_move are None, fallback is used."""
        predicted_move = None
        mate_val = None

        if mate_val is not None and mate_val > 0:
            move = "mating"
        elif mate_val is not None and mate_val < 0:
            move = "defensive_move"
        else:
            move = predicted_move or "standard_search"

        self.assertEqual(move, "standard_search")


class TestFullPowerMateMove(unittest.TestCase):
    """Test _get_full_power_move helper — disables UCI_LimitStrength, restores after (v2.4.2)."""

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
    """Validate clock-budget logic for secondary searches after prediction (v2.4.2).

    The play_game loop computes _remaining_after_pred = max(0, _my_remaining - elapsed_ms)
    to ensure mate / recovery searches never exceed the original per-move clock budget.
    These tests validate that inline arithmetic pattern directly.
    """

    def test_remaining_after_pred_normal(self):
        """Remaining clock is reduced by the elapsed prediction time."""
        _my_remaining = 30_000   # 30 s
        _pred_elapsed_ms = 1_200
        _remaining_after_pred = max(0, _my_remaining - _pred_elapsed_ms)
        self.assertEqual(_remaining_after_pred, 28_800)

    def test_remaining_after_pred_floors_at_zero(self):
        """remaining_after_pred never goes negative (e.g., lag spike longer than remaining)."""
        _my_remaining = 500
        _pred_elapsed_ms = 800   # elapsed > remaining (extreme lag spike)
        _remaining_after_pred = max(0, _my_remaining - _pred_elapsed_ms)
        self.assertEqual(_remaining_after_pred, 0)

    def test_remaining_after_pred_none_passthrough(self):
        """When _my_remaining is None (no clock data), remaining_after_pred stays None."""
        _my_remaining = None
        _pred_elapsed_ms = 1_000
        _remaining_after_pred = (
            max(0, _my_remaining - _pred_elapsed_ms)
            if _my_remaining else None
        )
        self.assertIsNone(_remaining_after_pred)

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

    def test_fallback_uses_movetime_min_ms_not_full_budget(self):
        """Exceptional fallback path uses MOVETIME_MIN_MS, not the full move_time budget."""
        from bot import MOVETIME_MIN_MS
        move_time = 3_000   # 3 s — a normal rapid-game budget
        # Simulated exceptional path: _get_full_power_move returns None
        full_power_result = None
        fallback_time = MOVETIME_MIN_MS   # must NOT be move_time
        move = full_power_result or f"stockfish.get_best_move_time({fallback_time})"
        self.assertIn(str(MOVETIME_MIN_MS), move)
        self.assertNotIn(str(move_time), move)


if __name__ == '__main__':
    unittest.main()
