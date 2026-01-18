# Configuration for Lichess Bot

import os

# Lichess API token (get from https://lichess.org/account/oauth/token or environment variable)
TOKEN = os.getenv('TOKEN', "your_lichess_token_here")

# Stockfish settings
import os
STOCKFISH_PATH = "./stockfish/stockfish" if os.path.exists("./stockfish/stockfish") else None  # Use downloaded binary if available
STOCKFISH_DEPTH = 15  # Search depth for Stockfish
STOCKFISH_TIME = 1100  # Time per move in milliseconds

# Playstyle modifications
# UCI options for Stockfish (modify these to change playstyle)
UCI_OPTIONS = {
    "Skill Level": 18,  # 0-20, higher is stronger
    "Threads": 6,  # Number of CPU threads
    "Hash": 1024,  # Hash size in MB
    "UCI_LimitStrength": True,  # Set to True to limit strength
    "UCI_Elo": 1600,  # Target Elo when UCI_LimitStrength is True (800-2850)
    "Move Overhead": 30,  # Time overhead in ms per move
    # "Slow Mover": 84,  # Time management factor (10-1000)
    "Contempt": 20,  # Draw avoidance in centipawns
    "SyzygyPath": "./syzygy",  # Path to Syzygy tablebases
}

# Bot behavior
ACCEPT_CHALLENGES = True
MIN_RATING = 1000  # Minimum opponent rating to accept
MAX_RATING = 2400  # Maximum opponent rating to accept
TIME_CONTROL = ["blitz", "rapid"]  # Accepted time controls