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


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def forward(self, seconds):
        self.now += seconds


class TestOpponentRests(unittest.TestCase):
    """How long a bot is left alone depends on what it did with the last challenge."""

    MINUTE, HOUR, DAY = 60, 3600, 86400

    def setUp(self):
        from bot import OpponentRests
        self.clock = Clock()
        self.rests = OpponentRests(self.clock)

    def test_a_bot_nothing_is_held_against_is_not_resting(self):
        self.assertFalse(self.rests.resting("SomeBot", "blitz"))

    def test_later_means_a_quarter_of_an_hour(self):
        self.assertEqual(self.rests.declined("BusyBot", "blitz", "later"), 15 * self.MINUTE)

        self.assertTrue(self.rests.resting("BusyBot", "blitz"))
        self.assertTrue(self.rests.resting("BusyBot", "rapid"))      # busy is busy at any speed
        self.clock.forward(15 * self.MINUTE)
        self.assertFalse(self.rests.resting("BusyBot", "blitz"))

    def test_later_stays_a_quarter_of_an_hour_however_often(self):
        for _ in range(4):
            self.assertEqual(self.rests.declined("BusyBot", "blitz", "later"), 15 * self.MINUTE)

    def test_an_unwanted_speed_rests_that_speed_only_for_a_day(self):
        for reason in ("toofast", "tooslow", "timecontrol"):         # as an event spells them
            with self.subTest(reason=reason):
                self.assertEqual(self.rests.declined(f"Picky{reason}", "bullet", reason), self.DAY)
                self.assertTrue(self.rests.resting(f"Picky{reason}", "bullet"))
                self.assertFalse(self.rests.resting(f"Picky{reason}", "rapid"))

    def test_a_bot_that_takes_no_such_challenge_at_all_rests_a_week(self):
        for reason in ("nobot", "casual", "variant"):
            with self.subTest(reason=reason):
                self.assertEqual(self.rests.declined(f"Never{reason}", "blitz", reason), 7 * self.DAY)
                self.assertTrue(self.rests.resting(f"Never{reason}", "classical"))

    def test_a_reason_is_understood_in_the_spelling_of_the_api_documentation_too(self):
        self.assertEqual(self.rests.declined("NeverBot", "blitz", "noBot"), 7 * self.DAY)
        self.assertEqual(self.rests.declined("PickyBot", "bullet", "tooFast"), self.DAY)

    def test_the_other_reasons_say_nothing_lasting_about_a_rated_standard_challenge_from_a_bot(self):
        for reason in ("generic", "rated", "standard", "onlybot", "something lichess adds later"):
            with self.subTest(reason=reason):
                self.assertEqual(self.rests.declined(f"Odd{reason}", "blitz", reason), self.HOUR)

    def test_a_speed_reason_without_a_known_speed_counts_like_no_reason(self):
        self.assertEqual(self.rests.declined("PickyBot", None, "toofast"), self.HOUR)

    def test_no_answer_rests_an_hour_then_twice_as_long_each_time_in_a_row(self):
        spans = []
        for _ in range(7):
            spans.append(self.rests.unanswered("AwayBot"))
            self.clock.forward(spans[-1] + 1)       # challenged again as soon as the rest is over

        hours = [span / self.HOUR for span in spans]
        self.assertEqual(hours, [1, 2, 4, 8, 16, 24, 24])       # and never more than a day

    def test_a_decline_without_a_reason_counts_like_no_answer(self):
        self.assertEqual(self.rests.declined("VagueBot", "blitz", "generic"), self.HOUR)
        self.clock.forward(self.HOUR + 1)
        self.assertEqual(self.rests.unanswered("VagueBot"), 2 * self.HOUR)

    def test_in_a_row_ends_after_a_day_of_peace(self):
        self.rests.unanswered("AwayBot")
        self.clock.forward(self.HOUR + self.DAY + 1)             # the rest ended more than a day ago

        self.assertEqual(self.rests.unanswered("AwayBot"), self.HOUR)

    def test_a_refusal_by_lichess_lasts_as_long_as_lichess_says(self):
        self.assertEqual(self.rests.refused("TiredBot", 5000), 5000)
        self.clock.forward(4999)
        self.assertTrue(self.rests.resting("TiredBot", "blitz"))
        self.clock.forward(2)
        self.assertFalse(self.rests.resting("TiredBot", "blitz"))

    def test_a_refusal_without_a_time_lasts_six_hours(self):
        self.assertEqual(self.rests.refused("ClosedBot"), 6 * self.HOUR)

    def test_later_does_not_count_towards_the_doubling(self):
        for _ in range(3):
            self.rests.declined("BusyBot", "blitz", "later")
            self.clock.forward(15 * self.MINUTE + 1)

        self.assertEqual(self.rests.unanswered("BusyBot"), self.HOUR)

    def test_a_rest_is_never_cut_short_by_a_shorter_one(self):
        self.rests.declined("NeverBot", "blitz", "nobot")
        self.clock.forward(self.HOUR)

        left = self.rests.declined("NeverBot", "blitz", "later")       # a late answer to an older challenge

        self.assertEqual(left, 7 * self.DAY - self.HOUR)
        self.clock.forward(6 * self.DAY)
        self.assertTrue(self.rests.resting("NeverBot", "blitz"))

    def test_a_bot_that_plays_is_cleared(self):
        self.rests.unanswered("ComeBackBot")

        self.rests.played("ComeBackBot", "blitz")

        self.assertFalse(self.rests.resting("ComeBackBot", "blitz"))
        self.assertEqual(self.rests.unanswered("ComeBackBot"), self.HOUR)     # and counts from one again

    def test_a_game_at_one_speed_does_not_undo_the_decline_of_another(self):
        self.rests.declined("PickyBot", "bullet", "toofast")
        self.rests.declined("PickyBot", "blitz", "timecontrol")

        self.rests.played("PickyBot", "blitz")

        self.assertTrue(self.rests.resting("PickyBot", "bullet"))
        self.assertFalse(self.rests.resting("PickyBot", "blitz"))

    def test_names_are_matched_whatever_their_case(self):
        self.rests.declined("LeelaQueenOdds", "blitz", "nobot")

        self.assertTrue(self.rests.resting("leelaqueenodds", "blitz"))
        self.rests.played("LEELAQUEENODDS")
        self.assertFalse(self.rests.resting("LeelaQueenOdds", "blitz"))

    def test_clearing_one_bot_leaves_a_bot_with_a_longer_name_alone(self):
        self.rests.declined("Bot", "blitz", "nobot")
        self.rests.declined("Bot2", "blitz", "nobot")

        self.rests.played("Bot", "blitz")

        self.assertTrue(self.rests.resting("Bot2", "blitz"))

    def test_bots_are_counted_once_and_only_while_they_rest(self):
        self.rests.declined("PickyBot", "bullet", "toofast")
        self.rests.declined("PickyBot", "rapid", "tooslow")
        self.rests.declined("BusyBot", "blitz", "later")
        self.assertEqual(self.rests.count(), 2)

        self.clock.forward(self.HOUR)                    # BusyBot's quarter of an hour is over

        self.assertEqual(self.rests.count(), 1)

    def test_what_is_written_down_is_taken_over_by_the_next_run(self):
        from bot import OpponentRests
        self.rests.declined("NeverBot", "blitz", "nobot")
        self.rests.declined("PickyBot", "bullet", "toofast")
        self.rests.unanswered("AwayBot")
        self.clock.forward(self.HOUR + 1)
        self.rests.unanswered("AwayBot")                                   # second time in a row
        written = self.rests.export()

        self.clock.forward(30 * self.MINUTE)                               # the bot was down for a while
        after_restart = OpponentRests(self.clock)
        after_restart.restore(written)

        self.assertTrue(after_restart.resting("NeverBot", "rapid"))
        self.assertTrue(after_restart.resting("PickyBot", "bullet"))
        self.assertFalse(after_restart.resting("PickyBot", "blitz"))
        self.assertTrue(after_restart.resting("AwayBot", "blitz"))
        self.clock.forward(2 * self.HOUR)
        self.assertEqual(after_restart.unanswered("AwayBot"), 4 * self.HOUR)  # the count came along

    def test_rests_that_are_long_over_are_not_written_down(self):
        self.rests.declined("BusyBot", "blitz", "later")
        self.clock.forward(2 * self.DAY)

        self.assertEqual(self.rests.export(), {})

    def test_a_damaged_record_is_ignored(self):
        from bot import OpponentRests
        for damaged in (None, "text", [1, 2], {"bot": "soon"}, {"bot": [1]}, {"bot": ["a", "b"]}, {5: [1, 2]},
                        {"bot": [True, False]}):
            with self.subTest(damaged=damaged):
                rests = OpponentRests(self.clock)
                rests.restore(damaged)
                self.assertEqual(rests.export(), {})


class TestChallengeMemory(unittest.TestCase):
    """The challenges of the last day count across a restart, as they do at Lichess."""

    def setUp(self):
        self.wall = Clock(1_800_000_000.0)

    def tracker(self, running_for=0.0, per_hour=10, per_day=180):
        """A tracker in a process that has been running for ``running_for`` seconds."""
        from bot import ChallengeTracker
        offset = self.wall.now - running_for
        return ChallengeTracker(per_hour, per_day, clock=lambda: self.wall.now - offset, wall_clock=self.wall)

    def test_attempts_are_taken_over_at_the_age_they_had(self):
        before = self.tracker(running_for=5000)
        for _ in range(3):
            before.record_challenge()
            self.wall.forward(600)
        written = before.export()

        self.wall.forward(120)                      # down for two minutes
        after = self.tracker()
        after.restore(written)

        self.assertEqual(after.counts(), (3, 3))
        self.assertEqual(after.get_remaining_challenges(), 7)

    def test_a_restart_does_not_hand_out_a_fresh_allowance(self):
        """The reason the count is kept: a full day's worth sent, then a restart."""
        before = self.tracker(per_hour=1000, per_day=180)
        for _ in range(180):
            before.record_challenge()
            self.wall.forward(60)
        self.assertFalse(before.can_challenge())

        after = self.tracker(per_hour=1000, per_day=180)
        after.restore(before.export())

        self.assertFalse(after.can_challenge())
        self.assertGreater(after.seconds_until_free(), 20 * 3600)

    def test_the_hourly_limit_is_also_kept(self):
        before = self.tracker(per_hour=2)
        before.record_challenge()
        before.record_challenge()

        self.wall.forward(600)
        after = self.tracker(per_hour=2)
        after.restore(before.export())

        self.assertFalse(after.can_challenge())
        self.assertEqual(after.seconds_until_free(), 3000)

    def test_attempts_older_than_a_day_are_left_behind(self):
        before = self.tracker()
        before.record_challenge()
        written = before.export()

        self.wall.forward(86400 + 1)
        after = self.tracker()
        after.restore(written)

        self.assertEqual(after.counts(), (0, 0))

    def test_a_time_ahead_of_the_clock_counts_as_just_made(self):
        """Written before the clock was set back. Forgetting it would hand out a challenge Lichess has counted."""
        after = self.tracker(per_hour=1)
        after.restore([self.wall.now + 30])

        self.assertEqual(after.counts(), (1, 1))
        self.assertEqual(after.seconds_until_free(), 3600)

    def test_what_is_written_down_does_not_change_while_nothing_happens(self):
        tracker = self.tracker()
        tracker.record_challenge()
        written = tracker.export()

        self.wall.forward(0.0004)                # the two clocks never tick in step

        self.assertEqual(tracker.export(), written)

    def test_a_damaged_record_is_ignored(self):
        for damaged in (None, "text", {"a": 1}, ["x", None, {}, True]):
            with self.subTest(damaged=damaged):
                tracker = self.tracker()
                tracker.restore(damaged)
                self.assertEqual(tracker.counts(), (0, 0))


class TestStateFile(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.directory, ignore_errors=True))
        self.path = os.path.join(self.directory, "state.json")

    def store(self, path=None):
        from bot import StateFile
        return StateFile(path or self.path)

    def test_what_is_saved_is_what_is_loaded(self):
        data = {"challenges": [1.5, 2.5], "rests": {"bot": [9.0, 2]}}
        self.store().save(data)

        self.assertEqual(self.store().load(), data)
        self.assertEqual(os.listdir(self.directory), ["state.json"])      # no scratch file left

    def test_no_file_means_nothing_remembered(self):
        self.assertEqual(self.store().load(), {})

    def test_a_file_that_is_not_json_means_nothing_remembered(self):
        for content in ("", "{half a file", "[1, 2, 3]", "null"):
            with self.subTest(content=content):
                with open(self.path, "w") as f:
                    f.write(content)
                self.assertEqual(self.store().load(), {})

    def test_a_place_that_cannot_be_written_does_not_stop_the_bot(self):
        store = self.store(os.path.join(self.directory, "no", "such", "directory", "state.json"))

        store.save({"challenges": []})          # must not raise
        store.save({"challenges": []})

        self.assertEqual(store.load(), {})

    def test_a_save_replaces_the_file_whole(self):
        self.store().save({"challenges": list(range(1000))})
        self.store().save({"challenges": [1]})

        self.assertEqual(self.store().load(), {"challenges": [1]})

    def test_nothing_is_written_while_nothing_has_changed(self):
        store = self.store()
        store.save({"challenges": [1.5]})
        written = os.stat(self.path).st_ino      # a save puts a new file in place

        store.save({"challenges": [1.5]})
        self.assertEqual(os.stat(self.path).st_ino, written)

        store.save({"challenges": [1.5, 2.5]})
        self.assertNotEqual(os.stat(self.path).st_ino, written)

    def test_a_save_that_failed_is_tried_again(self):
        missing = os.path.join(self.directory, "later")
        store = self.store(os.path.join(missing, "state.json"))
        store.save({"challenges": [1.5]})

        os.mkdir(missing)                        # the log directory turns up
        store.save({"challenges": [1.5]})

        self.assertEqual(store.load(), {"challenges": [1.5]})


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
        from bot import ChallengeTracker, try_challenge_random_bot
        client = Mock()
        client.bots.get_online_bots.return_value = iter([
            self.bot("BulletWeak", blitz=2000, bullet=900),
            self.bot("BulletFine", blitz=1000, bullet=2000),
        ])
        client.challenges.create.return_value = {"id": "chal0001"}
        tracker = ChallengeTracker(5, 100)

        with patch("bot.ENABLE_AUTO_CHALLENGE", True), \
             patch("bot.CHALLENGE_TIME_CONTROLS", [{"limit": 60, "increment": 0}]), \
             patch("bot.CHALLENGE_MIN_RATING", 1500), patch("bot.CHALLENGE_MAX_RATING", 2900):
            result = try_challenge_random_bot(client, "Axiom_BOT", tracker)

        self.assertEqual(result, ("chal0001", "BulletFine", "bullet"))
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
        import stockfish_updater

        binary_name = stockfish_updater.get_binary_name()

        # Should return a valid binary name
        self.assertIsInstance(binary_name, str)
        self.assertTrue(binary_name.startswith("stockfish-"))
    
    def test_get_installed_version(self):
        """Test version detection of installed Stockfish."""
        import stockfish_updater

        version = stockfish_updater.get_installed_version()
        
        # Should return either None or a version string
        if version is not None:
            self.assertIsInstance(version, str)
    
    def test_binary_name_is_a_universal_build(self):
        """Stockfish 19+ only ships universal builds; the old per-microarch
        assets (stockfish-ubuntu-x86-64) are the generic SSE2 build and no
        longer exist in the release."""
        import stockfish_updater

        binary_name = stockfish_updater.get_binary_name()

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

    DOWNLOADS = "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/"

    def asset(self, name, digest="sha256:" + "ab" * 32, url=None):
        return {"name": name, "digest": digest, "browser_download_url": url or self.DOWNLOADS + name}

    def test_asset_lookup_returns_the_address_and_checksum_of_this_platforms_archive(self):
        import stockfish_updater

        release = {"tag_name": "sf_19", "assets": [
            self.asset("stockfish-linux-arm64-universal.tar.gz", digest="sha256:" + "11" * 32),
            self.asset("stockfish-linux-x86-64-universal.tar.gz", digest="sha256:" + "22" * 32),
        ]}

        url, sha256 = stockfish_updater.find_release_asset("stockfish-linux-x86-64-universal", release)

        self.assertEqual(url, self.DOWNLOADS + "stockfish-linux-x86-64-universal.tar.gz")
        self.assertEqual(sha256, "22" * 32)

    def test_asset_lookup_reports_available_assets_when_missing(self):
        """A missing asset names what the release does contain, so the failure
        is diagnosable rather than a bare lookup error."""
        import stockfish_updater

        release = {"tag_name": "sf_19", "assets": [self.asset("stockfish-macos-universal.tar.gz")]}
        with self.assertRaises(RuntimeError) as ctx:
            stockfish_updater.find_release_asset("stockfish-linux-x86-64-universal", release)

        self.assertIn("stockfish-macos-universal.tar.gz", str(ctx.exception))

    def test_an_archive_without_a_published_checksum_is_refused(self):
        import stockfish_updater

        for digest in (None, "", "md5:abcdef"):
            with self.subTest(digest=digest):
                release = {"assets": [self.asset("stockfish-linux-x86-64-universal.tar.gz", digest=digest)]}
                with self.assertRaises(RuntimeError) as ctx:
                    stockfish_updater.find_release_asset("stockfish-linux-x86-64-universal", release)
                self.assertIn("SHA-256", str(ctx.exception))

    def test_a_download_address_outside_the_stockfish_releases_is_refused(self):
        """The address comes out of an API response and what it points at is run."""
        import stockfish_updater

        for url in (
            "https://evil.example.com/payload.tar.gz",
            "https://github.com/someone-else/Stockfish/releases/download/sf_19/x.tar.gz",
            "http://github.com/official-stockfish/Stockfish/releases/download/sf_19/x.tar.gz",
            "https://github.com.evil.example/official-stockfish/Stockfish/releases/download/x.tar.gz",
        ):
            with self.subTest(url=url):
                release = {"assets": [self.asset("stockfish-linux-x86-64-universal.tar.gz", url=url)]}
                with self.assertRaises(RuntimeError) as ctx:
                    stockfish_updater.find_release_asset("stockfish-linux-x86-64-universal", release)
                self.assertIn("unexpected address", str(ctx.exception))

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


class TestStockfishInstall(unittest.TestCase):
    """Download, check and install, against a local server standing in for GitHub."""

    BINARY = "stockfish-linux-x86-64-universal"

    def setUp(self):
        import io
        import tarfile
        import tempfile
        from lichess_stub import StubLichess

        self.server = StubLichess()
        self.addCleanup(self.server.close)
        self.directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.directory, ignore_errors=True))
        self.target = os.path.join(self.directory, "installed-stockfish")

        # An archive laid out like a release: the binary nested in a directory.
        self.engine = b"#!/bin/sh\necho engine\n"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            info = tarfile.TarInfo(f"stockfish/{self.BINARY}")
            info.size = len(self.engine)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(self.engine))
        self.archive = buffer.getvalue()
        self.sha256 = __import__("hashlib").sha256(self.archive).hexdigest()

        self.server.reply("GET", f"/download/{self.BINARY}.tar.gz", 200, self.archive)
        self.url = f"{self.server.url}/download/{self.BINARY}.tar.gz"
        for target, value in {
            "stockfish_updater.RELEASE_DOWNLOAD_PREFIX": f"{self.server.url}/download/",
            "stockfish_updater.INSTALL_PATH": self.target,
            "stockfish_updater.GITHUB_API": f"{self.server.url}/releases/latest",
        }.items():
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_matching_archive_is_installed_and_executable(self):
        import stockfish_updater

        stockfish_updater.download_and_install(self.url, self.sha256, self.BINARY)

        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), self.engine)
        self.assertEqual(os.stat(self.target).st_mode & 0o777, 0o755)

    def test_an_archive_that_differs_from_the_published_checksum_is_not_installed(self):
        import stockfish_updater

        with self.assertRaises(RuntimeError) as ctx:
            stockfish_updater.download_and_install(self.url, "00" * 32, self.BINARY)

        self.assertIn("does not match", str(ctx.exception))
        self.assertFalse(os.path.exists(self.target))

    def test_the_checksum_is_compared_without_regard_to_case(self):
        import stockfish_updater

        stockfish_updater.download_and_install(self.url, self.sha256.upper(), self.BINARY)

        self.assertTrue(os.path.exists(self.target))

    def test_an_archive_without_the_expected_binary_is_not_installed(self):
        import stockfish_updater

        with self.assertRaises(RuntimeError) as ctx:
            stockfish_updater.download_and_install(self.url, self.sha256, "stockfish-linux-arm64-universal")

        self.assertIn("Could not find", str(ctx.exception))
        self.assertFalse(os.path.exists(self.target))

    def test_nothing_is_fetched_from_an_address_outside_the_releases(self):
        import stockfish_updater

        with self.assertRaises(RuntimeError):
            stockfish_updater.download_and_install(f"{self.server.url}/elsewhere/x.tar.gz", self.sha256, self.BINARY)

        self.assertEqual(self.server.requests, [])

    def test_a_missing_engine_is_installed_from_the_latest_release(self):
        import stockfish_updater

        self.server.reply("GET", "/releases/latest", 200, {"tag_name": "sf_19", "assets": [
            {"name": f"{self.BINARY}.tar.gz", "digest": f"sha256:{self.sha256}", "browser_download_url": self.url},
        ]})
        with patch("stockfish_updater.get_binary_name", return_value=self.BINARY), \
             patch("stockfish_updater.log_build_info"):
            path = stockfish_updater.ensure_stockfish_installed(auto_update=True)

        self.assertEqual(path, self.target)
        self.assertTrue(os.access(self.target, os.X_OK))

    def test_an_engine_that_is_present_is_left_alone_without_auto_update(self):
        import stockfish_updater

        with open(self.target, "w") as f:
            f.write("#!/bin/sh\necho 'Stockfish 18 by the Stockfish developers'\n")
        os.chmod(self.target, 0o700)

        with patch("stockfish_updater.get_binary_name", return_value=self.BINARY), \
             patch("stockfish_updater.log_build_info"):
            path = stockfish_updater.ensure_stockfish_installed(auto_update=False)

        self.assertEqual(path, self.target)
        self.assertEqual(self.server.requests, [])

    def test_an_older_engine_is_replaced_and_a_current_one_is_not(self):
        import stockfish_updater

        release = {"assets": [{"name": f"{self.BINARY}.tar.gz", "digest": f"sha256:{self.sha256}", "browser_download_url": self.url}]}
        for installed, latest, replaced in (("18", "sf_19", True), ("19", "sf_19", False)):
            with self.subTest(installed=installed, latest=latest):
                with open(self.target, "w") as f:
                    f.write(f"#!/bin/sh\necho 'Stockfish {installed} by the Stockfish developers'\n")
                os.chmod(self.target, 0o700)
                self.server.reply("GET", "/releases/latest", 200, {"tag_name": latest, **release})

                with patch("stockfish_updater.get_binary_name", return_value=self.BINARY), \
                     patch("stockfish_updater.log_build_info"):
                    stockfish_updater.ensure_stockfish_installed(auto_update=True)

                with open(self.target, "rb") as f:
                    self.assertEqual(f.read() == self.engine, replaced)

    def test_a_failed_update_check_keeps_the_installed_engine(self):
        import stockfish_updater

        with open(self.target, "w") as f:
            f.write("#!/bin/sh\necho 'Stockfish 18 by the Stockfish developers'\n")
        os.chmod(self.target, 0o700)
        self.server.reply("GET", "/releases/latest", 503, {"message": "unavailable"})

        with patch("stockfish_updater.get_binary_name", return_value=self.BINARY), \
             patch("stockfish_updater.log_build_info"):
            path = stockfish_updater.ensure_stockfish_installed(auto_update=True)

        self.assertEqual(path, self.target)


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


class TestDeclineReasons(unittest.TestCase):
    """The reason handed to Lichess says what the challenger would have to change."""

    def reason(self, time_control=None, **fields):
        from bot import challenge_decline_reason
        challenge = {
            "id": "chal0001",
            "challenger": {"rating": fields.pop("rating", 1800)},
            "variant": {"key": fields.pop("variant", "standard")},
            "timeControl": time_control or {"type": "clock", "limit": 300, "increment": 0},
            **fields,
        }
        return challenge_decline_reason(challenge)

    def setUp(self):
        for target, value in {"bot.ACCEPT_CHALLENGES": True, "bot.MIN_RATING": 1320, "bot.MAX_RATING": 2800,
                              "bot.TIME_CONTROL": ["bullet", "blitz", "rapid", "classical"]}.items():
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_challenge_the_bot_plays_has_no_reason(self):
        self.assertIsNone(self.reason())
        self.assertIsNone(self.reason(rating=1320))
        self.assertIsNone(self.reason(rating=2800))

    def test_variants_are_declined_as_standard_only(self):
        for variant in ("chess960", "antichess", "atomic", "fromPosition"):
            self.assertEqual(self.reason(variant=variant), "standard", variant)

    def test_games_without_a_clock_are_declined_as_a_time_control(self):
        self.assertEqual(self.reason({"type": "correspondence", "daysPerTurn": 2}, speed="correspondence"), "timeControl")
        self.assertEqual(self.reason({"type": "unlimited"}), "timeControl")

    def test_a_rating_outside_the_range_has_only_the_general_reason(self):
        self.assertEqual(self.reason(rating=1319), "generic")
        self.assertEqual(self.reason(rating=2801), "generic")

    def test_a_speed_outside_the_played_ones_names_the_direction(self):
        with patch("bot.TIME_CONTROL", ["rapid"]):
            self.assertEqual(self.reason({"limit": 60, "increment": 0}), "tooFast")
            self.assertEqual(self.reason({"limit": 300, "increment": 0}), "tooFast")
            self.assertEqual(self.reason({"limit": 1800, "increment": 0}), "tooSlow")
            self.assertIsNone(self.reason({"limit": 600, "increment": 5}))

    def test_the_clock_is_judged_before_the_rating(self):
        """A bullet challenge to a bot that plays no bullet is too fast, whoever sends it."""
        with patch("bot.TIME_CONTROL", ["blitz", "rapid", "classical"]):
            self.assertEqual(self.reason({"limit": 60, "increment": 0}, rating=900), "tooFast")

    def test_accepting_nothing_declines_everything(self):
        with patch("bot.ACCEPT_CHALLENGES", False):
            self.assertEqual(self.reason(), "generic")

    def test_the_yes_or_no_answer_follows_the_reason(self):
        from bot import should_accept_challenge
        base = {"challenger": {"rating": 1800}, "variant": {"key": "standard"}, "timeControl": {"limit": 300, "increment": 0}}
        self.assertTrue(should_accept_challenge(base))
        self.assertFalse(should_accept_challenge({**base, "variant": {"key": "atomic"}}))


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


class QuietStream:
    """A game stream that delivers the given events and then says nothing until released."""

    def __init__(self, *events):
        self._events = list(events)
        self._release = threading.Event()
        self._later = []

    def then(self, *events):
        """Deliver these when ``release`` is called."""
        self._later = list(events)
        return self

    def release(self):
        self._release.set()

    def __iter__(self):
        yield from self._events
        self._release.wait(10)
        yield from self._later


class TestGameWatchdog(unittest.TestCase):
    """What the bot does while a game stream is quiet."""

    def setUp(self):
        self.client = Mock()
        self.checks = 0

    def lichess_says(self, *answers):
        """Answers to "how is the game?", in order; the last one repeats. An exception is raised."""
        answers = list(answers)

        def export(game_id):
            self.checks += 1
            answer = answers[0] if len(answers) == 1 else answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        self.client.games.export.side_effect = export

    def watch(self, stream, interval=0.02, abort_timeout=600):
        from bot import _stream_with_watchdog
        with patch("bot.GAME_WATCHDOG_ABORT_TIMEOUT", abort_timeout):
            yield from _stream_with_watchdog(stream, self.client, "game0001", interval)

    def test_events_pass_through_in_order_and_the_stream_end_ends_it(self):
        events = [{"type": "gameFull"}, {"type": "gameState", "moves": "e2e4"}]

        self.assertEqual(list(self.watch(iter(events))), events)
        self.client.games.export.assert_not_called()

    def test_an_error_on_the_stream_is_raised_to_the_game_thread(self):
        def broken():
            yield {"type": "gameFull"}
            raise ConnectionError("stream cut")

        watched = self.watch(broken())

        self.assertEqual(next(watched), {"type": "gameFull"})
        with self.assertRaises(ConnectionError):
            next(watched)

    def test_a_game_that_ended_without_the_stream_saying_so_is_closed(self):
        from bot import _GameStuck
        self.lichess_says({"status": "resign", "moves": "e4 e5 Nf3"})
        stream = QuietStream({"type": "gameFull"})
        self.addCleanup(stream.release)
        watched = self.watch(stream)
        next(watched)

        with self.assertRaises(_GameStuck):
            next(watched)

    def test_a_long_think_in_a_game_under_way_ends_nothing(self):
        """Status "started" covers a whole game in progress, not only one without moves."""
        self.lichess_says({"status": "started", "moves": "e4 e5 Nf3 Nc6"})
        stream = QuietStream({"type": "gameFull"}).then({"type": "gameState", "moves": "e2e4 e7e5 g1f3 b8c6 f1b5"})
        watched = self.watch(stream, abort_timeout=0.05)   # far shorter than the silence below
        next(watched)

        threading.Timer(0.5, stream.release).start()       # the opponent moves after a long silence
        event = next(watched)

        self.assertEqual(event["type"], "gameState")
        self.assertGreater(self.checks, 5)
        self.client.bots.abort_game.assert_not_called()
        self.client.bots.resign_game.assert_not_called()

    def test_a_game_nobody_moves_in_is_aborted_after_the_timeout(self):
        from bot import _GameStuck
        self.lichess_says({"status": "started", "moves": ""})
        stream = QuietStream({"type": "gameFull"})
        self.addCleanup(stream.release)
        watched = self.watch(stream, abort_timeout=0.1)
        next(watched)

        with self.assertRaises(_GameStuck):
            next(watched)

        self.client.bots.abort_game.assert_called_once_with("game0001")
        self.client.bots.resign_game.assert_not_called()

    def test_a_game_with_one_move_can_still_be_aborted(self):
        from bot import _GameStuck
        self.lichess_says({"status": "started", "moves": "e4"})
        stream = QuietStream({"type": "gameFull"})
        self.addCleanup(stream.release)
        watched = self.watch(stream, abort_timeout=0.1)
        next(watched)

        with self.assertRaises(_GameStuck):
            next(watched)

        self.client.bots.abort_game.assert_called_once_with("game0001")

    def test_no_abort_before_the_timeout(self):
        self.lichess_says({"status": "started", "moves": ""})
        stream = QuietStream({"type": "gameFull"}).then({"type": "gameState", "moves": "e2e4"})
        watched = self.watch(stream, abort_timeout=600)
        next(watched)

        threading.Timer(0.3, stream.release).start()
        event = next(watched)

        self.assertEqual(event["moves"], "e2e4")
        self.client.bots.abort_game.assert_not_called()

    def test_a_refused_abort_means_the_game_is_on_and_is_never_a_resignation(self):
        self.lichess_says({"status": "started", "moves": ""})
        self.client.bots.abort_game.side_effect = RuntimeError("Too late to abort")
        stream = QuietStream({"type": "gameFull"}).then({"type": "gameState", "moves": "e2e4 e7e5"})
        watched = self.watch(stream, abort_timeout=0.1)
        next(watched)

        threading.Timer(0.6, stream.release).start()
        event = next(watched)

        self.assertEqual(event["type"], "gameState")
        self.assertGreaterEqual(self.client.bots.abort_game.call_count, 1)
        self.client.bots.resign_game.assert_not_called()

    def test_a_move_restarts_the_wait_for_the_other_first_move(self):
        from bot import _GameStuck
        self.lichess_says({"status": "started", "moves": "e4"})

        import time

        def stream():
            yield {"type": "gameFull"}
            time.sleep(0.15)                      # most of the abort timeout...
            yield {"type": "gameState", "moves": "e2e4"}
            time.sleep(5)

        watched = self.watch(stream(), interval=0.02, abort_timeout=0.25)
        next(watched)
        self.assertEqual(next(watched)["type"], "gameState")
        self.client.bots.abort_game.assert_not_called()   # ...and then a move, so the wait starts over

        with self.assertRaises(_GameStuck):
            next(watched)
        self.client.bots.abort_game.assert_called_once()

    def test_failing_to_reach_lichess_ends_nothing(self):
        """However often the check fails, the game goes on when its stream does."""
        self.lichess_says(RuntimeError("HTTP 429"))
        stream = QuietStream({"type": "gameFull"}).then({"type": "gameState", "moves": "e2e4 e7e5"})
        watched = self.watch(stream, abort_timeout=0.05)
        next(watched)

        threading.Timer(0.5, stream.release).start()
        event = next(watched)

        self.assertEqual(event["type"], "gameState")
        self.assertGreater(self.checks, 10)
        self.client.bots.abort_game.assert_not_called()
        self.client.bots.resign_game.assert_not_called()

    def test_a_check_that_works_again_is_acted_on(self):
        from bot import _GameStuck
        self.lichess_says(RuntimeError("down"), RuntimeError("down"), {"status": "mate", "moves": "f3 e5 g4 Qh4#"})
        stream = QuietStream({"type": "gameFull"})
        self.addCleanup(stream.release)
        watched = self.watch(stream)
        next(watched)

        with self.assertRaises(_GameStuck):
            next(watched)

        self.assertEqual(self.checks, 3)


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
