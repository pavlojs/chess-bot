# Configuration for Axiom Chess Bot

import os
from typing import Dict, Any

# Lichess API token (get from https://lichess.org/account/oauth/token or environment variable)
# Only require TOKEN when actually running the bot, not for imports/tests
_token = os.getenv('TOKEN')
if not _token and 'pytest' not in os.sys.modules and 'bot' in os.sys.argv:
    raise ValueError(
        "TOKEN environment variable not set. "
        "Get your token from https://lichess.org/account/oauth/token"
    )
TOKEN = _token or "test_token_for_imports"

# Stockfish settings
import os
STOCKFISH_PATH: str = "/usr/local/bin/stockfish"  # Path to Stockfish binary
STOCKFISH_DEPTH: int = 15  # Search depth for Stockfish
STOCKFISH_TIME: int = 1100  # Time per move in milliseconds
STOCKFISH_TIMEOUT: int = 5  # Timeout in seconds for Stockfish operations

# Playstyle modifications
# UCI options for Stockfish (modify these to change playstyle)
UCI_OPTIONS: Dict[str, Any] = {
    "Skill Level": 18,  # 0-20, higher is stronger
    "Threads": 6,  # Number of CPU threads
    "Hash": 1024,  # Hash size in MB
    "UCI_LimitStrength": False,  # Set to True to limit strength
    "UCI_Elo": 1600,  # Target Elo when UCI_LimitStrength is True (800-2850)
    "Move Overhead": 30,  # Time overhead in ms per move
    # "Slow Mover": 84,  # Time management factor (10-1000)
    "Contempt": 20,  # Draw avoidance in centipawns
    # "SyzygyPath": "./syzygy",  # Path to Syzygy tablebases
}

# Bot behavior
ACCEPT_CHALLENGES: bool = True
MIN_RATING: int = 0  # Minimum opponent rating to accept
MAX_RATING: int = 2800  # Maximum opponent rating to accept
TIME_CONTROL: list = ["bullet", "blitz", "rapid", "classical"]  # Accepted time controls

# Dynamic bot strength based on opponent
DYNAMIC_STRENGTH: bool = True  # Adapt bot strength to opponent rating
STRENGTH_ADVANTAGE: int = 100  # Bot Elo advantage over opponent (in rating points)