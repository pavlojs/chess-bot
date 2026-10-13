"""
Axiom Chess Bot – stable BOT API architecture using Berserk and Stockfish
"""

import json
import os
import signal
import sys
import threading
import queue
import logging
import chess
import berserk
from berserk.exceptions import ResponseError, ApiError
import time
import random
from collections import deque
from datetime import timedelta

from stockfish import Stockfish, StockfishException
from dataclasses import dataclass, field
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
    MAX_CHALLENGES_PER_DAY,
    CHALLENGE_MIN_RATING,
    CHALLENGE_MAX_RATING,
    CHALLENGE_TIME_CONTROLS,
    CHALLENGE_CHECK_INTERVAL,
    ENABLE_MOVE_PREDICTION,
    PREDICTION_DEPTH,
    PREDICTION_RECOVER_THRESHOLD,
    PREDICTION_RECOVER_ELO_BOOST,
    MOVETIME_CLOCK_SAFETY,
    MOVETIME_MIN_MS,
    MOVETIME_ESTIMATED_MOVES,
    MOVETIME_MIN_MOVES_LEFT,
    GAME_WATCHDOG_INTERVAL,
    GAME_WATCHDOG_ABORT_TIMEOUT,
    MAX_CONCURRENT_GAMES,
)

import healthcheck
from logging_config import setup_logger

logger = setup_logger(__name__)
shutdown_requested = False
# Set together with shutdown_requested, so that waits end at once on shutdown.
_shutdown_event = threading.Event()

LICHESS_URL = "https://lichess.org"

_TERMINAL_STATUSES = frozenset({
    "mate", "resign", "stalemate", "timeout", "draw",
    "outoftime", "aborted", "cheat", "noStart",
    "unknownFinish", "variantEnd",
})

# The state of the running bot, so the shutdown handler can wait for its game threads
_running_state: Optional["BotState"] = None

# Seconds a shutdown waits for game threads before the process ends anyway
SHUTDOWN_TIMEOUT = 15


# ─────────────────────────────────────────────
# CHALLENGE TRACKER
# ─────────────────────────────────────────────

class ChallengeTracker:
    """Counts the challenges the bot creates, against an hourly and a daily limit.

    Lichess counts every request to create a challenge, including the ones it
    then refuses, so every attempt is recorded here and not only the ones that
    produced a challenge.
    """

    HOUR = 3600
    DAY = 86400

    def __init__(self, max_per_hour: int = MAX_CHALLENGES_PER_HOUR,
                 max_per_day: int = MAX_CHALLENGES_PER_DAY, clock=time.monotonic):
        self.max_per_hour = max_per_hour
        self.max_per_day = max_per_day
        self._clock = clock
        self._attempts: deque = deque()  # times of the attempts of the last day, oldest first
        self.lock = threading.Lock()

    def _recent(self, now: float) -> List[float]:
        """Forget attempts older than a day and return those of the last hour."""
        while self._attempts and self._attempts[0] <= now - self.DAY:
            self._attempts.popleft()
        return [t for t in self._attempts if t > now - self.HOUR]

    def record_challenge(self):
        """Record an attempt to create a challenge, whatever came of it."""
        with self.lock:
            self._attempts.append(self._clock())

    def can_challenge(self) -> bool:
        return self.get_remaining_challenges() > 0

    def get_remaining_challenges(self) -> int:
        """Challenges that may still be created right now, under both limits."""
        with self.lock:
            last_hour = self._recent(self._clock())
            return max(0, min(self.max_per_hour - len(last_hour), self.max_per_day - len(self._attempts)))

    def counts(self) -> tuple[int, int]:
        """Attempts in the last hour and in the last 24 hours."""
        with self.lock:
            last_hour = self._recent(self._clock())
            return len(last_hour), len(self._attempts)

    def seconds_until_free(self) -> float:
        """Seconds until another challenge may be created; 0 when one may be created now."""
        with self.lock:
            now = self._clock()
            last_hour = self._recent(now)
            wait = 0.0
            if self.max_per_hour <= 0 or self.max_per_day <= 0:
                return float(self.DAY)
            if len(last_hour) >= self.max_per_hour:
                # The attempt whose expiry brings the hour back under the limit.
                wait = max(wait, last_hour[len(last_hour) - self.max_per_hour] + self.HOUR - now)
            if len(self._attempts) >= self.max_per_day:
                wait = max(wait, self._attempts[len(self._attempts) - self.max_per_day] + self.DAY - now)
            return wait


# ─────────────────────────────────────────────
# CUSTOM EXCEPTIONS
# ─────────────────────────────────────────────

class RateLimitError(Exception):
    """Lichess refused a request with HTTP 429 Too Many Requests."""

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        # Seconds until the limit is lifted, when the answer says so.
        self.retry_after = retry_after


# Gateway answers that mean "Lichess is briefly unavailable": worth a retry.
_GATEWAY_ERRORS = frozenset({502, 503, 504})


def _http_status(exc: BaseException) -> Optional[int]:
    """HTTP status of a failed Lichess call, or None if Lichess never answered.

    Read it from the exception, never through ``exc.response``: a
    requests.Response is falsy for every status of 400 and above, so
    ``exc.response and exc.response.status_code == ...`` is false for exactly
    the answers it is meant to recognise.
    """
    if isinstance(exc, ResponseError):
        return exc.status_code
    return None


def _retry_after(exc: BaseException) -> Optional[int]:
    """Seconds Lichess asks to wait, from a 429 answer that names the limit it applied.

    The limit on games between bots answers
    ``{"error": ..., "ratelimit": {"key": "bot.vsBot.day", "seconds": N}}``.
    The general limiter only says "Too many requests", and then this is None.
    """
    cause = getattr(exc, "cause", None)
    if isinstance(cause, dict) and isinstance(cause.get("ratelimit"), dict):
        seconds = cause["ratelimit"].get("seconds")
        if isinstance(seconds, int) and seconds > 0:
            return seconds
    return None


_NETWORK_ERRORS = (ChunkedEncodingError, ProtocolError, ConnectionError, Timeout)


def _is_network_error(exc: BaseException) -> bool:
    """True when Lichess could not be reached, as opposed to having answered.

    berserk wraps whatever requests raises while a request is being sent in
    ApiError, so a refused, reset or timed-out connection does not arrive as a
    requests exception. Failures while a stream is being read come straight
    from requests and are not wrapped. Both have to count.
    """
    if isinstance(exc, _NETWORK_ERRORS):
        return True
    if isinstance(exc, ApiError) and not isinstance(exc, ResponseError):
        return isinstance(exc.__cause__, RequestException)
    return False


# ─────────────────────────────────────────────
# SIGNAL HANDLING
# ─────────────────────────────────────────────

def handle_shutdown(signum, frame):
    """First signal: let the game threads wind down, then exit. Second signal: exit now."""
    global shutdown_requested
    if shutdown_requested:
        logger.warning("Force shutdown!")
        sys.exit(1)

    shutdown_requested = True
    _shutdown_event.set()
    logger.warning("Shutdown signal received, waiting for game threads to finish...")
    threading.Thread(target=_finish_shutdown, daemon=True).start()


def _finish_shutdown(exit_process=os._exit):
    """Wait for the game threads, then end the process.

    The main thread is normally blocked reading the event stream, and
    sys.exit() called from this thread would end this thread alone, leaving
    the process to be killed by its supervisor. os._exit ends the process.
    """
    deadline = time.monotonic() + SHUTDOWN_TIMEOUT
    state = _running_state
    while state is not None and time.monotonic() < deadline:
        with state.games_lock:
            alive = [t for t in state.active_games.values() if t.is_alive()]
        if not alive:
            break
        logger.info(f"Waiting for {len(alive)} game thread(s) to finish...")
        for t in alive:
            t.join(timeout=max(0.5, deadline - time.monotonic()))

    # Remove the heartbeat so a process that lingers reads as unhealthy
    healthcheck.clear()

    logger.info("Graceful shutdown complete")
    logging.shutdown()
    exit_process(0)


def install_signal_handlers():
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
    """Call ``func``, retrying with exponential backoff while Lichess is unreachable.

    Network failures and gateway answers (502, 503, 504) are retried; any other
    error is raised at once, since repeating the call would not change it.

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
        except Exception as e:
            if not (_is_network_error(e) or _http_status(e) in _GATEWAY_ERRORS):
                logger.error(f"{description} failed: {e}")
                raise

            if attempt == max_retries - 1:
                logger.error(f"{description} failed after {max_retries} attempts: {e}")
                raise

            delay = min(base_delay * (2 ** attempt), max_delay)
            logger.warning(f"{description} failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
            time.sleep(delay)


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

    # Only accept standard chess — reject all variants (chess960, antichess, atomic, etc.)
    variant = challenge.get("variant", {})
    variant_key = variant.get("key", "standard") if isinstance(variant, dict) else str(variant)
    if variant_key != "standard":
        logger.info(f"Rejecting challenge: unsupported variant '{variant_key}'")
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


# Sentinel used by _get_best_move_with_clocks to store raw output in
# stockfish._raw_stockfish_output so that _get_last_info_line() can
# retrieve the info line later.
def _clocks_search_sentinel():
    pass


def _get_best_move_with_clocks(stockfish: Stockfish, wtime: int, btime: int,
                                winc: int = 0, binc: int = 0) -> Optional[str]:
    """Send go wtime/btime/winc/binc so Stockfish manages time natively.

    The library's get_best_move(wtime, btime) omits winc/binc, so we use the
    same internal two-step pattern (_put → _get_best_move_from_sf_popen_process)
    that all library search methods use internally.
    """
    stockfish._put(f"go wtime {wtime} btime {btime} winc {winc} binc {binc}")
    return stockfish._get_best_move_from_sf_popen_process(_clocks_search_sentinel)


def _get_last_info_line(stockfish: Stockfish, func_ref) -> str:
    """Return the last info line from the most recent search.

    Uses ``raw_stockfish_output`` (stockfish >= 5.0) to retrieve the
    penultimate line (the last ``info`` line before ``bestmove``).
    Returns an empty string if the output is unavailable.
    """
    try:
        lines = stockfish.raw_stockfish_output(func_ref)
        if lines and len(lines) >= 2:
            return lines[-2]
    except Exception as e:
        logger.debug(f"Could not read raw Stockfish output: {e}")
    return ""


def _get_last_eval_cp(stockfish: Stockfish) -> Optional[int]:
    """Return cached cp eval from the most recent search, trying all known function keys."""
    for func_ref in (stockfish.get_best_move_time, _clocks_search_sentinel, stockfish.get_best_move):
        info = _get_last_info_line(stockfish, func_ref)
        if info:
            cp = _extract_cp_from_info(info)
            if cp is not None:
                return cp
    return None


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


def _extract_mate_from_info(info_line: str) -> Optional[int]:
    """Extract raw mate distance from a Stockfish info line.

    Returns the mate value (positive or negative) if present, otherwise None.
    Positive mate means mate for side to move; negative means being mated.
    """
    try:
        if ' score mate ' in info_line:
            return int(info_line.split(' score mate ')[1].split()[0])
    except (IndexError, ValueError):
        pass
    return None


def _get_full_power_move(stockfish: Stockfish, game_id: str,
                          move_time_ms: int,
                          restore_elo: int | None = None) -> Optional[str]:
    """Search for the best move at full engine power, bypassing UCI_LimitStrength.

    Temporarily disables UCI_LimitStrength, runs a movetime search at maximum
    engine quality, then restores the strength cap so all subsequent searches
    remain limited.  Used for forced-mate and mate-avoidance situations where
    correctness matters more than playing at the opponent's level.

    Args:
        stockfish:   Initialized Stockfish instance (position already set).
        game_id:     Game ID for logging.
        move_time_ms: Time budget in ms for the full-power search.
        restore_elo: If provided, re-applies UCI_LimitStrength at this ELO
                     after the search to restore the active strength cap.

    Returns:
        Best move string, or None on failure.
    """
    try:
        stockfish.update_engine_parameters({"UCI_LimitStrength": False})
        move = stockfish.get_best_move_time(move_time_ms)
        return move
    except Exception as e:
        logger.debug(f"[{game_id}] Full-power move search failed: {e}")
        return None
    finally:
        if restore_elo is not None:
            try:
                stockfish.update_engine_parameters({
                    "UCI_LimitStrength": True,
                    "UCI_Elo": restore_elo,
                })
            except Exception as e:
                logger.debug(f"Could not restore UCI_Elo to {restore_elo}: {e}")


def get_move_prediction(stockfish: Stockfish, game_id: str,
                         move_time_ms: int | None = None,
                         wtime: int | None = None, btime: int | None = None,
                         winc: int = 0, binc: int = 0,
                         prediction_depth: int = PREDICTION_DEPTH) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """Search for the best move and log the predicted continuation (PV).

    Returns a tuple `(best_move, mate_value, cp_value)` where `mate_value` is
    the mate distance parsed from the engine info (positive for mate for
    side-to-move, negative for being mated), or `None` if no mate score was
    present. `cp_value` is the centipawn evaluation (or ±30000 for mate
    scores), or `None` if unavailable.

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
        Tuple of (best_move, mate_value, cp_value).  Each element is None
        when the search fails or the corresponding info is not available.
    """
    try:
        if move_time_ms is not None:
            move = stockfish.get_best_move_time(move_time_ms)
        else:
            move = _get_best_move_with_clocks(stockfish, wtime, btime, winc, binc)

        if not move:
            return None, None, None

        # Capture engine info once and reuse.
        # In stockfish >= 5.0 `.info()` was removed; use raw_stockfish_output instead.
        if move_time_ms is not None:
            info_line = _get_last_info_line(stockfish, stockfish.get_best_move_time)
        else:
            info_line = _get_last_info_line(stockfish, _clocks_search_sentinel)

        # Parse PV, mate and cp info for logging and decision-making
        if ENABLE_MOVE_PREDICTION and logger.isEnabledFor(logging.INFO):
            eval_str, pv_display = _parse_pv_from_info(info_line, prediction_depth)
            logger.info(f"[{game_id}] 🔮 Predicted line{eval_str}: {pv_display or move}")

        mate_val = _extract_mate_from_info(info_line)
        cp_val = _extract_cp_from_info(info_line)

        return move, mate_val, cp_val
        
    except Exception as e:
        logger.debug(f"[{game_id}] Move prediction failed: {e}")
        return None, None, None


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


def clock_aware_move_time(
    opponent_rating: int | None,
    base_time: int,
    remaining_ms: int | None,
    increment_ms: int = 0,
    moves_left_estimate: int = 20,
) -> int:
    """Return a movetime budget that respects the remaining clock.

    Combines calculate_move_time (rating-based ideal budget) with a hard cap
    derived from the bot's actual remaining time, preventing outoftime losses.

    Clock budget formula:
        clock_budget = (remaining_ms / moves_left_estimate + increment_ms) * MOVETIME_CLOCK_SAFETY
        result       = min(ideal_budget, clock_budget)  -- capped by clock
        result       = max(result, MOVETIME_MIN_MS)     -- floored to stay legal

    Args:
        opponent_rating:   Opponent ELO (forwarded to calculate_move_time).
        base_time:         Base movetime in ms (forwarded to calculate_move_time).
        remaining_ms:      Bot's remaining clock in ms.  None → no cap applied.
        increment_ms:      Bot's per-move increment in ms.
        moves_left_estimate: Estimated number of moves remaining in the game.

    Returns:
        Thinking time in milliseconds.
    """
    ideal = calculate_move_time(opponent_rating, base_time)

    if not remaining_ms:
        return ideal

    clock_budget = int(
        (remaining_ms / moves_left_estimate + increment_ms) * MOVETIME_CLOCK_SAFETY
    )
    clock_budget = max(clock_budget, MOVETIME_MIN_MS)

    result = min(ideal, clock_budget)
    if result < ideal:
        logger.debug(
            f"Clock-aware cap: ideal={ideal}ms → {result}ms "
            f"(remaining={remaining_ms}ms, inc={increment_ms}ms, "
            f"moves_left~{moves_left_estimate})"
        )
    return result


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
        # Propagate rate-limit errors so callers can apply backoff
        if _http_status(e) == 429:
            raise RateLimitError(str(e), _retry_after(e)) from e
        return None
    except Exception as e:
        logger.error(f"Error challenging {opponent_username}: {e}")
        return None


def try_challenge_random_bot(client: berserk.Client, bot_username: str,
                             tracker: ChallengeTracker) -> Optional[tuple[str, str]]:
    """Challenge one random suitable bot.

    Returns:
        (challenge id, opponent name) if a challenge was created, None otherwise
    """
    if not ENABLE_AUTO_CHALLENGE:
        return None

    if not tracker.can_challenge():
        last_hour, last_day = tracker.counts()
        logger.info(
            f"Challenge limit reached — {last_hour}/{tracker.max_per_hour} this hour, "
            f"{last_day}/{tracker.max_per_day} in 24 hours"
        )
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

    # Counted before the outcome is known: Lichess counts the request too.
    tracker.record_challenge()
    challenge_id = challenge_bot(
        client,
        target_bot["username"],
        time_control,
        color="random"
    )

    return (challenge_id, target_bot["username"]) if challenge_id else None


# ─────────────────────────────────────────────
# GAME THREAD
# ─────────────────────────────────────────────

class _GameStuck(Exception):
    """Raised by the watchdog when the game is over but the stream didn't report it."""


def _stream_with_watchdog(stream, client, game_id, check_interval):
    """Wrap a blocking game-stream iterator with an API watchdog.

    A daemon reader thread pulls events from *stream* into a queue.
    The main thread reads the queue with *check_interval* timeouts;
    on each timeout it polls the Lichess API to verify the game is
    still in progress.  This is safe for classical games (long thinks)
    because the watchdog only breaks when the API confirms the game ended.

    Additionally, if the game stays in "started" status (no moves) for
    longer than GAME_WATCHDOG_ABORT_TIMEOUT seconds, the watchdog will
    attempt to abort/resign and terminate the stream to prevent the bot
    from being stuck indefinitely by an offline opponent.
    """
    q: queue.Queue = queue.Queue()
    _sentinel = object()
    _consecutive_failures = 0
    _MAX_CONSECUTIVE_FAILURES = 10  # after 10 failures (~10 min) force-end
    _started_since: float | None = None  # monotonic time when we first saw "started" status

    def _reader():
        try:
            for event in stream:
                q.put(event)
            q.put(_sentinel)
        except Exception as exc:
            q.put(exc)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    while True:
        try:
            item = q.get(timeout=check_interval)
            _consecutive_failures = 0  # reset on any event
            _started_since = None  # stream event received → game is progressing
        except queue.Empty:
            # No stream event — ask the API whether the game is still alive
            try:
                game = client.games.export(game_id)
                status = game.get("status")
                if status in _TERMINAL_STATUSES:
                    logger.info(f"[{game_id}] Watchdog: game ended via API ({status})")
                    raise _GameStuck(f"Game {game_id} ended ({status}) but stream did not report it")

                # Track how long the game has been in "started" status (no moves)
                if status == "started":
                    if _started_since is None:
                        _started_since = time.monotonic()
                    elapsed_stuck = time.monotonic() - _started_since
                    if elapsed_stuck >= GAME_WATCHDOG_ABORT_TIMEOUT:
                        logger.warning(
                            f"[{game_id}] Watchdog: game stuck in '{status}' for "
                            f"{elapsed_stuck:.0f}s — aborting"
                        )
                        try:
                            client.bots.abort_game(game_id)
                            logger.info(f"[{game_id}] Watchdog: abort sent")
                        except Exception:
                            try:
                                client.bots.resign_game(game_id)
                                logger.info(f"[{game_id}] Watchdog: resign sent (abort failed)")
                            except Exception as resign_err:
                                logger.warning(f"[{game_id}] Watchdog: resign also failed: {resign_err}")
                        raise _GameStuck(
                            f"Game {game_id} stuck in '{status}' for {elapsed_stuck:.0f}s, forced abort"
                        )
                    logger.info(
                        f"[{game_id}] Watchdog: game still active ({status}) "
                        f"— stuck for {elapsed_stuck:.0f}s/{GAME_WATCHDOG_ABORT_TIMEOUT}s"
                    )
                else:
                    _started_since = None  # game progressed past "started"
                    logger.info(f"[{game_id}] Watchdog: game still active ({status})")

                _consecutive_failures = 0
            except _GameStuck:
                raise
            except Exception as e:
                _consecutive_failures += 1
                if _consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    logger.warning(
                        f"[{game_id}] Watchdog: {_consecutive_failures} consecutive API failures, "
                        f"assuming game is over"
                    )
                    raise _GameStuck(
                        f"Game {game_id}: watchdog could not verify game status "
                        f"after {_consecutive_failures} attempts"
                    )
                if _consecutive_failures >= 3:
                    logger.warning(f"[{game_id}] Watchdog API check failed ({_consecutive_failures}x): {e}")
                else:
                    logger.info(f"[{game_id}] Watchdog API check failed: {e}")
            continue
        if item is _sentinel:
            return
        if isinstance(item, BaseException):
            raise item
        yield item


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
    last_opponent_draw: bool = False  # Tracks opponent draw flag from previous event (rising-edge detection)
    _claim_victory_timer: threading.Timer | None = None  # Timer for claiming win after opponentGone
    _no_first_move_timer: threading.Timer | None = None  # Abort game if opponent never plays first move

    try:
        # Retry stream connection with backoff
        while not shutdown_requested:
            try:
                raw_stream = client.bots.stream_game_state(game_id)
                stream = _stream_with_watchdog(raw_stream, client, game_id, GAME_WATCHDOG_INTERVAL)
                
                for event in stream:
                    if shutdown_requested:
                        break

                    if event["type"] == "gameFull":
                        board.reset()

                        # Check if game is already over (e.g. reconnecting to a finished game)
                        initial_status = event.get("state", {}).get("status")
                        if initial_status in _TERMINAL_STATUSES:
                            logger.info(f"[{game_id}] Game already ended ({initial_status}), exiting")
                            break

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

                        # Kill previous Stockfish process if reconnecting
                        if stockfish is not None:
                            try:
                                if hasattr(stockfish, "_stockfish") and stockfish._stockfish:
                                    stockfish._stockfish.kill()
                                    stockfish._stockfish.wait()
                            except Exception as e:
                                logger.debug(f"Could not kill Stockfish subprocess: {e}")

                        stockfish = init_stockfish(opponent_rating)
                        last_opponent_draw = False  # Reset draw state on (re)connect

                        logger.info(
                            f"Game {game_id}: playing as "
                            f"{'white' if bot_is_white else 'black'} "
                            f"vs {opponent_rating}"
                        )

                        # If no moves yet and it's the opponent's turn, start a safety
                        # timer to abort the game if the opponent never plays.  Lichess
                        # should handle this with noStart, but this is a client-side backup.
                        if last_move_count == 0 and not (
                            (board.turn == chess.WHITE and bot_is_white) or
                            (board.turn == chess.BLACK and not bot_is_white)
                        ):
                            def _abort_no_first_move(gid=game_id):
                                logger.warning(f"[{gid}] Opponent never made first move — aborting game")
                                try:
                                    client.bots.abort_game(gid)
                                except Exception as err:
                                    logger.debug(f"[{gid}] Abort after no first move failed: {err}")

                            _no_first_move_timer = threading.Timer(120.0, _abort_no_first_move)
                            _no_first_move_timer.daemon = True
                            _no_first_move_timer.start()
                            logger.info(f"[{game_id}] Waiting for opponent's first move (abort in 120s if no move)")

                        # Don't continue here - we need to check if it's our turn

                    if event["type"] == "gameState":
                        moves = event["moves"].split() if event.get("moves") else []
                        current_move_count = len(moves)

                        # Cancel no-first-move timer once any move arrives
                        if _no_first_move_timer is not None and current_move_count > 0:
                            _no_first_move_timer.cancel()
                            _no_first_move_timer = None
                        
                        # Refresh both clocks on every state update
                        if bot_is_white is not None:
                            wtime_ms = parse_time_to_milliseconds(event.get("wtime")) or wtime_ms
                            btime_ms = parse_time_to_milliseconds(event.get("btime")) or btime_ms
                        
                        # Check if game ended (resignation, timeout, abort, etc.)
                        status = event.get("status")
                        if status in _TERMINAL_STATUSES:
                            logger.info(f"[{game_id}] Game ended: {status}")
                            break
                        
                        # Only process new moves
                        if current_move_count > last_move_count:
                            new_moves = moves[last_move_count:]
                            for move in new_moves:
                                board.push_uci(move)
                                logger.info(f"[{game_id}] Move received: {move}")
                            last_move_count = current_move_count

                        # Handle draw offers — respond only to the *opponent's* offer and only
                        # when it first appears (rising edge), to avoid duplicate replies.
                        opponent_draw_now = (
                            bool(event.get("bdraw") if bot_is_white else event.get("wdraw"))
                            if bot_is_white is not None else False
                        )
                        if opponent_draw_now and not last_opponent_draw:
                            logger.info(f"[{game_id}] Draw offer received")
                            
                            if stockfish:
                                try:
                                    accept_draw = False

                                    # Reuse the eval cached from the last move search — no extra engine
                                    # call needed. Fall back to get_evaluation() only at game start.
                                    if last_eval_cp is not None:
                                        # last_eval_cp is from side-to-move perspective at search time,
                                        # which was always the bot's turn → already bot's perspective.
                                        evaluation = last_eval_cp
                                    else:
                                        # First few moves or no cache yet — quick explicit evaluation.
                                        # get_evaluation() returns from current side-to-move perspective;
                                        # flip only if it's the opponent's turn.
                                        stockfish.set_fen_position(board.fen())
                                        eval_info = stockfish.get_evaluation()
                                        if eval_info["type"] == "cp":
                                            raw_cp = eval_info["value"]
                                        else:
                                            mate = eval_info["value"]
                                            raw_cp = 30000 if mate > 0 else -30000
                                        bot_is_side_to_move = (board.turn == chess.WHITE) == bot_is_white
                                        evaluation = raw_cp if bot_is_side_to_move else -raw_cp

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
                                        if "not for bot accounts" in err_text or "403" in err_text or (getattr(api_error, 'response', None) and getattr(api_error.response, 'status_code', None) == 403):
                                            try:
                                                url_action = "yes" if accept_draw else "no"
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
                                            url = f"https://lichess.org/api/bot/game/{game_id}/draw/no"
                                            headers = {"Authorization": f"Bearer {TOKEN}"}
                                            requests.post(url, headers=headers, timeout=10)
                                        except Exception as e:
                                            logger.debug(f"Draw decline failed for {game_id}: {e}")

                        last_opponent_draw = opponent_draw_now

                    if event["type"] == "opponentGone":
                        gone = event.get("gone", False)
                        claim_seconds = event.get("claimWinInSeconds")
                        if gone:
                            logger.warning(f"[{game_id}] Opponent has disconnected"
                                           f"{f' (can claim win in {claim_seconds}s)' if claim_seconds else ''}")
                            # Cancel any previous timer before starting a new one
                            if _claim_victory_timer is not None:
                                _claim_victory_timer.cancel()
                                _claim_victory_timer = None
                            if claim_seconds is not None:
                                def _claim_win(_gid=game_id):
                                    try:
                                        url = f"https://lichess.org/api/bot/game/{_gid}/claim-victory"
                                        headers = {"Authorization": f"Bearer {TOKEN}"}
                                        resp = requests.post(url, headers=headers, timeout=10)
                                        if resp.status_code < 400:
                                            logger.info(f"[{_gid}] Claimed victory (opponent gone)")
                                        else:
                                            logger.warning(f"[{_gid}] Claim victory returned {resp.status_code}: {resp.text}")
                                    except Exception as e:
                                        logger.error(f"[{_gid}] Failed to claim victory: {e}")
                                _claim_victory_timer = threading.Timer(claim_seconds + 1, _claim_win)
                                _claim_victory_timer.daemon = True
                                _claim_victory_timer.start()
                        else:
                            logger.info(f"[{game_id}] Opponent has reconnected")
                            if _claim_victory_timer is not None:
                                _claim_victory_timer.cancel()
                                _claim_victory_timer = None

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
                            _my_remaining = wtime_ms if bot_is_white else btime_ms
                            _my_inc = winc_ms if bot_is_white else binc_ms
                            _moves_left = max(
                                MOVETIME_MIN_MOVES_LEFT,
                                MOVETIME_ESTIMATED_MOVES - board.fullmove_number // 2,
                            )
                            move_time = clock_aware_move_time(
                                opponent_rating, STOCKFISH_TIME,
                                _my_remaining, _my_inc, _moves_left,
                            )
                            # ELO to restore after full-power mate searches
                            _target_elo = (
                                min(max(opponent_rating + STRENGTH_ADVANTAGE, 1320), 2850)
                                if opponent_rating else None
                            )

                            # Measure wall-clock time spent in prediction so every
                            # subsequent search gets a properly adjusted clock budget.
                            _pred_start = time.monotonic()
                            predicted_move, mate_val, pred_cp = get_move_prediction(
                                stockfish, game_id,
                                move_time_ms=move_time,
                                prediction_depth=PREDICTION_DEPTH,
                            )
                            _pred_elapsed_ms = int((time.monotonic() - _pred_start) * 1000)
                            # Remaining clock after the prediction search, floored at 0.
                            _remaining_after_pred = (
                                max(0, _my_remaining - _pred_elapsed_ms)
                                if _my_remaining else None
                            )

                            # Evaluate prediction from the bot's perspective.
                            # UCI 'score cp' is always from the side-to-move
                            # perspective, and get_move_prediction is called only
                            # on the bot's turn — so pred_cp is already the bot's
                            # score.  No colour flip needed.
                            eval_for_bot = pred_cp

                            # If predictor found a mating sequence for us, follow it
                            # using full-power Stockfish to guarantee the fastest/best mate.
                            if mate_val is not None and mate_val > 0:
                                _fp_time = clock_aware_move_time(
                                    opponent_rating, STOCKFISH_TIME,
                                    _remaining_after_pred, _my_inc, _moves_left,
                                )
                                move = (
                                    _get_full_power_move(stockfish, game_id, _fp_time, restore_elo=_target_elo)
                                    or predicted_move
                                )
                                logger.info(f"[{game_id}] Following mating sequence at full power (mate in {mate_val}, fp_time={_fp_time}ms)")
                            # If predictor indicates we're being mated, use full-power
                            # Stockfish to find the best defensive resource.
                            elif mate_val is not None and mate_val < 0:
                                _fp_time = clock_aware_move_time(
                                    opponent_rating, STOCKFISH_TIME,
                                    _remaining_after_pred, _my_inc, _moves_left,
                                )
                                logger.info(f"[{game_id}] Prediction: forced mate against us (mate in {abs(mate_val)}) — choosing defensive move at full power (fp_time={_fp_time}ms)")
                                move = (
                                    _get_full_power_move(stockfish, game_id, _fp_time, restore_elo=_target_elo)
                                    or stockfish.get_best_move_time(MOVETIME_MIN_MS)
                                )
                            # If predicted eval shows we are significantly down, try to recover
                            elif eval_for_bot is not None and eval_for_bot <= -PREDICTION_RECOVER_THRESHOLD:
                                alt_time = clock_aware_move_time(
                                    opponent_rating, int(STOCKFISH_TIME * 1.5),
                                    _remaining_after_pred, _my_inc, _moves_left,
                                )
                                _recover_elo = min(_target_elo + PREDICTION_RECOVER_ELO_BOOST, 2850) if _target_elo else None
                                # If the boosted ELO cap reaches or exceeds FULL_STRENGTH_THRESHOLD,
                                # UCI_LimitStrength provides no meaningful restriction at that level —
                                # switch to full-power search instead (same as native-clocks mode).
                                if _recover_elo is None or _recover_elo >= FULL_STRENGTH_THRESHOLD:
                                    logger.info(f"[{game_id}] Prediction shows we're down {eval_for_bot}cp — recovery at full power (recover_elo {_recover_elo} >= {FULL_STRENGTH_THRESHOLD})")
                                    move = (
                                        _get_full_power_move(stockfish, game_id, alt_time, restore_elo=_target_elo)
                                        or predicted_move
                                    )
                                    logger.info(f"[{game_id}] Recovery move chosen at full power (movetime {alt_time}ms): {move}")
                                else:
                                    logger.info(f"[{game_id}] Prediction shows we're down {eval_for_bot}cp — attempting recovery search (+{PREDICTION_RECOVER_ELO_BOOST} ELO boost)")
                                    # Recovery: UCI_LimitStrength stays active but ELO cap is
                                    # temporarily raised by PREDICTION_RECOVER_ELO_BOOST.
                                    # Keeps the game winnable for the opponent while giving
                                    # the bot slightly stronger defensive resources.
                                    try:
                                        stockfish.update_engine_parameters({"UCI_LimitStrength": True, "UCI_Elo": _recover_elo})
                                        move = stockfish.get_best_move_time(alt_time) or predicted_move
                                        logger.info(f"[{game_id}] Recovery move chosen (ELO {_recover_elo}, movetime {alt_time}ms): {move}")
                                    finally:
                                        if _target_elo:
                                            try:
                                                stockfish.update_engine_parameters({"UCI_LimitStrength": True, "UCI_Elo": _target_elo})
                                            except Exception as e:
                                                logger.debug(f"Could not restore UCI_Elo to {_target_elo}: {e}")
                            else:
                                move = predicted_move or stockfish.get_best_move_time(move_time)

                            logger.debug(f"[{game_id}] Movetime mode: {move_time}ms (UCI_LimitStrength active)")

                        elif wtime_ms and btime_ms:
                            # Cap the clock values sent to Stockfish on the very first
                            # move.  Lichess aborts the game if no move is made within
                            # ~30 seconds, but with large remaining time (e.g. 20 min)
                            # Stockfish may allocate several minutes for move 1.
                            _FIRST_MOVE_CAP_MS = 15_000
                            _effective_wtime = wtime_ms
                            _effective_btime = btime_ms
                            # Bot's first move: white (empty stack) or black (stack has 1 = opponent's move).
                            # Lichess aborts after ~30s with no move, but Stockfish may
                            # allocate minutes on move 1 with large remaining time.
                            _bot_first_move = (
                                (bot_is_white and len(board.move_stack) == 0) or
                                (not bot_is_white and len(board.move_stack) == 1)
                            )
                            if _bot_first_move:
                                if bot_is_white and wtime_ms > _FIRST_MOVE_CAP_MS:
                                    _effective_wtime = _FIRST_MOVE_CAP_MS
                                    logger.info(f"[{game_id}] First move as white — capping wtime {wtime_ms}→{_FIRST_MOVE_CAP_MS}ms to avoid abort")
                                elif not bot_is_white and btime_ms > _FIRST_MOVE_CAP_MS:
                                    _effective_btime = _FIRST_MOVE_CAP_MS
                                    logger.info(f"[{game_id}] First move as black — capping btime {btime_ms}→{_FIRST_MOVE_CAP_MS}ms to avoid abort")

                            predicted_move, mate_val, pred_cp = get_move_prediction(
                                stockfish, game_id,
                                wtime=_effective_wtime, btime=_effective_btime,
                                winc=winc_ms, binc=binc_ms,
                                prediction_depth=PREDICTION_DEPTH,
                            )

                            # UCI 'score cp' is always from the side-to-move
                            # perspective — which is always the bot here.
                            eval_for_bot = pred_cp

                            if mate_val is not None and mate_val > 0:
                                move = predicted_move or _get_best_move_with_clocks(
                                    stockfish, _effective_wtime, _effective_btime, winc_ms, binc_ms
                                )
                                logger.info(f"[{game_id}] Following mating sequence (mate in {mate_val})")
                            elif mate_val is not None and mate_val < 0:
                                logger.info(f"[{game_id}] Prediction: forced mate against us (mate in {abs(mate_val)}) — choosing defensive move")
                                move = _get_best_move_with_clocks(
                                    stockfish, _effective_wtime, _effective_btime, winc_ms, binc_ms
                                )
                            elif eval_for_bot is not None and eval_for_bot <= -PREDICTION_RECOVER_THRESHOLD:
                                logger.info(f"[{game_id}] Prediction shows we're down {eval_for_bot}cp — attempting recovery search (native clocks)")
                                move = _get_best_move_with_clocks(
                                    stockfish, _effective_wtime, _effective_btime, winc_ms, binc_ms
                                )
                                logger.info(f"[{game_id}] Recovery move chosen: {move}")
                            else:
                                move = predicted_move or _get_best_move_with_clocks(
                                    stockfish, _effective_wtime, _effective_btime, winc_ms, binc_ms
                                )

                            logger.debug(
                                f"[{game_id}] Native clock mode — "
                                f"w:{wtime_ms}ms b:{btime_ms}ms inc:{winc_ms}/{binc_ms}ms"
                            )

                        else:
                            # No clock data — fall back to base movetime (no clock cap)
                            move_time = calculate_move_time(opponent_rating, STOCKFISH_TIME)
                            move = stockfish.get_best_move_time(move_time)
                            logger.debug(f"[{game_id}] No clock data, movetime fallback: {move_time}ms")

                        # Cache eval for draw offer decisions — free from the search info line above
                        last_eval_cp = _get_last_eval_cp(stockfish)

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
                                except (ApiError, ResponseError) as api_err:
                                    # berserk wraps RemoteDisconnected/connection errors as ApiError
                                    err_str = str(api_err).lower()
                                    if "not your turn" in err_str or "game already over" in err_str:
                                        raise  # Not a network error — let outer handler deal with it
                                    if "connection" in err_str or "remote" in err_str or "aborted" in err_str:
                                        if attempt < max_retries - 1:
                                            logger.warning(f"[{game_id}] Network error while making move (attempt {attempt + 1}/{max_retries}): {api_err}")
                                            time.sleep(retry_delay)
                                            retry_delay *= 2
                                        else:
                                            logger.error(f"[{game_id}] Failed to make move after {max_retries} attempts: {api_err}")
                                            logger.info(f"[{game_id}] Game interrupted due to persistent connection issues")
                                            raise
                                    else:
                                        raise  # Non-network API error — let outer handler deal with it
                        else:
                            logger.warning(f"[{game_id}] Stockfish returned no move")

                    except (ConnectionError, Timeout, ChunkedEncodingError, ProtocolError, RequestException) as e:
                        # Network errors that couldn't be resolved after retries
                        logger.warning(f"[{game_id}] Network error while making move: {e}")
                        logger.info(f"[{game_id}] Game interrupted due to connection issues")
                        break
                    except (ApiError, ResponseError) as e:
                        # Handle API-specific errors (connection-related ones were already retried above)
                        error_str = str(e).lower()
                        if "not your turn" in error_str or "game already over" in error_str:
                            # Race condition: engine finished computing after game ended (abort/flag)
                            logger.info(f"[{game_id}] Game ended while making move (race condition)")
                        elif "connection" in error_str or "remote" in error_str or "aborted" in error_str:
                            # Exhausted retries from the inner loop
                            logger.warning(f"[{game_id}] Network error while making move: {e}")
                            logger.info(f"[{game_id}] Game interrupted due to connection issues")
                        else:
                            logger.error(f"[{game_id}] API error while making move: {e}")
                        break
                    except StockfishException as e:
                        logger.error(f"Stockfish error in game {game_id}: {e}")
                        break
                
                # If stream ends normally, exit
                break
                
            except _GameStuck:
                # Watchdog confirmed the game is over — just exit the thread
                break
            except Exception as e:
                status = _http_status(e)
                if _is_network_error(e):
                    logger.warning(f"[{game_id}] Stream connection lost: {e}. Reconnecting in 5s...")
                    time.sleep(5)
                elif status in _GATEWAY_ERRORS:
                    logger.warning(f"[{game_id}] Lichess API error {status}. Reconnecting in 5s...")
                    time.sleep(5)
                elif status == 429:
                    # Lichess asks for a full minute of silence after a 429.
                    logger.warning(f"[{game_id}] Rate limited on the game stream. Reconnecting in 60s...")
                    time.sleep(60)
                else:
                    logger.error(f"[{game_id}] Unexpected stream error: {e}", exc_info=True)
                    break
                continue

    except Exception as e:
        logger.error(f"Game {game_id} crashed: {e}", exc_info=True)

    finally:
        if _claim_victory_timer is not None:
            _claim_victory_timer.cancel()
        if _no_first_move_timer is not None:
            _no_first_move_timer.cancel()
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

# Seconds the event loop may go without reading a line or trying to reconnect
# before the process gives up and exits. The loop does one or the other at
# least once a minute even while Lichess is unreachable, so this much silence
# means the loop itself is stuck.
STALL_EXIT_AFTER = 300


class StreamMonitor:
    """Remembers when Lichess last sent a line and when the event loop last moved."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._last_line: Optional[float] = None
        self._last_progress = clock()

    def line_received(self):
        self._last_line = self._last_progress = self._clock()
        healthcheck.beat()

    def progress(self):
        """The event loop is running, whether or not Lichess can be reached."""
        self._last_progress = self._clock()

    def alive(self, max_silence: float = 30) -> bool:
        """True while lines keep arriving; Lichess sends one at least every 7 seconds."""
        return self._last_line is not None and self._clock() - self._last_line <= max_silence

    def stalled_for(self) -> float:
        return self._clock() - self._last_progress


def watch_event_loop(monitor: StreamMonitor, limit: float = STALL_EXIT_AFTER,
                     interval: float = 15, exit_process=os._exit):
    """End the process when the event loop stops moving, so its supervisor starts a fresh one.

    A lost connection is not a stall: the loop notices it through the read
    timeout and reconnects by itself. This is for the cases it cannot get out
    of, a handler that never returns or a read that hangs despite the timeout.
    """
    while not shutdown_requested:
        _pause(interval)
        stalled = monitor.stalled_for()
        if stalled > limit and not shutdown_requested:
            logger.critical(f"The event loop has not moved for {stalled:.0f}s, exiting to be restarted")
            logging.shutdown()
            exit_process(1)
            return


def stream_events(session: requests.Session, base_url: str = LICHESS_URL):
    """Yield every line of the account's event stream: an event, or None for a keep-alive.

    Lichess writes an empty line every 7 seconds while it has nothing to
    report. berserk's own iterator drops those lines, yet they are the only
    sign that an idle stream is still connected, so the stream is read here.
    """
    try:
        response = session.get(
            f"{base_url}/api/stream/event",
            stream=True,
            headers={"Accept": "application/x-ndjson"},
        )
    except RequestException as e:
        raise ApiError(e) from e

    with response:
        if not response.ok:
            raise ResponseError(response)
        for line in response.iter_lines():
            yield json.loads(line) if line else None


def _pause(seconds: float):
    """Wait, but return at once when the bot is shutting down."""
    _shutdown_event.wait(seconds)


def run_event_loop(session: requests.Session, state: "BotState", base_url: str = LICHESS_URL):
    """Follow the event stream until shutdown, reopening it whenever it ends or fails."""
    while not shutdown_requested:
        state.stream.progress()
        try:
            logger.info("Connecting to event stream...")
            for event in stream_events(session, base_url):
                state.stream.line_received()
                if shutdown_requested:
                    return
                if event is None:
                    continue

                try:
                    handle_event(event, state)
                except Exception as e:
                    logger.error(f"Event processing error: {e}", exc_info=True)

            logger.warning("Event stream ended unexpectedly. Reconnecting in 10s...")
            delay = 10
        except Exception as e:
            delay = _event_stream_retry_delay(e)

        _pause(delay)


@dataclass
class BotState:
    """What the event loop, the challenge loop and the game threads share."""
    client: berserk.Client
    username: str
    tracker: ChallengeTracker
    # One thread per game being played, keyed by game id.
    active_games: Dict[str, threading.Thread] = field(default_factory=dict)
    games_lock: threading.Lock = field(default_factory=threading.Lock)
    # The outgoing challenge still waiting for an answer: {id, opponent, sent_at}, or empty.
    pending_challenge: Dict[str, Any] = field(default_factory=dict)
    # Set to wake the challenge loop before its current wait runs out.
    retry_event: threading.Event = field(default_factory=threading.Event)
    # Incoming challenges the bot has accepted whose game has not started yet,
    # by challenge id with the time of acceptance. Each one holds a game slot.
    accepted_challenges: Dict[str, float] = field(default_factory=dict)
    stream: "StreamMonitor" = field(default_factory=lambda: StreamMonitor())


# How long an accepted challenge may take to show up as a game before its slot
# is given back. Lichess starts the game at once; this only covers an accept
# that was lost on the way.
ACCEPTED_CHALLENGE_TTL = 30


def free_game_slots(state: BotState) -> int:
    """Game slots not taken by a running game or by an accepted challenge."""
    now = time.monotonic()
    with state.games_lock:
        for cid in [c for c, at in state.accepted_challenges.items() if now - at > ACCEPTED_CHALLENGE_TTL]:
            del state.accepted_challenges[cid]
        running = sum(1 for t in state.active_games.values() if t.is_alive())
        return MAX_CONCURRENT_GAMES - running - len(state.accepted_challenges)


def cancel_pending_challenge(state: BotState, why: str):
    """Withdraw the outgoing challenge, so that it cannot turn into a game later.

    Lichess stops showing a real-time challenge after 20 seconds, but a bot
    that queued its id can still accept it much later, when this bot may have
    no slot left for the game.
    """
    challenge_id = state.pending_challenge.get("id")
    if not challenge_id:
        return
    opponent = state.pending_challenge.get("opponent", "unknown")
    state.pending_challenge.clear()
    try:
        state.client.challenges.cancel(challenge_id)
        logger.info(f"Canceled challenge {challenge_id} to {opponent}: {why}")
    except Exception as e:
        logger.debug(f"Could not cancel challenge {challenge_id}: {e}")


def challenge_loop(state: BotState):
    """Background thread that challenges bots whenever the bot is idle.

    Uses an event-based wait so the loop reacts immediately when a challenge
    is declined or canceled instead of sleeping through the full interval.
    """
    logger.info("Challenge loop started")
    ACCEPT_TIMEOUT = 90   # seconds to wait for opponent to accept
    RETRY_DELAY   = 30   # seconds to wait after a decline before trying again

    # Exponential backoff state for HTTP 429 responses
    RATE_LIMIT_BASE  = 300   # initial backoff: 5 minutes
    RATE_LIMIT_MAX   = 3600  # maximum backoff: 60 minutes
    rate_limit_backoff = RATE_LIMIT_BASE  # current backoff duration (reset after success)
    stream_down = False  # so the outage is logged once, not on every pass

    pending_challenge = state.pending_challenge
    retry_event = state.retry_event

    while not shutdown_requested:
        try:
            free_slots = free_game_slots(state)

            if not ENABLE_AUTO_CHALLENGE or free_slots <= 0:
                if free_slots <= 0:
                    logger.debug(f"Skipping challenge: all {MAX_CONCURRENT_GAMES} game slot(s) are taken")
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
                    cancel_pending_challenge(state, f"no answer after {elapsed:.0f}s")
                    retry_event.wait(timeout=RETRY_DELAY)
                    retry_event.clear()

            # ── Without the event stream a challenge would go unanswered ─────
            if not state.stream.alive():
                # An accepted challenge is announced on the event stream. With
                # the stream down the game would start and never get a move.
                if not stream_down:
                    logger.info("Event stream is down — not challenging until it is back")
                    stream_down = True
                retry_event.clear()
                retry_event.wait(timeout=CHALLENGE_CHECK_INTERVAL)
                retry_event.clear()
                continue
            stream_down = False

            # ── The bot's own limits ─────────────────────────────────────────
            limit_wait = state.tracker.seconds_until_free()
            if limit_wait > 0:
                last_hour, last_day = state.tracker.counts()
                logger.info(
                    f"Challenge limit reached ({last_hour}/{state.tracker.max_per_hour} this hour, "
                    f"{last_day}/{state.tracker.max_per_day} in 24 hours) — "
                    f"next challenge in {limit_wait / 60:.0f} min"
                )
                retry_event.clear()
                retry_event.wait(timeout=limit_wait)
                retry_event.clear()
                continue

            # ── Send a new challenge ─────────────────────────────────────────
            logger.info("Looking for a bot to challenge...")
            try:
                challenge = try_challenge_random_bot(state.client, state.username, state.tracker)
            except RateLimitError as e:
                if e.retry_after:
                    # Lichess said when the limit ends; asking sooner is pointless.
                    wait = e.retry_after + 60
                else:
                    wait = rate_limit_backoff
                    rate_limit_backoff = min(rate_limit_backoff * 2, RATE_LIMIT_MAX)
                logger.warning(
                    f"Rate limited by Lichess API (HTTP 429) — backing off for "
                    f"{wait // 60}m {wait % 60}s before next attempt"
                )
                retry_event.clear()
                retry_event.wait(timeout=wait)
                retry_event.clear()
                continue

            # Successful challenge attempt — reset backoff
            rate_limit_backoff = RATE_LIMIT_BASE

            if challenge:
                challenge_id, opponent = challenge
                with state.games_lock:
                    already_playing = challenge_id in state.active_games
                if already_playing:
                    # Accepted before this thread got here; the game has the challenge's id.
                    continue
                pending_challenge["id"] = challenge_id
                pending_challenge["opponent"] = opponent
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


def _event_stream_retry_delay(exc: BaseException) -> int:
    """Log why the event stream stopped and return the seconds to wait before reopening it."""
    status = _http_status(exc)
    if _is_network_error(exc):
        logger.warning(f"Event stream connection lost: {exc}. Reconnecting in 10s...")
        return 10
    if status in _GATEWAY_ERRORS:
        logger.warning(f"Lichess API error {status}. Reconnecting in 15s...")
        return 15
    if status == 429:
        # Lichess asks for a full minute of silence after a 429.
        logger.warning("Rate limited by Lichess (429). Backing off for 60s...")
        return 60
    if status is not None:
        logger.error(f"API error: {exc}. Reconnecting in 30s...")
        return 30
    logger.error(f"Main loop error: {exc}", exc_info=True)
    return 10


class TimeoutHTTPAdapter(requests.adapters.HTTPAdapter):
    """HTTPAdapter that gives every request a timeout unless the caller set one.

    requests hands the adapter ``timeout=None`` whenever the caller gave none,
    so the key is always present: it has to be tested for None. ``setdefault``
    never fires here and leaves every request, streams included, without a
    timeout, and a read on a silently dropped connection then blocks forever.
    """
    def __init__(self, *args, timeout=None, **kwargs):
        self.timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self.timeout
        return super().send(request, **kwargs)


# (connect, read) in seconds. Lichess writes an empty keep-alive line every
# 7 seconds on the event stream and on game streams, so 30 seconds without a
# byte means the connection is gone, not idle.
HTTP_TIMEOUT = (10, 30)


def abort_stale_games(client: berserk.Client):
    """Abort games left over from a previous run that never got going.

    A game with fewer than two moves can still be aborted at no cost. Anything
    further along is left alone: Lichess announces every game in progress when
    the event stream opens, and the game is picked up from there.
    """
    try:
        ongoing = client.games.get_ongoing()
        if ongoing:
            logger.info(f"Found {len(ongoing)} ongoing game(s) from previous session")
            for game in ongoing:
                gid = game.get("gameId") or game.get("id", "")
                status = game.get("status", {})
                status_name = status.get("name", status) if isinstance(status, dict) else str(status)
                opponent = game.get("opponent", {})
                opp_name = opponent.get("username", "?")

                if status_name in _TERMINAL_STATUSES:
                    logger.info(f"  [{gid}] Already finished ({status_name}), skipping")
                    continue

                try:
                    full = client.games.export(gid)
                    moves = full.get("moves", "")
                    move_count = len(moves.split()) if moves else 0

                    if move_count < 2:
                        try:
                            client.bots.abort_game(gid)
                            logger.info(f"  [{gid}] Aborted stuck game vs {opp_name} ({move_count} moves)")
                        except Exception as abort_err:
                            logger.debug(f"  [{gid}] Abort failed ({abort_err}), will resume normally")
                    else:
                        logger.info(f"  [{gid}] In-progress game vs {opp_name} ({move_count} moves), will resume via event stream")
                except Exception as e:
                    logger.debug(f"  [{gid}] Could not check game details: {e}")
    except Exception as e:
        logger.warning(f"Could not check ongoing games: {e}")


def _answer_challenge(answer, challenge_id: str, **kwargs) -> bool:
    """Accept or decline a challenge; False when Lichess did not take the answer."""
    try:
        answer(challenge_id, **kwargs)
        return True
    except ResponseError as e:
        if _http_status(e) == 404:
            logger.debug(f"Challenge {challenge_id} no longer exists")
        else:
            logger.warning(f"Could not answer challenge {challenge_id}: {e}")
    except ApiError as e:
        logger.warning(f"Could not answer challenge {challenge_id}: {e}")
    return False


def handle_event(event: Dict[str, Any], state: BotState):
    """Act on one event from the account's event stream."""
    client = state.client
    pending_challenge = state.pending_challenge
    retry_event = state.retry_event
    kind = event["type"]

    if kind == "challenge":
        challenge = event["challenge"]
        cid = challenge["id"]

        dest_user = challenge.get("destUser", {})
        dest_username = dest_user.get("name", dest_user.get("id", "")).lower()

        # Only incoming challenges (where we are the destination) need an answer
        if dest_username == state.username.lower():
            if not should_accept_challenge(challenge):
                _answer_challenge(client.bots.decline_challenge, cid)
            elif free_game_slots(state) <= 0:
                # Accepting would start a game that has to be aborted at once.
                logger.info(f"Declining challenge {cid}: all {MAX_CONCURRENT_GAMES} game slot(s) are taken")
                _answer_challenge(client.bots.decline_challenge, cid, reason="later")
            elif _answer_challenge(client.bots.accept_challenge, cid):
                with state.games_lock:
                    state.accepted_challenges[cid] = time.monotonic()
                if pending_challenge and free_game_slots(state) <= 0:
                    cancel_pending_challenge(state, "the last game slot went to an incoming challenge")
        else:
            # Outgoing challenge — update opponent name in pending tracker
            logger.debug(f"Outgoing challenge to {dest_username}: {cid}")
            if pending_challenge.get("id") == cid:
                pending_challenge["opponent"] = dest_username

    elif kind == "challengeDeclined":
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
        retry_timer = threading.Timer(30, retry_event.set)
        retry_timer.daemon = True
        retry_timer.start()

    elif kind == "challengeCanceled":
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

    elif kind == "gameStart":
        game_id = event["game"]["id"]
        over_limit = False

        with state.games_lock:
            # Forget threads that have ended, so their slots are free again
            dead = [gid for gid, t in state.active_games.items() if not t.is_alive()]
            for gid in dead:
                del state.active_games[gid]

            # A game carries the id of the challenge it came from.
            state.accepted_challenges.pop(game_id, None)

            if game_id in state.active_games:
                # Lichess announces every game in progress each time the event
                # stream opens, so after a reconnect this arrives for games
                # that already have a thread. Starting again would put two
                # engines on one game, and counting it against the limit
                # would abort or resign a game the bot is in the middle of.
                logger.debug(f"Game {game_id} is already being played")
                return

            if len(state.active_games) >= MAX_CONCURRENT_GAMES:
                over_limit = True
            else:
                # Register the thread before clearing pending_challenge or
                # waking the challenge loop, so the loop's count of active
                # games already includes this one.
                thread = threading.Thread(
                    target=play_game,
                    args=(client, game_id, state.username),
                    daemon=True,
                )
                state.active_games[game_id] = thread

        if over_limit:
            logger.warning(f"Concurrent game limit ({MAX_CONCURRENT_GAMES}) reached, cannot start game {game_id}")
            try:
                client.bots.abort_game(game_id)
            except Exception:
                try:
                    client.bots.resign_game(game_id)
                except Exception as e:
                    logger.debug(f"Could not abort or resign {game_id}: {e}")
            return

        thread.start()

        # A game carries the id of the challenge it came from, so this tells
        # the bot's own challenge being accepted from any other game starting.
        if pending_challenge.get("id") == game_id:
            logger.info(f"Challenge to {pending_challenge.get('opponent', 'unknown')} accepted — game {game_id} started")
            pending_challenge.clear()
        retry_event.set()

        logger.info(f"Game {game_id} started")

    elif kind == "gameFinish":
        game_id = event["game"]["id"]
        with state.games_lock:
            if game_id in state.active_games:
                # Clean up finished game thread
                state.active_games[game_id].join(timeout=1)
                del state.active_games[game_id]
        logger.info(f"Game {game_id} finished — looking for next challenge...")
        retry_event.set()  # wake challenge loop immediately when game ends


def main():
    install_signal_handlers()

    session = berserk.TokenSession(TOKEN)
    adapter = TimeoutHTTPAdapter(timeout=HTTP_TIMEOUT)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
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

    abort_stale_games(client)

    state = BotState(
        client=client,
        username=bot_username,
        tracker=ChallengeTracker(MAX_CHALLENGES_PER_HOUR, MAX_CHALLENGES_PER_DAY),
    )
    global _running_state
    _running_state = state

    # Start challenge loop in background thread
    challenge_thread = threading.Thread(target=challenge_loop, args=(state,), daemon=True)
    challenge_thread.start()
    logger.info("Background challenge thread started")

    threading.Thread(target=watch_event_loop, args=(state.stream,), daemon=True).start()

    run_event_loop(session, state)

    logger.info("Shutting down bot")


if __name__ == "__main__":
    main()
