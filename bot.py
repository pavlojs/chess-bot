"""
Axiom Chess Bot – stable BOT API architecture using Berserk and Stockfish
"""

import signal
import sys
import threading
import logging
import chess
import berserk
from berserk.exceptions import ResponseError, ApiError
import time
import random
from collections import deque
from datetime import datetime, timedelta

from stockfish import Stockfish, StockfishException
from typing import Dict, Any, List, Optional
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout, RequestException
from urllib3.exceptions import ProtocolError

from config import (
    TOKEN,
    STOCKFISH_PATH,
    STOCKFISH_TIME,
    UCI_OPTIONS,
    ACCEPT_CHALLENGES,
    MIN_RATING,
    MAX_RATING,
    TIME_CONTROL,
    DYNAMIC_STRENGTH,
    STRENGTH_ADVANTAGE,
    LIMIT_STRENGTH_THRESHOLD,
    FULL_STRENGTH_THRESHOLD,
    ENABLE_AUTO_CHALLENGE,
    MAX_CHALLENGES_PER_HOUR,
    CHALLENGE_MIN_RATING,
    CHALLENGE_MAX_RATING,
    CHALLENGE_TIME_CONTROLS,
    CHALLENGE_CHECK_INTERVAL,
    ENABLE_MOVE_PREDICTION,
    PREDICTION_DEPTH,
)

from logging_config import setup_logger

logger = setup_logger(__name__)
shutdown_requested = False


# ─────────────────────────────────────────────
# CHALLENGE TRACKER
# ─────────────────────────────────────────────

class ChallengeTracker:
    """Track challenges sent to enforce rate limits."""
    
    def __init__(self, max_per_hour: int = MAX_CHALLENGES_PER_HOUR):
        self.max_per_hour = max_per_hour
        self.challenge_times: deque = deque()
        self.lock = threading.Lock()
    
    def can_challenge(self) -> bool:
        """Check if we can send another challenge within the hourly limit."""
        with self.lock:
            now = datetime.now()
            # Remove challenges older than 1 hour
            while self.challenge_times and self.challenge_times[0] < now - timedelta(hours=1):
                self.challenge_times.popleft()
            
            return len(self.challenge_times) < self.max_per_hour
    
    def record_challenge(self):
        """Record a new challenge."""
        with self.lock:
            self.challenge_times.append(datetime.now())
    
    def get_remaining_challenges(self) -> int:
        """Get number of challenges remaining in current hour."""
        with self.lock:
            now = datetime.now()
            # Remove old challenges
            while self.challenge_times and self.challenge_times[0] < now - timedelta(hours=1):
                self.challenge_times.popleft()
            
            return max(0, self.max_per_hour - len(self.challenge_times))


# ─────────────────────────────────────────────
# SIGNAL HANDLING
# ─────────────────────────────────────────────

def handle_shutdown(signum, frame):
    global shutdown_requested
    if shutdown_requested:
        # Second signal - force exit immediately
        logger.warning("Force shutdown!")
        sys.exit(1)
    
    shutdown_requested = True
    logger.warning("Shutdown signal received, waiting for cleanup (press Ctrl+C again to force)")
    
    # Give threads a moment to finish, then exit
    def delayed_exit():
        time.sleep(2)
        if shutdown_requested:
            logger.info("Forcing shutdown after timeout")
            sys.exit(0)
    
    threading.Thread(target=delayed_exit, daemon=True).start()


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


# ─────────────────────────────────────────────
# TIME PARSING UTILITIES
# ─────────────────────────────────────────────

def parse_time_to_milliseconds(time_value: Any) -> Optional[int]:
    """Parse time value from various formats to milliseconds.
    
    Handles multiple input formats from Lichess API:
    - Integers: Already in milliseconds
    - Floats: Milliseconds as float
    - String integers: "120000" -> 120000
    - Timedelta strings: "0:08:44.640000" -> 524640 (8m 44.64s in ms)
    - Timedelta objects: Direct conversion
    
    Args:
        time_value: Time value in various formats
    
    Returns:
        Time in milliseconds as integer, or None if parsing fails
    """
    if time_value is None:
        return None
    
    # Already an integer (milliseconds)
    if isinstance(time_value, int):
        return time_value
    
    # Float (milliseconds)
    if isinstance(time_value, float):
        return int(time_value)
    
    # Timedelta object
    if isinstance(time_value, timedelta):
        return int(time_value.total_seconds() * 1000)
    
    # String - try multiple parsing strategies
    if isinstance(time_value, str):
        # Try direct integer conversion
        try:
            return int(time_value)
        except ValueError:
            pass
        
        # Try parsing as timedelta string format "H:MM:SS.ffffff"
        try:
            # Remove any whitespace
            time_str = time_value.strip()
            
            # Parse format like "0:08:44.640000" or "0:08:44"
            parts = time_str.split(':')
            if len(parts) >= 2:
                hours = int(parts[0])
                minutes = int(parts[1])
                
                # Handle seconds (may have microseconds)
                if len(parts) >= 3:
                    seconds_part = parts[2]
                    if '.' in seconds_part:
                        sec, microsec = seconds_part.split('.')
                        seconds = int(sec)
                        # Pad microseconds to 6 digits if needed
                        microsec = microsec.ljust(6, '0')[:6]
                        microseconds = int(microsec)
                    else:
                        seconds = int(seconds_part)
                        microseconds = 0
                else:
                    seconds = 0
                    microseconds = 0
                
                # Convert to milliseconds
                total_ms = (
                    hours * 3600 * 1000 +
                    minutes * 60 * 1000 +
                    seconds * 1000 +
                    microseconds // 1000
                )
                return total_ms
        except (ValueError, IndexError, AttributeError):
            pass
    
    # If all parsing attempts fail, return None
    return None


# ─────────────────────────────────────────────
# RETRY LOGIC
# ─────────────────────────────────────────────

def retry_with_backoff(func, max_retries=5, base_delay=1, max_delay=60, description="Operation"):
    """Execute a function with exponential backoff retry logic.
    
    Args:
        func: Function to execute
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        description: Description of the operation for logging
    
    Returns:
        Result of the function call
    
    Raises:
        Last exception if all retries fail
    """
    for attempt in range(max_retries):
        if shutdown_requested:
            raise KeyboardInterrupt("Shutdown requested")
        
        try:
            return func()
        except (ChunkedEncodingError, ProtocolError, ConnectionError, Timeout) as e:
            if attempt == max_retries - 1:
                logger.error(f"{description} failed after {max_retries} attempts: {e}")
                raise
            
            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(f"{description} failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
            time.sleep(delay)
        except berserk.exceptions.ResponseError as e:
            # Handle 502, 503, 504 errors with retry
            if hasattr(e, 'response') and e.response and e.response.status_code in [502, 503, 504]:
                if attempt == max_retries - 1:
                    logger.error(f"{description} failed after {max_retries} attempts: {e}")
                    raise
                
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.warning(f"{description} failed with {e.response.status_code} (attempt {attempt + 1}/{max_retries}). Retrying in {delay}s...")
                time.sleep(delay)
            else:
                # For other errors, don't retry
                raise
        except Exception as e:
            logger.error(f"{description} failed with unexpected error: {e}")
            raise


# ─────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────

def determine_time_category(limit: int, increment: int) -> str | None:
    # Reject unlimited time games (limit = 0 and increment = 0)
    if limit == 0 and increment == 0:
        return None
    
    # Reject correspondence games (days per move > 0)
    # In Lichess API, correspondence games have very large limits
    # or are marked differently in variant/speed fields
    if limit >= 259200:  # 3+ days in seconds = correspondence
        return None
    
    total = limit + increment * 40
    if total < 180:
        return "bullet"
    elif total < 480:
        return "blitz"
    elif total < 1500:
        return "rapid"
    return "classical"


def should_accept_challenge(challenge: Dict[str, Any]) -> bool:
    if not ACCEPT_CHALLENGES:
        return False

    challenger = challenge.get("challenger", {})
    rating = challenger.get("rating", 1500)
    
    # Check if challenge has speed field (more reliable than calculating)
    speed = challenge.get("speed")
    if speed:
        # Reject correspondence and unlimited time games
        if speed in ["correspondence", "unlimited"]:
            logger.info(f"Rejecting {speed} challenge")
            return False

    clock = challenge.get("timeControl", {})
    limit = clock.get("limit", 0)
    increment = clock.get("increment", 0)

    category = determine_time_category(limit, increment)
    
    # Reject if category is None (unlimited or correspondence)
    if category is None:
        logger.info(f"Rejecting challenge with no valid time category")
        return False

    if not (MIN_RATING <= rating <= MAX_RATING):
        return False

    if category not in TIME_CONTROL:
        return False

    logger.info(f"Accepting challenge from {rating} ({category})")
    return True


def get_game_end_reason(board: chess.Board) -> str:
    """Get detailed reason for game ending.
    
    Args:
        board: Chess board in final position
        
    Returns:
        Human-readable description of game ending reason
    """
    if board.is_checkmate():
        winner = "White" if board.turn == chess.BLACK else "Black"
        return f"checkmate - {winner} wins"
    
    if board.is_stalemate():
        return "draw by stalemate"
    
    if board.is_insufficient_material():
        return "draw by insufficient material"
    
    # Check for threefold repetition
    if board.can_claim_threefold_repetition():
        return "draw by threefold repetition"
    
    # Check for fivefold repetition (automatic draw)
    if board.is_fivefold_repetition():
        return "draw by fivefold repetition"
    
    # Check for fifty-move rule
    if board.can_claim_fifty_moves():
        return "draw by fifty-move rule"
    
    # Check for seventy-five move rule (automatic draw)
    if board.is_seventyfive_moves():
        return "draw by seventy-five-move rule"
    
    # Shouldn't reach here if board.is_game_over() was True
    return "game ended (unknown reason)"


def init_stockfish(opponent_rating: int | None = None) -> Stockfish:
    """Initialize Stockfish engine with hybrid strength system.
    
    Hybrid approach:
    - Weak opponents (< 1800): UCI_LimitStrength for fair games
    - Intermediate (1800-2199): Full strength, reduced time
    - Strong (2200+): FULL POWER
    """
    sf = Stockfish(
        path=STOCKFISH_PATH,
        parameters=UCI_OPTIONS.copy(),
    )
    
    if DYNAMIC_STRENGTH and opponent_rating:
        # For weak opponents: Use UCI_LimitStrength for fair, balanced games
        if opponent_rating < LIMIT_STRENGTH_THRESHOLD:
            target_elo = min(max(opponent_rating + STRENGTH_ADVANTAGE, 1320), 2850)
            sf.update_engine_parameters({
                "UCI_LimitStrength": True,
                "UCI_Elo": target_elo,
            })
            logger.info(f"Opponent {opponent_rating} ELO: Using UCI_LimitStrength = {target_elo} (fair play mode)")
        else:
            # For intermediate/strong opponents: Full engine strength, time-controlled
            logger.info(f"Opponent {opponent_rating} ELO: Using full strength engine (time-controlled)")
    
    return sf


def get_move_prediction(stockfish: Stockfish, game_id: str, prediction_depth: int = PREDICTION_DEPTH) -> Optional[str]:
    """Get Stockfish's predicted line of best moves (Principal Variation).
    
    Args:
        stockfish: Initialized Stockfish instance
        game_id: Game ID for logging
        prediction_depth: Number of moves to predict (half-moves/plies)
    
    Returns:
        String with predicted move sequence, or None if unavailable
    """
    try:
        # Get top move with full analysis including PV (Principal Variation)
        top_moves = stockfish.get_top_moves(num_top_moves=1, verbose=True)
        
        if not top_moves:
            return None
        
        best_move_info = top_moves[0]
        pv_moves = best_move_info.get('PVMoves', [])
        
        if not pv_moves:
            return None
        
        # Limit to requested depth
        pv_moves = pv_moves[:prediction_depth]
        
        # Get evaluation for context
        eval_info = best_move_info.get('Centipawn')
        mate_info = best_move_info.get('Mate')
        
        eval_str = ""
        if mate_info is not None:
            eval_str = f" (Mate in {mate_info})"
        elif eval_info is not None:
            eval_str = f" ({eval_info:+d} cp)"
        
        # Format the predicted line
        prediction = " ".join(pv_moves)
        logger.info(f"[{game_id}] 🔮 Predicted line{eval_str}: {prediction}")
        
        return prediction
        
    except Exception as e:
        logger.debug(f"[{game_id}] Could not get move prediction: {e}")
        return None


def calculate_move_time(opponent_rating: int | None, base_time: int = STOCKFISH_TIME, 
                       bot_time_remaining: int | None = None, increment: int = 0) -> int:
    """Calculate thinking time based on opponent strength and remaining time.
    
    Strategy:
    - Weak opponents (< 1800): Reduced time (40% min) + UCI_LimitStrength handles fairness
    - Intermediate (1800-2799): Scaled time (40-95%) with full strength engine
    - Strong opponents (2800+): Full time (100%) with full strength engine
    - Critical time (<= 20s): Fast moves to avoid time loss while maintaining strength
    
    Args:
        opponent_rating: Opponent's rating for strength adjustment
        base_time: Base thinking time in milliseconds
        bot_time_remaining: Bot's remaining time in milliseconds
        increment: Increment per move in milliseconds
    
    Returns:
        Thinking time in milliseconds
    """
    # Start with opponent-based time calculation
    if not DYNAMIC_STRENGTH or not opponent_rating:
        adjusted_time = base_time
    elif opponent_rating >= FULL_STRENGTH_THRESHOLD:
        # FULL POWER for strong opponents (2800+)
        adjusted_time = base_time
        logger.debug(f"Strong opponent ({opponent_rating}): FULL POWER - {base_time}ms (100%)")
    elif opponent_rating < LIMIT_STRENGTH_THRESHOLD:
        # For weak opponents (< 1800): Use minimal time since UCI_LimitStrength handles fairness
        adjusted_time = int(base_time * 0.4)  # 40% = 1200ms (reasonable minimum)
        logger.debug(f"Weak opponent ({opponent_rating}): {adjusted_time}ms (40%, UCI_LimitStrength active)")
    else:
        # For intermediate opponents (1800-2799): Time-based scaling with full strength
        # Linear scaling: 1800 → 40%, 2799 → 95%
        rating_range = FULL_STRENGTH_THRESHOLD - LIMIT_STRENGTH_THRESHOLD  # 1000
        rating_offset = opponent_rating - LIMIT_STRENGTH_THRESHOLD
        time_percentage = 0.4 + (rating_offset / rating_range) * 0.55  # 40% to 95%
        
        adjusted_time = int(base_time * time_percentage)
        logger.debug(f"Intermediate opponent ({opponent_rating}): {adjusted_time}ms ({time_percentage*100:.0f}%)")
    
    # Apply time pressure adjustment if we're running low on time
    if bot_time_remaining is not None:
        # Parse time value (handles multiple formats including timedelta strings)
        bot_time_remaining = parse_time_to_milliseconds(bot_time_remaining)
        if bot_time_remaining is None:
            logger.debug(f"Could not parse bot_time_remaining, using default time")
            return adjusted_time
        
        # Parse increment value as well
        increment = parse_time_to_milliseconds(increment)
        if increment is None:
            increment = 0
        
        time_remaining_seconds = bot_time_remaining / 1000.0
        
        # Critical time threshold: 20 seconds or less
        if time_remaining_seconds <= 20:
            # In critical time, use very fast moves to avoid timeout
            # But ensure we maintain reasonable quality by not going below 300ms
            # Calculate based on remaining moves (estimate ~20 moves to go)
            estimated_moves_remaining = 20
            time_per_move = max(300, (bot_time_remaining + increment * estimated_moves_remaining) / estimated_moves_remaining)
            
            # Take the minimum of adjusted_time and emergency time
            move_time = min(adjusted_time, int(time_per_move * 0.6))  # Use 60% of available time
            logger.info(f"TIME PRESSURE! Remaining: {time_remaining_seconds:.1f}s, using {move_time}ms (emergency mode)")
            return max(300, move_time)  # Never go below 300ms for move quality
        
        # Moderate time pressure: 20-60 seconds
        elif time_remaining_seconds <= 60:
            # Start being more conservative with time
            time_factor = time_remaining_seconds / 60.0  # 33%-100% scaling
            move_time = int(adjusted_time * time_factor)
            logger.debug(f"Moderate time pressure: {time_remaining_seconds:.1f}s, adjusted to {move_time}ms")
            return max(500, move_time)  # Minimum 500ms in moderate pressure
    
    return adjusted_time


# ─────────────────────────────────────────────
# CHALLENGE FUNCTIONS
# ─────────────────────────────────────────────

def get_online_bots(client: berserk.Client, limit: int = 100) -> List[Dict[str, Any]]:
    """Get list of online bots from Lichess.
    
    Args:
        client: Berserk client instance
        limit: Maximum number of bots to retrieve
    
    Returns:
        List of bot dictionaries with user information
    """
    try:
        # Use berserk's built-in method to get online bots
        online_bots = []
        
        try:
            # client.bots.get_online_bots returns an iterator
            for bot_data in client.bots.get_online_bots(limit=limit):
                online_bots.append(bot_data)
                
                if len(online_bots) >= limit:
                    break
                    
        except Exception as e:
            logger.warning(f"Failed to fetch online bots: {e}")
            return []
        
        logger.debug(f"Retrieved {len(online_bots)} online bots")
        return online_bots
        
    except Exception as e:
        logger.error(f"Error getting online bots: {e}")
        return []


def filter_suitable_bots(bots: List[Dict[str, Any]], min_rating: int, max_rating: int, 
                         bot_username: str) -> List[Dict[str, Any]]:
    """Filter bots by rating criteria.
    
    Args:
        bots: List of bot dictionaries
        min_rating: Minimum rating threshold
        max_rating: Maximum rating threshold
        bot_username: Our bot's username (to exclude self)
    
    Returns:
        Filtered list of suitable bots
    """
    suitable = []
    
    for bot in bots:
        username = bot.get("username", "").lower()
        
        # Skip self
        if username == bot_username.lower():
            continue
        
        # Get perfs (performance ratings)
        perfs = bot.get("perfs", {})
        
        # Check if bot has any rating in acceptable range
        has_suitable_rating = False
        for time_control in ["blitz", "rapid", "bullet", "classical"]:
            if time_control in perfs:
                rating = perfs[time_control].get("rating", 0)
                if min_rating <= rating <= max_rating:
                    has_suitable_rating = True
                    break
        
        if has_suitable_rating:
            suitable.append(bot)
    
    return suitable


def challenge_bot(client: berserk.Client, opponent_username: str, 
                  time_control: Dict[str, int], color: str = "random") -> bool:
    """Challenge a bot to a game.
    
    Args:
        client: Berserk client instance
        opponent_username: Username of the bot to challenge
        time_control: Dictionary with 'limit' and 'increment' keys (in seconds)
        color: Color preference ("white", "black", or "random")
    
    Returns:
        True if challenge was sent successfully, False otherwise
    """
    try:
        # Use berserk to create a challenge
        challenge = client.challenges.create(
            opponent_username,
            rated=True,
            clock_limit=time_control["limit"],
            clock_increment=time_control["increment"],
            color=color,
            variant="standard",
        )
        
        logger.info(
            f"Challenged {opponent_username} to {time_control['limit']}+{time_control['increment']} game"
        )
        return True
    except berserk.exceptions.ResponseError as e:
        logger.warning(f"Failed to challenge {opponent_username}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error challenging {opponent_username}: {e}")
        return False


def try_challenge_random_bot(client: berserk.Client, bot_username: str, 
                             tracker: ChallengeTracker) -> bool:
    """Attempt to challenge a random suitable bot.
    
    Args:
        client: Berserk client instance
        bot_username: Our bot's username
        tracker: Challenge tracker to enforce rate limits
    
    Returns:
        True if challenge was sent, False otherwise
    """
    if not ENABLE_AUTO_CHALLENGE:
        return False
    
    if not tracker.can_challenge():
        remaining = tracker.get_remaining_challenges()
        logger.debug(f"Challenge limit reached. Remaining this hour: {remaining}")
        return False
    
    # Get online bots
    logger.debug("Fetching online bots...")
    online_bots = get_online_bots(client, limit=100)
    
    if not online_bots:
        logger.debug("No online bots found")
        return False
    
    # Filter by rating
    suitable_bots = filter_suitable_bots(
        online_bots, 
        CHALLENGE_MIN_RATING, 
        CHALLENGE_MAX_RATING, 
        bot_username
    )
    
    if not suitable_bots:
        logger.debug(
            f"No suitable bots found (rating range: {CHALLENGE_MIN_RATING}-{CHALLENGE_MAX_RATING})"
        )
        return False
    
    # Select random bot and time control
    target_bot = random.choice(suitable_bots)
    time_control = random.choice(CHALLENGE_TIME_CONTROLS)
    
    # Send challenge
    success = challenge_bot(
        client, 
        target_bot["username"], 
        time_control,
        color="random"
    )
    
    if success:
        tracker.record_challenge()
    
    return success


# ─────────────────────────────────────────────
# GAME THREAD
# ─────────────────────────────────────────────

def play_game(client: berserk.Client, game_id: str, bot_username: str):
    logger.info(f"Starting game thread {game_id}")

    board = chess.Board()
    stockfish: Stockfish | None = None
    bot_is_white: bool | None = None
    opponent_rating: int | None = None  # Track opponent rating for move time calculation
    last_move_count = 0  # Track number of moves processed
    bot_time_remaining: int | None = None  # Track bot's remaining time in milliseconds
    increment: int = 0  # Time increment per move in milliseconds

    try:
        # Retry stream connection with backoff
        while not shutdown_requested:
            try:
                stream = client.bots.stream_game_state(game_id)
                
                for event in stream:
                    if shutdown_requested:
                        break

                    if event["type"] == "gameFull":
                        board.reset()

                        moves = event["state"]["moves"].split() if event["state"]["moves"] else []
                        for move in moves:
                            board.push_uci(move)
                        
                        last_move_count = len(moves)

                        white_username = event["white"].get("name", event["white"].get("id", "")).lower()
                        black_username = event["black"].get("name", event["black"].get("id", "")).lower()
                        bot_is_white = (white_username == bot_username.lower())

                        logger.debug(
                            f"[{game_id}] White: {white_username}, Black: {black_username}, "
                            f"Bot: {bot_username.lower()}, Bot is white: {bot_is_white}"
                        )

                        opponent = event["black"] if bot_is_white else event["white"]
                        opponent_rating = opponent.get("rating")  # Store in outer scope
                        
                        # Extract time information from game state
                        state = event.get("state", {})
                        raw_time = state.get("wtime" if bot_is_white else "btime")
                        raw_inc = state.get("winc" if bot_is_white else "binc", 0)
                        
                        # Parse time values (handles multiple formats)
                        bot_time_remaining = parse_time_to_milliseconds(raw_time)
                        if bot_time_remaining is None and raw_time is not None:
                            logger.warning(f"[{game_id}] Could not parse bot_time_remaining: {raw_time}")
                        
                        increment = parse_time_to_milliseconds(raw_inc)
                        if increment is None:
                            increment = 0
                            if raw_inc not in (0, None, ""):
                                logger.warning(f"[{game_id}] Could not parse increment: {raw_inc}")

                        stockfish = init_stockfish(opponent_rating)

                        logger.info(
                            f"Game {game_id}: playing as "
                            f"{'white' if bot_is_white else 'black'} "
                            f"vs {opponent_rating}"
                        )
                        # Don't continue here - we need to check if it's our turn

                    if event["type"] == "gameState":
                        moves = event["moves"].split() if event.get("moves") else []
                        current_move_count = len(moves)
                        
                        # Update bot's remaining time
                        if bot_is_white is not None:
                            raw_time = event.get("wtime" if bot_is_white else "btime")
                            bot_time_remaining = parse_time_to_milliseconds(raw_time)
                            if bot_time_remaining is None and raw_time is not None:
                                logger.debug(f"[{game_id}] Could not parse time update: {raw_time}")
                            
                            if increment == 0:  # Only update increment if not set
                                raw_inc = event.get("winc" if bot_is_white else "binc", 0)
                                new_increment = parse_time_to_milliseconds(raw_inc)
                                if new_increment is not None:
                                    increment = new_increment
                                elif raw_inc not in (0, None, ""):
                                    logger.debug(f"[{game_id}] Could not parse increment update: {raw_inc}")
                        
                        # Check if game ended (resignation, timeout, etc.)
                        status = event.get("status")
                        if status in ["mate", "resign", "stalemate", "timeout", "draw", "outoftime", "cheat", "noStart", "unknownFinish", "variantEnd"]:
                            logger.info(f"[{game_id}] Game ended: {status}")
                            break
                        
                        # Only process new moves
                        if current_move_count > last_move_count:
                            new_moves = moves[last_move_count:]
                            for move in new_moves:
                                board.push_uci(move)
                                logger.debug(f"[{game_id}] Applied move {move}, board turn: {board.turn}")
                            last_move_count = current_move_count

                        # Handle draw offers
                        if event.get("wdraw") or event.get("bdraw"):
                            logger.info(f"[{game_id}] Draw offer received")
                            
                            if stockfish:
                                try:
                                    # Evaluate position to decide
                                    stockfish.set_fen_position(board.fen())
                                    eval_info = stockfish.get_evaluation()
                                    
                                    # Get centipawn evaluation (positive = bot winning, negative = bot losing)
                                    accept_draw = False
                                    
                                    if eval_info["type"] == "cp":
                                        evaluation = eval_info["value"]
                                        # Adjust for color (Stockfish always evaluates from white's perspective)
                                        if not bot_is_white:
                                            evaluation = -evaluation
                                        
                                        logger.info(f"[{game_id}] Position evaluation: {evaluation} centipawns")
                                        
                                        # Accept draw only if position is close to equal (±200 centipawns)
                                        # Decline if we have advantage OR disadvantage - let the engine play it out
                                        if -200 <= evaluation <= 200:
                                            accept_draw = True
                                            logger.info(f"[{game_id}] Accepting draw offer (balanced position: {evaluation}cp)")
                                        elif evaluation > 200:
                                            logger.info(f"[{game_id}] Declining draw offer (we're winning: {evaluation}cp)")
                                        else:
                                            logger.info(f"[{game_id}] Declining draw offer (we're losing but engine can play: {evaluation}cp)")
                                    else:
                                        # If mate evaluation, always decline - let the engine play
                                        mate_value = eval_info["value"]
                                        if mate_value < 0:
                                            logger.info(f"[{game_id}] Declining draw offer (getting mated in {abs(mate_value)}, but will fight)")
                                        else:
                                            logger.info(f"[{game_id}] Declining draw offer (we have mate in {mate_value})")
                                    
                                    # Send decision via API
                                    try:
                                        client.board.handle_draw_offer(game_id, accept=accept_draw)
                                    except Exception as api_error:
                                        logger.error(f"[{game_id}] Failed to respond to draw offer: {api_error}")
                                        
                                except Exception as e:
                                    logger.error(f"[{game_id}] Error evaluating draw offer: {e}")
                                    # On error, decline draw and continue playing
                                    try:
                                        client.board.handle_draw_offer(game_id, accept=False)
                                    except:
                                        pass

                    # After processing event, check if game is over
                    if board.is_game_over():
                        reason = get_game_end_reason(board)
                        logger.info(f"Game {game_id} finished: {reason}")
                        break

                    # Skip if game not initialized yet
                    if bot_is_white is None or stockfish is None:
                        logger.debug(f"[{game_id}] Waiting for game initialization...")
                        continue

                    is_my_turn = (
                        (board.turn == chess.WHITE and bot_is_white) or
                        (board.turn == chess.BLACK and not bot_is_white)
                    )

                    if not is_my_turn:
                        logger.debug(
                            f"[{game_id}] Not my turn (board.turn={board.turn}, "
                            f"bot_is_white={bot_is_white})"
                        )
                        continue

                    try:
                        logger.debug(f"[{game_id}] Calculating move for position: {board.fen()}")
                        stockfish.set_fen_position(board.fen())
                        
                        # Get move prediction (principal variation) if enabled
                        if ENABLE_MOVE_PREDICTION:
                            get_move_prediction(stockfish, game_id, PREDICTION_DEPTH)
                        
                        # Calculate appropriate thinking time based on opponent strength and remaining time
                        move_time = calculate_move_time(opponent_rating, STOCKFISH_TIME, 
                                                       bot_time_remaining, increment)
                        move = stockfish.get_best_move_time(move_time)

                        if move:
                            # Double-check game isn't over before making move
                            if board.is_game_over():
                                reason = get_game_end_reason(board)
                                logger.info(f"[{game_id}] Game ended while calculating move: {reason}")
                                break
                            
                            # Retry mechanism for network errors during move submission
                            max_retries = 3
                            retry_delay = 2
                            
                            for attempt in range(max_retries):
                                try:
                                    client.bots.make_move(game_id, move)
                                    board.push_uci(move)
                                    last_move_count += 1  # Increment move count after our move
                                    logger.info(f"[{game_id}] Played {move}")
                                    break  # Success - exit retry loop
                                except (ConnectionError, Timeout, ChunkedEncodingError, ProtocolError, RequestException) as net_err:
                                    if attempt < max_retries - 1:
                                        logger.warning(f"[{game_id}] Network error while making move (attempt {attempt + 1}/{max_retries}): {net_err}")
                                        time.sleep(retry_delay)
                                        retry_delay *= 2  # Exponential backoff
                                    else:
                                        logger.error(f"[{game_id}] Failed to make move after {max_retries} attempts: {net_err}")
                                        logger.info(f"[{game_id}] Game interrupted due to persistent connection issues")
                                        raise  # Re-raise to trigger outer exception handler
                        else:
                            logger.warning(f"[{game_id}] Stockfish returned no move")

                    except (ConnectionError, Timeout, ChunkedEncodingError, ProtocolError, RequestException) as e:
                        # Network errors that couldn't be resolved after retries
                        logger.warning(f"[{game_id}] Network error while making move: {e}")
                        logger.info(f"[{game_id}] Game interrupted due to connection issues")
                        break
                    except ApiError as e:
                        # Handle API-specific errors
                        error_str = str(e).lower()
                        if "connection" in error_str or "remote" in error_str:
                            logger.warning(f"[{game_id}] Network error while making move: {e}")
                            logger.info(f"[{game_id}] Game interrupted due to connection issues")
                        else:
                            logger.error(f"[{game_id}] API error while making move: {e}")
                        break
                    except ResponseError as e:
                        # Handle "game already over" errors gracefully (race condition)
                        error_msg = str(e).lower()
                        if "not your turn" in error_msg or "game already over" in error_msg:
                            logger.info(f"[{game_id}] Game ended while making move (race condition)")
                            break
                        else:
                            logger.error(f"[{game_id}] API error: {e}")
                            break
                    except StockfishException as e:
                        logger.error(f"Stockfish error in game {game_id}: {e}")
                        break
                
                # If stream ends normally, exit
                break
                
            except (ChunkedEncodingError, ProtocolError, ConnectionError, Timeout) as e:
                logger.warning(f"[{game_id}] Stream connection lost: {e}. Reconnecting in 5s...")
                time.sleep(5)
                continue
            except Exception as e:
                logger.error(f"[{game_id}] Unexpected stream error: {e}", exc_info=True)
                break

    except Exception as e:
        logger.error(f"Game {game_id} crashed: {e}", exc_info=True)

    finally:
        if stockfish:
            try:
                if hasattr(stockfish, "_stockfish") and stockfish._stockfish:
                    stockfish._stockfish.kill()
                    stockfish._stockfish.wait()
            except Exception as e:
                logger.debug(f"[{game_id}] Error during Stockfish cleanup: {e}")
        logger.info(f"Game thread {game_id} exited")


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────

def challenge_loop(client: berserk.Client, bot_username: str, 
                  active_games: Dict[str, threading.Thread],
                  challenge_tracker: ChallengeTracker):
    """Background thread that periodically challenges other bots."""
    logger.info("Challenge loop started")
    
    while not shutdown_requested:
        try:
            time.sleep(CHALLENGE_CHECK_INTERVAL)
            
            if shutdown_requested:
                break
            
            if not ENABLE_AUTO_CHALLENGE:
                continue
            
            # Count active games (threads that are still alive)
            active_count = sum(1 for t in active_games.values() if t.is_alive())
            
            if active_count == 0:
                logger.info("No active games, attempting to challenge a bot...")
                try_challenge_random_bot(client, bot_username, challenge_tracker)
            else:
                logger.debug(f"Skipping challenge check: {active_count} active game(s)")
                
        except Exception as e:
            logger.error(f"Challenge loop error: {e}", exc_info=True)
            time.sleep(10)
    
    logger.info("Challenge loop stopped")


def main():
    session = berserk.TokenSession(TOKEN)
    client = berserk.Client(session)

    # Get account with retry logic
    account = retry_with_backoff(
        lambda: client.account.get(),
        max_retries=10,
        base_delay=2,
        description="Get account info"
    )
    
    is_bot = account.get("title") == "BOT"
    if not is_bot:
        raise RuntimeError("This account is NOT a BOT account")

    bot_username = account.get("username")
    logger.info("Bot account verified: %s", bot_username)

    active_games: Dict[str, threading.Thread] = {}
    challenge_tracker = ChallengeTracker(MAX_CHALLENGES_PER_HOUR)
    
    # Start challenge loop in background thread
    challenge_thread = threading.Thread(
        target=challenge_loop,
        args=(client, bot_username, active_games, challenge_tracker),
        daemon=True
    )
    challenge_thread.start()
    logger.info("Background challenge thread started")

    # Main event loop with automatic reconnection
    while not shutdown_requested:
        try:
            logger.info("Connecting to event stream...")
            for event in client.bots.stream_incoming_events():
                if shutdown_requested:
                    break

                try:
                    if event["type"] == "challenge":
                        challenge = event["challenge"]
                        cid = challenge["id"]
                        
                        # Check if this is an incoming challenge (destUser is us)
                        dest_user = challenge.get("destUser", {})
                        challenger = challenge.get("challenger", {})
                        
                        dest_username = dest_user.get("name", dest_user.get("id", "")).lower()
                        challenger_username = challenger.get("name", challenger.get("id", "")).lower()
                        
                        # Only process incoming challenges (where we are the destination)
                        if dest_username == bot_username.lower():
                            if should_accept_challenge(challenge):
                                try:
                                    client.bots.accept_challenge(cid)
                                except berserk.exceptions.ResponseError as e:
                                    if "404" in str(e):
                                        logger.debug(f"Challenge {cid} no longer exists")
                                    else:
                                        logger.warning(f"Failed to accept challenge: {e}")
                            else:
                                try:
                                    client.bots.decline_challenge(cid)
                                except berserk.exceptions.ResponseError as e:
                                    if "404" in str(e):
                                        logger.debug(f"Challenge {cid} no longer exists")
                                    else:
                                        logger.warning(f"Failed to decline challenge: {e}")
                        else:
                            # Outgoing challenge - just log it
                            logger.debug(f"Outgoing challenge to {dest_username}: {cid}")
                    
                    elif event["type"] == "challengeDeclined":
                        challenge = event.get("challenge", {})
                        decliner = challenge.get("destUser", {}).get("name", "Unknown")
                        logger.info(f"Challenge declined by {decliner}")
                    
                    elif event["type"] == "challengeCanceled":
                        challenge = event.get("challenge", {})
                        challenger = challenge.get("challenger", {}).get("name", "Unknown")
                        logger.info(f"Challenge canceled by {challenger}")

                    elif event["type"] == "gameStart":
                        game_id = event["game"]["id"]

                        thread = threading.Thread(
                            target=play_game,
                            args=(client, game_id, bot_username),
                            daemon=True,
                        )
                        active_games[game_id] = thread
                        thread.start()

                        logger.info(f"Game {game_id} started")
                    
                    elif event["type"] == "gameFinish":
                        game_id = event["game"]["id"]
                        if game_id in active_games:
                            # Clean up finished game thread
                            active_games[game_id].join(timeout=1)
                            del active_games[game_id]
                            logger.info(f"Game {game_id} finished and cleaned up")

                except Exception as e:
                    logger.error(f"Event processing error: {e}", exc_info=True)
            
            # Stream ended normally
            logger.info("Event stream ended")
            break
            
        except (ChunkedEncodingError, ProtocolError, ConnectionError, Timeout) as e:
            logger.warning(f"Event stream connection lost: {e}. Reconnecting in 10s...")
            time.sleep(10)
            continue
        except berserk.exceptions.ResponseError as e:
            if hasattr(e, 'response') and e.response and e.response.status_code in [502, 503, 504]:
                logger.warning(f"Lichess API error {e.response.status_code}. Reconnecting in 15s...")
                time.sleep(15)
                continue
            else:
                logger.error(f"Unrecoverable API error: {e}", exc_info=True)
                break
        except Exception as e:
            logger.error(f"Main loop error: {e}", exc_info=True)
            time.sleep(10)
            continue

    logger.info("Shutting down bot")


if __name__ == "__main__":
    main()
