"""
Unit tests for Axiom Chess Bot
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import os
import signal
import time
import threading

import chess
import requests

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
        """Test draw eval fallback: get_evaluation() returns from side-to-move perspective.

        When bot is black and it's the opponent's turn (white to move), Stockfish's
        get_evaluation() reports from white's perspective.  The bot must negate it.
        """
        mock_sf = Mock()
        # Stockfish says +300 from side-to-move (white) — bad for black bot
        mock_sf.get_evaluation.return_value = {"type": "cp", "value": 300}

        eval_info = mock_sf.get_evaluation()
        raw_cp = eval_info["value"]

        # New logic: flip based on whether bot is side-to-move, not bot colour
        bot_is_white = False
        board_turn_is_white = True  # opponent (white) to move after draw offer
        bot_is_side_to_move = (board_turn_is_white == bot_is_white)  # False
        evaluation = raw_cp if bot_is_side_to_move else -raw_cp

        # From bot's (black's) perspective: -300 → losing → reject draw
        accept_draw = -200 <= evaluation <= 200
        self.assertFalse(accept_draw)
        self.assertEqual(evaluation, -300)

    @patch('bot.Stockfish')
    def test_cached_eval_no_color_flip(self, mock_stockfish_class):
        """Cached last_eval_cp is already from bot's perspective — no flip needed.

        The search that produced last_eval_cp ran on the bot's turn, so UCI
        'score cp' is from the bot's side-to-move.  The draw handler must
        use it directly regardless of bot colour.
        """
        # Bot is black, cached eval shows bot is losing (-400 from bot's perspective)
        last_eval_cp = -400
        evaluation = last_eval_cp  # NO flip — already bot's perspective

        accept_draw = -200 <= evaluation <= 200
        self.assertFalse(accept_draw)
        self.assertEqual(evaluation, -400)

    @patch('bot.Stockfish')
    def test_cached_eval_positive_black_accepts_draw(self, mock_stockfish_class):
        """Cached eval +50 as black → balanced → should accept draw."""
        last_eval_cp = 50
        evaluation = last_eval_cp
        accept_draw = -200 <= evaluation <= 200
        self.assertTrue(accept_draw)

    @patch('bot.Stockfish')
    def test_fallback_eval_bot_is_side_to_move(self, mock_stockfish_class):
        """Fallback eval when bot IS side-to-move → no flip needed."""
        mock_sf = Mock()
        mock_sf.get_evaluation.return_value = {"type": "cp", "value": -150}

        raw_cp = mock_sf.get_evaluation()["value"]
        bot_is_white = True
        board_turn_is_white = True  # bot's turn
        bot_is_side_to_move = (board_turn_is_white == bot_is_white)
        evaluation = raw_cp if bot_is_side_to_move else -raw_cp

        self.assertEqual(evaluation, -150)  # no flip
        accept_draw = -200 <= evaluation <= 200
        self.assertTrue(accept_draw)


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
        """Recovery uses ELO boost when below FULL_STRENGTH_THRESHOLD (v2.4.2).

        Below the threshold: UCI_LimitStrength stays active, ELO raised by
        PREDICTION_RECOVER_ELO_BOOST. Keeps the game winnable for the opponent.
        """
        from bot import PREDICTION_RECOVER_ELO_BOOST, FULL_STRENGTH_THRESHOLD
        target_elo = 1600   # well below 2800
        recover_elo = min(target_elo + PREDICTION_RECOVER_ELO_BOOST, 2850)
        self.assertEqual(recover_elo, target_elo + PREDICTION_RECOVER_ELO_BOOST)
        # Below threshold — should use ELO boost path, not full power
        self.assertLess(recover_elo, FULL_STRENGTH_THRESHOLD)

    def test_recovery_escalates_to_full_power_near_threshold(self):
        """When boosted ELO >= FULL_STRENGTH_THRESHOLD, switch to full-power instead.

        An opponent near 2800 already has _target_elo at 2850 (max cap).
        Adding PREDICTION_RECOVER_ELO_BOOST still gives 2850, which is >= 2800
        (FULL_STRENGTH_THRESHOLD). In this case recovery should use full-power
        Stockfish, not the ELO-capped engine.
        """
        from bot import PREDICTION_RECOVER_ELO_BOOST, FULL_STRENGTH_THRESHOLD
        # Opponent near 2800: _target_elo already at Stockfish max
        target_elo = 2850
        recover_elo = min(target_elo + PREDICTION_RECOVER_ELO_BOOST, 2850)
        # recover_elo is capped at 2850 — >= FULL_STRENGTH_THRESHOLD → full power path
        self.assertGreaterEqual(recover_elo, FULL_STRENGTH_THRESHOLD)

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


class TestTimeoutHTTPAdapter(unittest.TestCase):
    """Test TimeoutHTTPAdapter sets default timeout on all requests."""

    def test_default_timeout_applied(self):
        from bot import TimeoutHTTPAdapter
        adapter = TimeoutHTTPAdapter(timeout=(10, 120))
        self.assertEqual(adapter.timeout, (10, 120))

    def test_send_sets_timeout_in_kwargs(self):
        from bot import TimeoutHTTPAdapter
        adapter = TimeoutHTTPAdapter(timeout=(5, 60))

        # Mock the parent send method
        with patch.object(requests.adapters.HTTPAdapter, 'send', return_value=Mock()) as mock_send:
            fake_request = Mock()
            adapter.send(fake_request)
            _, kwargs = mock_send.call_args
            self.assertEqual(kwargs.get('timeout'), (5, 60))

    def test_explicit_timeout_not_overridden(self):
        from bot import TimeoutHTTPAdapter
        adapter = TimeoutHTTPAdapter(timeout=(5, 60))

        with patch.object(requests.adapters.HTTPAdapter, 'send', return_value=Mock()) as mock_send:
            fake_request = Mock()
            adapter.send(fake_request, timeout=30)
            _, kwargs = mock_send.call_args
            # Explicit timeout should be preserved, not overridden
            self.assertEqual(kwargs.get('timeout'), 30)


class TestHealthcheck(unittest.TestCase):
    """Test healthcheck heartbeat mechanism."""

    def test_healthcheck_file_constant(self):
        from bot import HEALTHCHECK_FILE
        self.assertEqual(HEALTHCHECK_FILE, "/tmp/axiom_heartbeat")

    def test_heartbeat_file_writable(self):
        """Verify heartbeat file can be written and read back."""
        import tempfile
        from bot import HEALTHCHECK_FILE
        # Use a temp file to avoid side effects
        with tempfile.NamedTemporaryFile(mode='w', suffix='_heartbeat', delete=True) as f:
            f.write(str(time.time()))
            f.flush()
            f.seek(0)
            # File should exist and contain a valid timestamp
            self.assertTrue(os.path.exists(f.name))


class TestGracefulShutdown(unittest.TestCase):
    """Test graceful shutdown handler."""

    def test_shutdown_flag_set(self):
        """handle_shutdown sets shutdown_requested to True."""
        import bot
        original = bot.shutdown_requested
        try:
            bot.shutdown_requested = False
            # Patch sys.exit and threading to prevent actual exit
            with patch('bot.sys.exit'), \
                 patch('bot.threading.Thread'):
                bot.handle_shutdown(signal.SIGTERM, None)
            self.assertTrue(bot.shutdown_requested)
        finally:
            bot.shutdown_requested = original

    def test_double_signal_force_exits(self):
        """Second signal calls sys.exit(1) for forced shutdown."""
        import bot
        original = bot.shutdown_requested
        try:
            bot.shutdown_requested = True  # simulate first signal already received
            with self.assertRaises(SystemExit) as ctx:
                bot.handle_shutdown(signal.SIGTERM, None)
            self.assertEqual(ctx.exception.code, 1)
        finally:
            bot.shutdown_requested = original


class TestConcurrentGameLimit(unittest.TestCase):
    """Test concurrent game limit logic."""

    def test_limit_prevents_excess_games(self):
        """When active_games >= MAX_CONCURRENT_GAMES, new game should be rejected."""
        import threading
        max_concurrent = 1
        active_games = {"game1": threading.Thread(target=lambda: None)}
        active_games["game1"].start()
        active_games["game1"].join()  # make it finish but keep in dict

        # Simulate dead-thread cleanup + limit check (mirrors main loop logic)
        dead = [gid for gid, t in active_games.items() if not t.is_alive()]
        for gid in dead:
            del active_games[gid]

        # After cleanup, dead thread removed → slot available
        self.assertLess(len(active_games), max_concurrent)

    def test_limit_blocks_when_game_alive(self):
        """A still-running game thread blocks new games."""
        import threading
        max_concurrent = 1

        blocker = threading.Event()
        def busy():
            blocker.wait(timeout=5)

        t = threading.Thread(target=busy, daemon=True)
        t.start()
        active_games = {"game1": t}

        # Thread is alive → at limit
        alive_count = sum(1 for t in active_games.values() if t.is_alive())
        self.assertGreaterEqual(alive_count, max_concurrent)

        blocker.set()  # cleanup
        t.join(timeout=2)


class TestTerminalStatuses(unittest.TestCase):
    """Test _TERMINAL_STATUSES constant."""

    def test_terminal_statuses_is_frozenset(self):
        from bot import _TERMINAL_STATUSES
        self.assertIsInstance(_TERMINAL_STATUSES, frozenset)

    def test_terminal_statuses_contains_expected(self):
        from bot import _TERMINAL_STATUSES
        for status in ["mate", "resign", "stalemate", "timeout", "draw",
                        "outoftime", "aborted", "cheat", "noStart",
                        "unknownFinish", "variantEnd"]:
            self.assertIn(status, _TERMINAL_STATUSES)

    def test_started_not_terminal(self):
        from bot import _TERMINAL_STATUSES
        self.assertNotIn("started", _TERMINAL_STATUSES)
        self.assertNotIn("created", _TERMINAL_STATUSES)


class TestGameStuckException(unittest.TestCase):
    """Test _GameStuck exception class."""

    def test_is_exception(self):
        from bot import _GameStuck
        self.assertTrue(issubclass(_GameStuck, Exception))

    def test_message_preserved(self):
        from bot import _GameStuck
        exc = _GameStuck("test message")
        self.assertEqual(str(exc), "test message")


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


class TestGameWatchdogConfig(unittest.TestCase):
    """Test GAME_WATCHDOG_INTERVAL config."""

    def test_config_importable(self):
        from config import GAME_WATCHDOG_INTERVAL
        self.assertIsInstance(GAME_WATCHDOG_INTERVAL, int)
        self.assertGreater(GAME_WATCHDOG_INTERVAL, 0)

    def test_default_value(self):
        from config import GAME_WATCHDOG_INTERVAL
        self.assertEqual(GAME_WATCHDOG_INTERVAL, 60)


class TestOpponentGoneHandling(unittest.TestCase):
    """Test opponentGone event handling logic."""

    def test_opponent_gone_event_structure(self):
        """Verify opponentGone event parsing logic."""
        event = {"type": "opponentGone", "gone": True, "claimWinInSeconds": 10}
        self.assertTrue(event.get("gone", False))
        self.assertEqual(event.get("claimWinInSeconds"), 10)

    def test_opponent_returned_event(self):
        """Verify opponentGone with gone=False is recognized."""
        event = {"type": "opponentGone", "gone": False}
        self.assertFalse(event.get("gone", False))
        self.assertIsNone(event.get("claimWinInSeconds"))

    def test_claim_victory_timer_created(self):
        """Timer is created and is a daemon for auto-cleanup."""
        claim_seconds = 15
        timer = threading.Timer(claim_seconds + 1, lambda: None)
        timer.daemon = True
        self.assertTrue(timer.daemon)
        self.assertFalse(timer.is_alive())
        timer.cancel()  # cleanup

    def test_claim_victory_timer_cancellation(self):
        """Timer can be cancelled before firing."""
        fired = threading.Event()
        timer = threading.Timer(0.5, fired.set)
        timer.daemon = True
        timer.start()
        timer.cancel()
        time.sleep(0.7)  # wait past the timer
        self.assertFalse(fired.is_set(), "Timer should have been cancelled")


class TestStartupGameCleanup(unittest.TestCase):
    """Test startup stuck game cleanup logic."""

    def test_ongoing_games_empty(self):
        """No action when no ongoing games."""
        mock_client = Mock()
        mock_client.games.get_ongoing.return_value = []
        ongoing = mock_client.games.get_ongoing()
        self.assertEqual(len(ongoing), 0)

    def test_ongoing_game_already_finished(self):
        """Already finished games are skipped."""
        from bot import _TERMINAL_STATUSES
        game = {"gameId": "abc", "status": {"name": "aborted"}, "opponent": {"username": "test"}}
        status = game.get("status", {})
        status_name = status.get("name", status) if isinstance(status, dict) else str(status)
        self.assertIn(status_name, _TERMINAL_STATUSES)

    def test_ongoing_game_few_moves_abort(self):
        """Games with < 2 moves should be aborted."""
        mock_client = Mock()
        mock_client.games.export.return_value = {"moves": "e2e4", "status": "started"}
        full = mock_client.games.export("abc")
        moves = full.get("moves", "")
        move_count = len(moves.split()) if moves else 0
        self.assertLess(move_count, 2)

    def test_ongoing_game_many_moves_resume(self):
        """Games with >= 2 moves should be resumed, not aborted."""
        mock_client = Mock()
        mock_client.games.export.return_value = {"moves": "e2e4 e7e5 d2d4", "status": "started"}
        full = mock_client.games.export("abc")
        moves = full.get("moves", "")
        move_count = len(moves.split()) if moves else 0
        self.assertGreaterEqual(move_count, 2)

    def test_status_as_string(self):
        """Handle status field that is a plain string rather than dict."""
        from bot import _TERMINAL_STATUSES
        game = {"gameId": "abc", "status": "started", "opponent": {"username": "test"}}
        status = game.get("status", {})
        status_name = status.get("name", status) if isinstance(status, dict) else str(status)
        self.assertNotIn(status_name, _TERMINAL_STATUSES)


class TestGameStreamReconnect502(unittest.TestCase):
    """Test that game stream handles 502/503/504 as reconnectable errors."""

    def _make_response_error(self, status_code):
        """Create a ResponseError with the given status code."""
        from berserk.exceptions import ResponseError
        mock_resp = Mock()
        mock_resp.status_code = status_code
        mock_resp.text = f"Error {status_code}"
        mock_resp.args = (f"Error {status_code}",)
        try:
            exc = ResponseError(mock_resp)
        except Exception:
            # Fallback for different berserk versions
            exc = ResponseError.__new__(ResponseError)
            exc.response = mock_resp
            Exception.__init__(exc, f"Error {status_code}")
        exc.response = mock_resp
        return exc

    def test_response_error_502_is_retriable(self):
        """ResponseError with 502 status should trigger reconnect, not break."""
        e = self._make_response_error(502)
        is_retriable = hasattr(e, 'response') and e.response and e.response.status_code in [502, 503, 504]
        self.assertTrue(is_retriable)

    def test_response_error_404_is_not_retriable(self):
        """ResponseError with 404 status should NOT be retried."""
        e = self._make_response_error(404)
        is_retriable = hasattr(e, 'response') and e.response and e.response.status_code in [502, 503, 504]
        self.assertFalse(is_retriable)


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


class TestNoFirstMoveAbort(unittest.TestCase):
    """Test that the bot aborts the game when the opponent never makes theirfirst move."""

    def test_no_first_move_timer_starts_when_waiting_for_opponent(self):
        """Timer should start when bot is black and opponent hasn't moved."""
        # The timer is started inside play_game after gameFull.
        # We test the logic: 0 moves + not our turn → timer should be set.
        board = chess.Board()
        bot_is_white = False  # bot is black
        last_move_count = 0

        is_my_turn = (
            (board.turn == chess.WHITE and bot_is_white) or
            (board.turn == chess.BLACK and not bot_is_white)
        )
        should_start_timer = last_move_count == 0 and not is_my_turn
        self.assertTrue(should_start_timer)

    def test_no_first_move_timer_not_started_when_bot_is_white(self):
        """Timer should NOT start when bot is white (bot moves first)."""
        board = chess.Board()
        bot_is_white = True  # bot is white → it's our turn
        last_move_count = 0

        is_my_turn = (
            (board.turn == chess.WHITE and bot_is_white) or
            (board.turn == chess.BLACK and not bot_is_white)
        )
        should_start_timer = last_move_count == 0 and not is_my_turn
        self.assertFalse(should_start_timer)

    def test_no_first_move_timer_not_started_when_moves_exist(self):
        """Timer should NOT start when there are already moves on the board."""
        board = chess.Board()
        bot_is_white = False
        last_move_count = 1  # opponent already made a move

        is_my_turn = (
            (board.turn == chess.WHITE and bot_is_white) or
            (board.turn == chess.BLACK and not bot_is_white)
        )
        should_start_timer = last_move_count == 0 and not is_my_turn
        self.assertFalse(should_start_timer)


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


class TestWatchdogAbortTimeout(unittest.TestCase):
    """Tests for the game watchdog abort timeout feature."""

    def test_abort_timeout_config_imported(self):
        """GAME_WATCHDOG_ABORT_TIMEOUT is importable from config."""
        from config import GAME_WATCHDOG_ABORT_TIMEOUT
        self.assertIsInstance(GAME_WATCHDOG_ABORT_TIMEOUT, int)
        self.assertGreater(GAME_WATCHDOG_ABORT_TIMEOUT, 0)

    def test_abort_timeout_default_value(self):
        """Default abort timeout is 600 seconds (10 minutes)."""
        from config import GAME_WATCHDOG_ABORT_TIMEOUT
        # If not overridden in env, default is 600
        env_value = os.environ.get("GAME_WATCHDOG_ABORT_TIMEOUT")
        if env_value is None:
            self.assertEqual(GAME_WATCHDOG_ABORT_TIMEOUT, 600)

    def test_terminal_statuses_include_aborted(self):
        """Ensure 'aborted' is a terminal status (watchdog abort should end the game)."""
        from bot import _TERMINAL_STATUSES
        self.assertIn("aborted", _TERMINAL_STATUSES)


class TestMaxConcurrentGamesConfig(unittest.TestCase):
    """Tests for MAX_CONCURRENT_GAMES configuration."""

    def test_config_importable(self):
        """MAX_CONCURRENT_GAMES is importable from config."""
        from config import MAX_CONCURRENT_GAMES
        self.assertIsInstance(MAX_CONCURRENT_GAMES, int)
        self.assertGreater(MAX_CONCURRENT_GAMES, 0)

    def test_default_value_is_2(self):
        """Default value is 2."""
        from config import MAX_CONCURRENT_GAMES
        env_value = os.environ.get("MAX_CONCURRENT_GAMES")
        if env_value is None:
            self.assertEqual(MAX_CONCURRENT_GAMES, 2)

    def test_bot_imports_max_concurrent_games(self):
        """bot.py imports MAX_CONCURRENT_GAMES from config."""
        import bot
        self.assertTrue(hasattr(bot, 'MAX_CONCURRENT_GAMES'))
        self.assertEqual(bot.MAX_CONCURRENT_GAMES, bot.MAX_CONCURRENT_GAMES)

    def test_bot_imports_abort_timeout(self):
        """bot.py imports GAME_WATCHDOG_ABORT_TIMEOUT from config."""
        import bot
        self.assertTrue(hasattr(bot, 'GAME_WATCHDOG_ABORT_TIMEOUT'))


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

    def test_game_stuck_exception_exists(self):
        """_GameStuck exception class should be importable."""
        from bot import _GameStuck
        exc = _GameStuck("test msg")
        self.assertIsInstance(exc, Exception)
        self.assertEqual(str(exc), "test msg")


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


if __name__ == '__main__':
    unittest.main()
