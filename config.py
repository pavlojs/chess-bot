import os
from typing import Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN environment variable not set")

STOCKFISH_PATH = "/usr/local/bin/stockfish"

STOCKFISH_TIME = 1100  # ms per move

UCI_OPTIONS: Dict[str, Any] = {
    "Threads": 4,
    "Hash": 1024,
    "UCI_LimitStrength": False,
    "MoveOverhead": 30,
    "Contempt": 20,
}

ACCEPT_CHALLENGES = True
MIN_RATING = 0
MAX_RATING = 2800
TIME_CONTROL = ["bullet", "blitz", "rapid", "classical"]

DYNAMIC_STRENGTH = True
STRENGTH_ADVANTAGE = 100
