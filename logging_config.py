"""
Centralized logging configuration for Axiom Chess Bot
"""

import logging
import logging.handlers
import os
from pathlib import Path

# The log file is rotated, so the log directory has a ceiling: one file of at
# most LOG_FILE_MAX_MB plus LOG_FILE_BACKUPS older ones (60 MB by default).
LOG_FILE_MAX_MB = int(os.getenv("LOG_FILE_MAX_MB", "10"))
LOG_FILE_BACKUPS = int(os.getenv("LOG_FILE_BACKUPS", "5"))
LOG_FILE_MAX_BYTES = LOG_FILE_MAX_MB * 1024 * 1024


def setup_logger(name: str) -> logging.Logger:
    """
    Setup and return a configured logger.

    The console gets INFO and above. The file ``logs/axiom_bot.log`` gets
    everything from DEBUG up, with the function and line each message came from.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Console handler with INFO level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)

    # File handler with DEBUG level (rotated)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "axiom_bot.log",
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUPS,
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)

    # Add handlers if not already added
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
