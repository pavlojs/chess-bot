"""
Unit tests for Axiom Chess Bot
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
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


if __name__ == '__main__':
    unittest.main()
