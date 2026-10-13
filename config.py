import os
import shutil
import logging
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN environment variable not set")

# Configure logging for this module
logger = logging.getLogger(__name__)

# Auto-install/update Stockfish if AUTO_UPDATE_STOCKFISH is enabled (default: True)
AUTO_UPDATE_STOCKFISH = os.getenv("AUTO_UPDATE_STOCKFISH", "true").lower() in ("true", "1", "yes")

def find_stockfish_path():
    """Find or install Stockfish binary."""
    # First, check environment variable
    env_path = os.getenv("STOCKFISH_PATH")
    if env_path and os.path.isfile(env_path):
        logger.info(f"Using Stockfish from STOCKFISH_PATH: {env_path}")
        return env_path
    
    # If auto-update is enabled, ensure latest version is installed
    if AUTO_UPDATE_STOCKFISH:
        try:
            from stockfish_updater import ensure_stockfish_installed
            logger.info("Checking Stockfish installation...")
            return ensure_stockfish_installed(auto_update=True)
        except Exception as e:
            logger.warning(f"Stockfish auto-update failed: {e}")
            logger.info("Falling back to manual detection...")
    
    # Fallback: check if stockfish is in PATH
    path_stockfish = shutil.which("stockfish")
    if path_stockfish:
        return path_stockfish
    
    # Check common installation paths
    common_paths = [
        "/usr/local/bin/stockfish",
        "/usr/bin/stockfish",
        "/usr/games/stockfish",
        "/snap/bin/stockfish",
        "./stockfish",
        "../stockfish",
    ]
    
    for path in common_paths:
        if os.path.isfile(path):
            return path
    
    raise FileNotFoundError(
        "Stockfish not found. Please install it:\n"
        "  Run: ./scripts/install_stockfish.sh\n"
        "  Or download from: https://github.com/official-stockfish/Stockfish/releases\n"
        "  Or set STOCKFISH_PATH environment variable"
    )

STOCKFISH_PATH = find_stockfish_path()

# Stockfish time per move (ms) — used for weak opponents and fallback (no clock data)
STOCKFISH_TIME = int(os.getenv("STOCKFISH_TIME", "3000"))

# Clock-aware movetime safety settings
# MOVETIME_CLOCK_SAFETY: fraction of (remaining/moves_left + inc) to use as hard cap
# Prevents outoftime by ensuring bot never overspends its clock budget per move.
MOVETIME_CLOCK_SAFETY = float(os.getenv("MOVETIME_CLOCK_SAFETY", "0.8"))
# MOVETIME_MIN_MS: floor for calculated movetime — never think less than this
MOVETIME_MIN_MS = int(os.getenv("MOVETIME_MIN_MS", "50"))
# MOVETIME_ESTIMATED_MOVES: baseline moves-to-go estimate for clock budget calculation
MOVETIME_ESTIMATED_MOVES = int(os.getenv("MOVETIME_ESTIMATED_MOVES", "40"))
# MOVETIME_MIN_MOVES_LEFT: minimum moves-to-go used in division to avoid over-spending late in game
MOVETIME_MIN_MOVES_LEFT = int(os.getenv("MOVETIME_MIN_MOVES_LEFT", "10"))

UCI_OPTIONS: Dict[str, Any] = {
    "Threads": int(os.getenv("SF_THREADS", "4")),
    "Hash": int(os.getenv("SF_HASH", "2048")),
    "UCI_LimitStrength": False,  # Managed dynamically by init_stockfish() — do not set here
    "Move Overhead": int(os.getenv("SF_MOVE_OVERHEAD", "30")),  # Note: space in key name (ms)
    "Ponder": False,
}

# Syzygy tablebases: auto-configure if the directory exists and contains tablebase files.
# Override with SF_SYZYGY_PATH env var to point to a custom location.
_syzygy_path = os.getenv("SF_SYZYGY_PATH", "./syzygy")
if os.path.isdir(_syzygy_path) and any(
    f.endswith((".rtbw", ".rtbz")) for f in os.listdir(_syzygy_path)
):
    UCI_OPTIONS["SyzygyPath"] = _syzygy_path
    logger.info(f"Syzygy tablebases enabled: {_syzygy_path}")
else:
    logger.debug(f"Syzygy tablebases not found at {_syzygy_path} (no .rtbw/.rtbz files)")

# Move Prediction Configuration
# Enable to see Stockfish's analysis of best continuation (principal variation)
ENABLE_MOVE_PREDICTION = os.getenv("ENABLE_MOVE_PREDICTION", "true").lower() in ("true", "1", "yes")
PREDICTION_DEPTH = int(os.getenv("PREDICTION_DEPTH", "10"))  # Number of moves to predict ahead

# When prediction is active and the predicted evaluation for the bot is worse
# than this threshold (in centipawns), attempt an alternative (recovery) move.
PREDICTION_RECOVER_THRESHOLD = int(os.getenv("PREDICTION_RECOVER_THRESHOLD", "400"))
# ELO boost applied to UCI_LimitStrength during recovery search.
# Keeps the game winnable for the opponent while giving the bot a slightly
# stronger defensive resource than its normal play level.
PREDICTION_RECOVER_ELO_BOOST = int(os.getenv("PREDICTION_RECOVER_ELO_BOOST", "200"))

ACCEPT_CHALLENGES = True

# Rating range of the challengers the bot accepts, at the speed of the challenge.
# 1320 is the lowest rating Stockfish's strength limit can be set to.
MIN_RATING = int(os.getenv("MIN_RATING", "1320"))
MAX_RATING = int(os.getenv("MAX_RATING", "2800"))

# Speeds the bot plays, fastest first, and the ones it accepts challenges at
SPEEDS = ("bullet", "blitz", "rapid", "classical")
TIME_CONTROL = [
    speed.strip().lower()
    for speed in os.getenv("TIME_CONTROL", ",".join(SPEEDS)).split(",")
    if speed.strip()
]
_unknown_speeds = [speed for speed in TIME_CONTROL if speed not in SPEEDS]
if _unknown_speeds:
    raise ValueError(
        f"TIME_CONTROL names unknown speeds: {', '.join(_unknown_speeds)}. "
        f"Choose from: {', '.join(SPEEDS)}"
    )

# Dynamic strength: the engine is limited to the opponent's level
DYNAMIC_STRENGTH = os.getenv("DYNAMIC_STRENGTH", "true").lower() in ("true", "1", "yes")

# Three tiers by the opponent's rating:
# 1. below LIMIT_STRENGTH_THRESHOLD: Stockfish's strength limit (UCI_LimitStrength)
#    at opponent + STRENGTH_ADVANTAGE, 40 % of STOCKFISH_TIME per move
# 2. from there to FULL_STRENGTH_THRESHOLD: the same limit, 40-95 % of STOCKFISH_TIME
# 3. at or above FULL_STRENGTH_THRESHOLD: full strength, searched on the game clock
#
# Limited games get a fixed time per move so that the bot answers quickly; on
# the game clock Stockfish takes tens of seconds over an early move.

LIMIT_STRENGTH_THRESHOLD = int(os.getenv("LIMIT_STRENGTH_THRESHOLD", "1800"))
FULL_STRENGTH_THRESHOLD = int(os.getenv("FULL_STRENGTH_THRESHOLD", "2800"))

# ELO bonus: UCI_Elo = opponent_rating + STRENGTH_ADVANTAGE
# Applied for ALL opponents below FULL_STRENGTH_THRESHOLD
STRENGTH_ADVANTAGE = int(os.getenv("STRENGTH_ADVANTAGE", "100"))  # e.g. 1500 → ~1600; 2000 → ~2100

# ─────────────────────────────────────────────
# CHALLENGE CONFIGURATION
# ─────────────────────────────────────────────

# Enable automatic challenging of other bots
ENABLE_AUTO_CHALLENGE = os.getenv("ENABLE_AUTO_CHALLENGE", "true").lower() in ("true", "1", "yes")

# Maximum number of challenges to create per hour
MAX_CHALLENGES_PER_HOUR = int(os.getenv("MAX_CHALLENGES_PER_HOUR", "5"))

# Maximum number of challenges to create in any 24 hours. Lichess allows an
# account 200 a day and answers the rest with HTTP 429 until its window ends,
# so this has to stay below 200.
MAX_CHALLENGES_PER_DAY = int(os.getenv("MAX_CHALLENGES_PER_DAY", "180"))

# ELO limits for challenging bots
CHALLENGE_MIN_RATING = int(os.getenv("CHALLENGE_MIN_RATING", "1500"))
CHALLENGE_MAX_RATING = int(os.getenv("CHALLENGE_MAX_RATING", "2900"))

# Time controls to use when challenging (random selection)
CHALLENGE_TIME_CONTROLS = [
    {"limit": 60, "increment": 0},    # 1+0 bullet
    {"limit": 60, "increment": 1},    # 1+1 bullet
    {"limit": 120, "increment": 1},   # 2+1 bullet
    {"limit": 180, "increment": 0},   # 3+0 blitz
    {"limit": 180, "increment": 2},   # 3+2 blitz
    {"limit": 300, "increment": 0},   # 5+0 blitz
    {"limit": 300, "increment": 3},   # 5+3 blitz
    {"limit": 600, "increment": 0},   # 10+0 rapid
    {"limit": 600, "increment": 5},   # 10+5 rapid
    {"limit": 900, "increment": 10},  # 15+10 rapid
    {"limit": 1200, "increment": 10}, # 20+10 classical
    {"limit": 1800, "increment": 0},  # 30+0 classical
]

# Challenge check interval (seconds) - how often to check if we should challenge
CHALLENGE_CHECK_INTERVAL = int(os.getenv("CHALLENGE_CHECK_INTERVAL", "60"))  # 1 minute

# Seconds a game stream may be silent before the bot asks Lichess about the
# game. A game that has ended closes its thread; a game under way is left alone
# however long the opponent thinks.
GAME_WATCHDOG_INTERVAL = int(os.getenv("GAME_WATCHDOG_INTERVAL", "60"))  # 1 minute

# Seconds a game may go without both sides having made their first move before
# the bot aborts it. Until then an abort costs neither side anything.
GAME_WATCHDOG_ABORT_TIMEOUT = int(os.getenv("GAME_WATCHDOG_ABORT_TIMEOUT", "600"))  # 10 minutes

# Maximum number of concurrent games the bot will play simultaneously.
MAX_CONCURRENT_GAMES = int(os.getenv("MAX_CONCURRENT_GAMES", "2"))
