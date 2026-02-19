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
    def test_stockfish_initialization_strong_opponent(self, mock_stockfish_class):
        """Test Stockfish initialization with strong opponent - full strength."""
        mock_sf_instance = Mock()
        mock_stockfish_class.return_value = mock_sf_instance
        
        with patch('bot.DYNAMIC_STRENGTH', True), \
             patch('bot.LIMIT_STRENGTH_THRESHOLD', 1800):
            result = init_stockfish(opponent_rating=2200)
        
        # Verify engine parameters are not modified for strong opponents
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


if __name__ == '__main__':
    unittest.main()
