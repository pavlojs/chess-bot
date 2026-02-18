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

# Stockfish time per move (ms) - dynamically adjusted based on opponent strength
# Base time for calculation, can be adjusted per opponent
STOCKFISH_TIME = 3000  # Default: 3 seconds per move

UCI_OPTIONS: Dict[str, Any] = {
    "Threads": 4,
    "Hash": 2048,
    "UCI_LimitStrength": False,  # Never use UCI_LimitStrength - it introduces blunders
    "Move Overhead": 30,  # Note: space in key name (ms)
    "Ponder": False,
}

ACCEPT_CHALLENGES = True
MIN_RATING = 1320
MAX_RATING = 2800
TIME_CONTROL = ["bullet", "blitz", "rapid", "classical"]

# Dynamic strength: HYBRID approach for fair games at all levels
# Combines UCI_LimitStrength (for beginners) with time control (for advanced players)
DYNAMIC_STRENGTH = True

# HYBRID SYSTEM THRESHOLDS:
# 1. Below LIMIT_STRENGTH_THRESHOLD: Use UCI_LimitStrength (fair for beginners)
# 2. Between thresholds: Full strength engine, reduced time (no blunders for intermediates)
# 3. Above FULL_STRENGTH_THRESHOLD: MAXIMUM POWER (full time + full strength)

LIMIT_STRENGTH_THRESHOLD = 1800  # Below this: UCI_LimitStrength for fair games
FULL_STRENGTH_THRESHOLD = 2800   # At or above: FULL POWER (no compromises)

# For opponents below LIMIT_STRENGTH_THRESHOLD:
# Bot plays at opponent_rating + STRENGTH_ADVANTAGE using UCI_LimitStrength
STRENGTH_ADVANTAGE = 100  # ELO advantage for weak opponents (e.g., 1500 → bot plays 1600)

# ─────────────────────────────────────────────
# CHALLENGE CONFIGURATION
# ─────────────────────────────────────────────

# Enable automatic challenging of other bots
ENABLE_AUTO_CHALLENGE = os.getenv("ENABLE_AUTO_CHALLENGE", "true").lower() in ("true", "1", "yes")

# Maximum number of games to challenge per hour
MAX_CHALLENGES_PER_HOUR = int(os.getenv("MAX_CHALLENGES_PER_HOUR", "3"))

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
    {"limit": 900, "increment": 10},  # 15+10 classical
    {"limit": 1200, "increment": 10}, # 20+10 classical
    {"limit": 1800, "increment": 0},  # 30+0 classical
]

# Challenge check interval (seconds) - how often to check if we should challenge
CHALLENGE_CHECK_INTERVAL = int(os.getenv("CHALLENGE_CHECK_INTERVAL", "300"))  # 5 minutes
