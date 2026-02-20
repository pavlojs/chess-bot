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
import requests
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
    
    Three-tier hybrid approach:
    - Beginners/Intermediates (< LIMIT_STRENGTH_THRESHOLD=1800):
        UCI_LimitStrength at opponent+100 + go movetime (fair, winnable games)
    - Advanced (LIMIT_STRENGTH_THRESHOLD–FULL_STRENGTH_THRESHOLD = 1800–2799):
        UCI_LimitStrength at opponent+100 + go movetime (scaled time).
        NO native clocks — UCI_LimitStrength + go wtime causes Stockfish to
        time-manage as a limited player, potentially hanging 30+ seconds.
    - Elite (>= FULL_STRENGTH_THRESHOLD=2800): Full power + native clocks
    """
    sf = Stockfish(
        path=STOCKFISH_PATH,
        parameters=UCI_OPTIONS.copy(),
    )
    
    if DYNAMIC_STRENGTH and opponent_rating:
        if opponent_rating < FULL_STRENGTH_THRESHOLD:
            # Apply UCI_LimitStrength for ALL opponents below the full-power threshold.
            # < 1800: movetime mode (extra cap, see play_game use_weak_mode branch)
            # 1800–2799: native clocks — quality capped by UCI_Elo, no intentional blunders
            target_elo = min(max(opponent_rating + STRENGTH_ADVANTAGE, 1320), 2850)
            sf.update_engine_parameters({
                "UCI_LimitStrength": True,
                "UCI_Elo": target_elo,
            })
            if opponent_rating < LIMIT_STRENGTH_THRESHOLD:
                logger.info(
                    f"Opponent {opponent_rating} ELO: UCI_LimitStrength = {target_elo} "
                    f"(fair play mode, movetime cap)"
                )
            else:
                logger.info(
                    f"Opponent {opponent_rating} ELO: UCI_LimitStrength = {target_elo} "
                    f"(intermediate mode, movetime cap)"
                )
        else:
            # Full power for elite opponents — no handicaps whatsoever
            logger.info(f"Opponent {opponent_rating} ELO: Full strength engine (MAXIMUM POWER)")
    
    return sf


def _parse_pv_from_info(info_line: str, depth: int) -> tuple[str, str]:
    """Parse evaluation and PV from a Stockfish info line.
    
    Returns:
        (eval_str, pv_display) - formatted evaluation and move sequence strings
    """
    eval_str = ""
    pv_display = ""
    
    try:
        # Parse evaluation: 'score cp VALUE' or 'score mate VALUE'
        if ' score mate ' in info_line:
            mate_val = int(info_line.split(' score mate ')[1].split()[0])
            eval_str = f" (Mate in {mate_val})"
        elif ' score cp ' in info_line:
            cp_val = int(info_line.split(' score cp ')[1].split()[0])
            eval_str = f" ({cp_val:+d} cp)"
        
        # Parse PV: everything after ' pv '
        if ' pv ' in info_line:
            pv_moves = info_line.split(' pv ')[1].split()
            pv_display = " ".join(pv_moves[:depth])
    except (IndexError, ValueError):
        pass
    
    return eval_str, pv_display


def _get_best_move_with_clocks(stockfish: Stockfish, wtime: int, btime: int,
                                winc: int = 0, binc: int = 0) -> Optional[str]:
    """Send go wtime/btime/winc/binc so Stockfish manages time natively.

    The library's get_best_move(wtime, btime) omits winc/binc, so we use the
    same internal two-step pattern (_put → _get_best_move_from_sf_popen_process)
    that all library search methods use internally.
    """
    stockfish._put(f"go wtime {wtime} btime {btime} winc {winc} binc {binc}")
    return stockfish._get_best_move_from_sf_popen_process()


def _extract_cp_from_info(info_line: str) -> Optional[int]:
    """Extract raw centipawn evaluation from a Stockfish info line.

    Converts mate scores to ±30000 so comparisons with cp thresholds
    work uniformly without special-casing the caller.

    Returns:
        cp value from white's perspective, or None if unavailable.
    """
    try:
        if ' score cp ' in info_line:
            return int(info_line.split(' score cp ')[1].split()[0])
        if ' score mate ' in info_line:
            mate = int(info_line.split(' score mate ')[1].split()[0])
            return 30000 if mate > 0 else -30000
    except (IndexError, ValueError):
        pass
    return None


def get_move_prediction(stockfish: Stockfish, game_id: str,
                         move_time_ms: int | None = None,
                         wtime: int | None = None, btime: int | None = None,
                         winc: int = 0, binc: int = 0,
                         prediction_depth: int = PREDICTION_DEPTH) -> Optional[str]:
    """Search for the best move and log the predicted continuation (PV).

    Two search modes:
    - movetime: supply move_time_ms for a fixed per-move budget
      (weak opponents / no clock data).
    - native clocks: supply wtime/btime/winc/binc so Stockfish manages its own
      time. Stockfish\'s internal algorithm accounts for game phase, position
      complexity, and increment — far superior to any manual formula.

    The PV is extracted at zero cost from the info line already stored after the
    search, so no second engine call is involved.

    Args:
        stockfish: Initialized Stockfish instance (position already set)
        game_id: Game ID for logging
        move_time_ms: Fixed time budget in ms (movetime mode)
        wtime: White\'s remaining clock in ms (native clock mode)
        btime: Black\'s remaining clock in ms (native clock mode)
        winc: White\'s increment in ms
        binc: Black\'s increment in ms
        prediction_depth: Number of PV half-moves to display in log

    Returns:
        Best move in UCI notation (e.g. "e2e4"), or None if search fails
    """
    try:
        if move_time_ms is not None:
            move = stockfish.get_best_move_time(move_time_ms)
        else:
            move = _get_best_move_with_clocks(stockfish, wtime, btime, winc, binc)
        
        if not move:
            return None
        
        # Log PV from the info line already produced by that search — no extra work
        if logger.isEnabledFor(logging.INFO):
            eval_str, pv_display = _parse_pv_from_info(stockfish.info(), prediction_depth)
            logger.info(f"[{game_id}] 🔮 Predicted line{eval_str}: {pv_display or move}")
        
        return move
        
    except Exception as e:
        logger.debug(f"[{game_id}] Move prediction failed: {e}")
        return None


def calculate_move_time(opponent_rating: int | None,
                        base_time: int = STOCKFISH_TIME) -> int:
    """Calculate movetime budget based on opponent strength.

    Used for ALL opponents with UCI_LimitStrength active (< FULL_STRENGTH_THRESHOLD),
    and as a fallback when the game has no clock data.

    IMPORTANT: native clocks (go wtime) cannot be used with UCI_LimitStrength —
    Stockfish time-manages like a limited human and may hang 30+ seconds on move 1.

    Strategy:
    - Below LIMIT_STRENGTH_THRESHOLD (1800): 40 % of base_time (1200ms default)
      UCI_LimitStrength already handles fairness, minimal time keeps things lively.
    - Between thresholds (1800–2799): 40–95 % linear scaling
      More time = plays closer to its capped ELO ceiling.
    - At or above FULL_STRENGTH_THRESHOLD (2800): 100 % (full power, native clocks)

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
        # Below 1800: minimal time — UCI_LimitStrength already limits quality
        adjusted_time = int(base_time * 0.4)  # 40% = 1200ms default
        logger.debug(f"Weak opponent ({opponent_rating}): {adjusted_time}ms (40%, UCI_LimitStrength active)")
    else:
        # Intermediate opponents (1800–2799): scale 40–95%, UCI_LimitStrength active
        # More time at higher rating = plays closer to the capped ELO ceiling
        rating_range = FULL_STRENGTH_THRESHOLD - LIMIT_STRENGTH_THRESHOLD  # 1000
        rating_offset = opponent_rating - LIMIT_STRENGTH_THRESHOLD
        time_percentage = 0.4 + (rating_offset / rating_range) * 0.55  # 40% to 95%
        
        adjusted_time = int(base_time * time_percentage)
        logger.debug(f"Intermediate opponent ({opponent_rating}): {adjusted_time}ms ({time_percentage*100:.0f}%)")
    
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
                  time_control: Dict[str, int], color: str = "random") -> Optional[str]:
    """Challenge a bot to a game.

    Returns:
        Challenge ID string if sent successfully, None otherwise
    """
    try:
        challenge = client.challenges.create(
            opponent_username,
            rated=True,
            clock_limit=time_control["limit"],
            clock_increment=time_control["increment"],
            color=color,
            variant="standard",
        )
        challenge_id = (
            challenge.get("id", "")
            if isinstance(challenge, dict)
            else getattr(challenge, "id", "")
        )
        logger.info(
            f"Challenged {opponent_username} to "
            f"{time_control['limit']}+{time_control['increment']} "
            f"(id: {challenge_id})"
        )
        return challenge_id or None
    except berserk.exceptions.ResponseError as e:
        logger.warning(f"Failed to challenge {opponent_username}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error challenging {opponent_username}: {e}")
        return None


def try_challenge_random_bot(client: berserk.Client, bot_username: str,
                             tracker: ChallengeTracker) -> Optional[str]:
    """Attempt to challenge a random suitable bot.

    Returns:
        Challenge ID if a challenge was sent, None otherwise
    """
    if not ENABLE_AUTO_CHALLENGE:
        return None

    if not tracker.can_challenge():
        remaining = tracker.get_remaining_challenges()
        logger.info(f"Challenge rate limit reached — {remaining} challenges left this hour")
        return None

    logger.debug("Fetching online bots...")
    online_bots = get_online_bots(client, limit=100)

    if not online_bots:
        logger.info("No online bots found")
        return None

    suitable_bots = filter_suitable_bots(
        online_bots,
        CHALLENGE_MIN_RATING,
        CHALLENGE_MAX_RATING,
        bot_username
    )

    if not suitable_bots:
        logger.info(
            f"No suitable bots online (rating range: {CHALLENGE_MIN_RATING}–{CHALLENGE_MAX_RATING})"
        )
        return None

    target_bot = random.choice(suitable_bots)
    time_control = random.choice(CHALLENGE_TIME_CONTROLS)

    challenge_id = challenge_bot(
        client,
        target_bot["username"],
        time_control,
        color="random"
    )

    if challenge_id:
        tracker.record_challenge()

    return challenge_id


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
    wtime_ms: int | None = None  # White's remaining clock in milliseconds
    btime_ms: int | None = None  # Black's remaining clock in milliseconds
    winc_ms: int = 0             # White's increment per move in milliseconds
    binc_ms: int = 0             # Black's increment per move in milliseconds
    last_eval_cp: int | None = None  # Cached eval from last move search (white's perspective)

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
                        
                        # Extract clock information from initial game state
                        state = event.get("state", {})
                        wtime_ms = parse_time_to_milliseconds(state.get("wtime")) or 0
                        btime_ms = parse_time_to_milliseconds(state.get("btime")) or 0
                        winc_ms  = parse_time_to_milliseconds(state.get("winc", 0)) or 0
                        binc_ms  = parse_time_to_milliseconds(state.get("binc", 0)) or 0

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
                        
                        # Refresh both clocks on every state update
                        if bot_is_white is not None:
                            wtime_ms = parse_time_to_milliseconds(event.get("wtime")) or wtime_ms
                            btime_ms = parse_time_to_milliseconds(event.get("btime")) or btime_ms
                        
                        # Check if game ended (resignation, timeout, abort, etc.)
                        status = event.get("status")
                        if status in ["mate", "resign", "stalemate", "timeout", "draw",
                                      "outoftime", "aborted", "cheat", "noStart",
                                      "unknownFinish", "variantEnd"]:
                            logger.info(f"[{game_id}] Game ended: {status}")
                            break
                        
                        # Only process new moves
                        if current_move_count > last_move_count:
                            new_moves = moves[last_move_count:]
                            for move in new_moves:
                                board.push_uci(move)
                                logger.info(f"[{game_id}] Opponent played {move}")
                            last_move_count = current_move_count

                        # Handle draw offers
                        if event.get("wdraw") or event.get("bdraw"):
                            logger.info(f"[{game_id}] Draw offer received")
                            
                            if stockfish:
                                try:
                                    accept_draw = False

                                    # Reuse the eval cached from the last move search — no extra engine
                                    # call needed. Fall back to get_evaluation() only at game start.
                                    if last_eval_cp is not None:
                                        # last_eval_cp is from white's perspective; flip for black bot
                                        evaluation = last_eval_cp if bot_is_white else -last_eval_cp
                                    else:
                                        # First few moves or no cache yet — quick explicit evaluation
                                        stockfish.set_fen_position(board.fen())
                                        eval_info = stockfish.get_evaluation()
                                        if eval_info["type"] == "cp":
                                            raw_cp = eval_info["value"]
                                        else:
                                            mate = eval_info["value"]
                                            raw_cp = 30000 if mate > 0 else -30000
                                        evaluation = raw_cp if bot_is_white else -raw_cp

                                    logger.info(f"[{game_id}] Position evaluation: {evaluation} centipawns")

                                    if abs(evaluation) >= 29000:
                                        # Mate evaluation — always decline
                                        if evaluation > 0:
                                            logger.info(f"[{game_id}] Declining draw offer (we have mate)")
                                        else:
                                            logger.info(f"[{game_id}] Declining draw offer (getting mated, but will fight)")
                                    elif -200 <= evaluation <= 200:
                                        accept_draw = True
                                        logger.info(f"[{game_id}] Accepting draw offer (balanced position: {evaluation}cp)")
                                    elif evaluation > 200:
                                        logger.info(f"[{game_id}] Declining draw offer (we're winning: {evaluation}cp)")
                                    else:
                                        logger.info(f"[{game_id}] Declining draw offer (we're losing but engine can play: {evaluation}cp)")

                                    # Send decision via API (try library first, then fall back to BOT endpoint)
                                    try:
                                        client.board.handle_draw_offer(game_id, accept=accept_draw)
                                    except Exception as api_error:
                                        # If the error indicates this endpoint isn't for BOT accounts,
                                        # fallback to the BOT HTTP endpoint which supports bot tokens.
                                        err_text = str(api_error).lower()
                                        if "not for bot accounts" in err_text or "403" in err_text or getattr(api_error, 'response', None) and getattr(api_error.response, 'status_code', None) == 403:
                                            try:
                                                url_action = "accept" if accept_draw else "decline"
                                                url = f"https://lichess.org/api/bot/game/{game_id}/draw/{url_action}"
                                                headers = {"Authorization": f"Bearer {TOKEN}"}
                                                resp = requests.post(url, headers=headers, timeout=10)
                                                if resp.status_code >= 400:
                                                    logger.error(f"[{game_id}] BOT endpoint responded {resp.status_code}: {resp.text}")
                                                else:
                                                    logger.info(f"[{game_id}] Responded to draw via BOT endpoint: {url_action}")
                                            except Exception as http_err:
                                                logger.error(f"[{game_id}] Failed to respond to draw offer via BOT endpoint: {http_err}")
                                        else:
                                            logger.error(f"[{game_id}] Failed to respond to draw offer: {api_error}")

                                except Exception as e:
                                    logger.error(f"[{game_id}] Error evaluating draw offer: {e}")
                                    # On error, attempt to decline draw and continue playing
                                    try:
                                        client.board.handle_draw_offer(game_id, accept=False)
                                    except Exception as api_error:
                                        try:
                                            url = f"https://lichess.org/api/bot/game/{game_id}/draw/decline"
                                            headers = {"Authorization": f"Bearer {TOKEN}"}
                                            requests.post(url, headers=headers, timeout=10)
                                        except Exception:
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
                        logger.info(
                            f"[{game_id}] Waiting for opponent"
                        )
                        continue

                    try:
                        logger.info(f"[{game_id}] Calculating move (move {board.fullmove_number})...")
                        stockfish.set_fen_position(board.fen())

                        # Decide search mode:
                        # - UCI_LimitStrength active (< FULL_STRENGTH_THRESHOLD):
                        #   MUST use go movetime. Native clocks + UCI_LimitStrength causes
                        #   Stockfish to time-manage as a limited player would, potentially
                        #   thinking 30+ seconds on the first move → Lichess abort.
                        # - Full strength (>= FULL_STRENGTH_THRESHOLD):
                        #   Native clocks — Stockfish manages time optimally.
                        use_movetime_mode = (
                            DYNAMIC_STRENGTH
                            and opponent_rating is not None
                            and opponent_rating < FULL_STRENGTH_THRESHOLD
                        )

                        if use_movetime_mode:
                            move_time = calculate_move_time(opponent_rating, STOCKFISH_TIME)
                            # Only allow the predicted move to be used as the played move
                            # for opponents at or above the configured prediction threshold.
                            allow_prediction_for_move = (
                                ENABLE_MOVE_PREDICTION
                                and opponent_rating is not None
                                and opponent_rating >= PREDICTION_MIN_USE_ELO
                            )

                            if allow_prediction_for_move:
                                move = get_move_prediction(
                                    stockfish, game_id,
                                    move_time_ms=move_time,
                                    prediction_depth=PREDICTION_DEPTH,
                                )
                                if not move:
                                    move = stockfish.get_best_move_time(move_time)
                            else:
                                # Use the engine's standard search result for the move,
                                # but still log the PV if prediction is enabled.
                                move = stockfish.get_best_move_time(move_time)
                                if ENABLE_MOVE_PREDICTION:
                                    eval_str, pv_display = _parse_pv_from_info(stockfish.info(), PREDICTION_DEPTH)
                                    logger.info(f"[{game_id}] 🔮 Predicted line{eval_str}: {pv_display or move}")

                            logger.debug(f"[{game_id}] Movetime mode: {move_time}ms (UCI_LimitStrength active)")

                        elif wtime_ms and btime_ms:
                            # For native clock games, only allow prediction to decide
                            # the actual played move when opponent meets the threshold.
                            allow_prediction_for_move = (
                                ENABLE_MOVE_PREDICTION
                                and opponent_rating is not None
                                and opponent_rating >= PREDICTION_MIN_USE_ELO
                            )

                            if allow_prediction_for_move:
                                move = get_move_prediction(
                                    stockfish, game_id,
                                    wtime=wtime_ms, btime=btime_ms,
                                    winc=winc_ms, binc=binc_ms,
                                    prediction_depth=PREDICTION_DEPTH,
                                )
                                if not move:
                                    move = _get_best_move_with_clocks(
                                        stockfish, wtime_ms, btime_ms, winc_ms, binc_ms
                                    )
                            else:
                                move = _get_best_move_with_clocks(
                                    stockfish, wtime_ms, btime_ms, winc_ms, binc_ms
                                )
                                if ENABLE_MOVE_PREDICTION:
                                    eval_str, pv_display = _parse_pv_from_info(stockfish.info(), PREDICTION_DEPTH)
                                    logger.info(f"[{game_id}] 🔮 Predicted line{eval_str}: {pv_display or move}")

                            logger.debug(
                                f"[{game_id}] Native clock mode — "
                                f"w:{wtime_ms}ms b:{btime_ms}ms inc:{winc_ms}/{binc_ms}ms"
                            )

                        else:
                            # No clock data — fall back to base movetime
                            move_time = calculate_move_time(opponent_rating, STOCKFISH_TIME)
                            move = stockfish.get_best_move_time(move_time)
                            logger.debug(f"[{game_id}] No clock data, movetime fallback: {move_time}ms")

                        # Cache eval for draw offer decisions — free from the search info line above
                        last_eval_cp = _extract_cp_from_info(stockfish.info())

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
                        if "not your turn" in error_str or "game already over" in error_str:
                            # Race condition: engine finished computing after game ended (abort/flag)
                            logger.info(f"[{game_id}] Game ended while making move (race condition)")
                        elif "connection" in error_str or "remote" in error_str:
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
                   challenge_tracker: ChallengeTracker,
                   retry_event: threading.Event,
                   pending_challenge: Dict):
    """Background thread that challenges bots whenever the bot is idle.

    Uses an event-based wait so the loop reacts immediately when a challenge
    is declined or canceled instead of sleeping through the full interval.

    pending_challenge is a shared dict written here and read by the main event
    loop: {'id': str, 'opponent': str, 'sent_at': float} or empty {}.
    """
    logger.info("Challenge loop started")
    ACCEPT_TIMEOUT = 90   # seconds to wait for opponent to accept
    RETRY_DELAY   = 30   # seconds to wait after a decline before trying again

    while not shutdown_requested:
        try:
            active_count = sum(1 for t in active_games.values() if t.is_alive())

            if not ENABLE_AUTO_CHALLENGE or active_count > 0:
                if active_count > 0:
                    logger.debug(f"Skipping challenge: {active_count} active game(s)")
                retry_event.clear()
                retry_event.wait(timeout=CHALLENGE_CHECK_INTERVAL)
                retry_event.clear()
                continue

            # ── A challenge was already sent — check its status ──────────────
            if pending_challenge:
                elapsed = time.monotonic() - pending_challenge["sent_at"]
                if elapsed < ACCEPT_TIMEOUT:
                    wait_left = ACCEPT_TIMEOUT - elapsed
                    logger.debug(
                        f"Waiting for {pending_challenge['opponent']} to accept "
                        f"challenge {pending_challenge['id']} ({wait_left:.0f}s left)"
                    )
                    retry_event.clear()
                    retry_event.wait(timeout=wait_left)
                    retry_event.clear()
                    continue
                else:
                    logger.info(
                        f"No response from {pending_challenge['opponent']} after "
                        f"{elapsed:.0f}s — they may be offline. Trying another bot in {RETRY_DELAY}s..."
                    )
                    pending_challenge.clear()
                    retry_event.wait(timeout=RETRY_DELAY)
                    retry_event.clear()

            # ── Send a new challenge ─────────────────────────────────────────
            logger.info("No active games — looking for a bot to challenge...")
            challenge_id = try_challenge_random_bot(client, bot_username, challenge_tracker)

            if challenge_id:
                pending_challenge["id"] = challenge_id
                pending_challenge["opponent"] = "unknown"
                pending_challenge["sent_at"] = time.monotonic()
                # Wait up to ACCEPT_TIMEOUT; fires early on decline/cancel
                retry_event.clear()
                retry_event.wait(timeout=ACCEPT_TIMEOUT)
                retry_event.clear()
            else:
                # Nothing to challenge right now — wait normal interval
                retry_event.clear()
                retry_event.wait(timeout=CHALLENGE_CHECK_INTERVAL)
                retry_event.clear()

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
    retry_event = threading.Event()   # signals challenge loop to wake up immediately
    pending_challenge: Dict = {}      # shared state: {id, opponent, sent_at}

    # Start challenge loop in background thread
    challenge_thread = threading.Thread(
        target=challenge_loop,
        args=(client, bot_username, active_games, challenge_tracker,
              retry_event, pending_challenge),
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
                            # Outgoing challenge — update opponent name in pending tracker
                            logger.debug(f"Outgoing challenge to {dest_username}: {cid}")
                            if pending_challenge.get("id") == cid:
                                pending_challenge["opponent"] = dest_username
                    
                    elif event["type"] == "challengeDeclined":
                        challenge = event.get("challenge", {})
                        decliner = challenge.get("destUser", {}).get("name", "Unknown")
                        reason = challenge.get("declineReason", challenge.get("declineReasonKey", "no reason given"))
                        cid = challenge.get("id", "")
                        is_ours = pending_challenge.get("id") == cid
                        logger.info(
                            f"Challenge {'(ours) ' if is_ours else ''}declined by {decliner}"
                            f" — reason: {reason}"
                        )
                        if is_ours:
                            pending_challenge.clear()
                        # Always signal retry so challenge loop can pick the next bot
                        threading.Timer(30, retry_event.set).start()

                    elif event["type"] == "challengeCanceled":
                        challenge = event.get("challenge", {})
                        challenger = challenge.get("challenger", {}).get("name", "Unknown")
                        cid = challenge.get("id", "")
                        is_ours = pending_challenge.get("id") == cid
                        logger.info(
                            f"Challenge {'(ours) ' if is_ours else ''}canceled by {challenger}"
                        )
                        if is_ours:
                            pending_challenge.clear()
                            retry_event.set()

                    elif event["type"] == "gameStart":
                        game_id = event["game"]["id"]

                        # Start game thread and register in active_games FIRST —
                        # before clearing pending_challenge or waking the challenge loop.
                        # This ensures the loop's active_count check sees the new game
                        # and won't send a second challenge.
                        thread = threading.Thread(
                            target=play_game,
                            args=(client, game_id, bot_username),
                            daemon=True,
                        )
                        active_games[game_id] = thread
                        thread.start()

                        # Now safe to clear pending challenge and wake the loop
                        if pending_challenge:
                            logger.info(
                                f"Challenge accepted — game {game_id} started "
                                f"(challenge id: {pending_challenge.get('id', '?')})"
                            )
                            pending_challenge.clear()
                            retry_event.set()

                        logger.info(f"Game {game_id} started")

                    elif event["type"] == "gameFinish":
                        game_id = event["game"]["id"]
                        if game_id in active_games:
                            # Clean up finished game thread
                            active_games[game_id].join(timeout=1)
                            del active_games[game_id]
                            logger.info(f"Game {game_id} finished — looking for next challenge...")
                            retry_event.set()  # wake challenge loop immediately when game ends

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
