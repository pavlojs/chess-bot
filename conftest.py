"""
Environment for the test run, set before any test module imports the bot.

The bot reads its settings at import time. Left alone it would look for a new
Stockfish release, and install it, when the tests are merely collected, and it
refuses to start without a token.
"""

import os

os.environ.setdefault("TOKEN", "test_token_for_testing")
os.environ["AUTO_UPDATE_STOCKFISH"] = "false"
