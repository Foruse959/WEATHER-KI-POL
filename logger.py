"""
Structured logging for weather bot.
"""

import os
import sys
import logging
from datetime import datetime, timezone


def setup_logger(name: str = 'weather_bot', log_file: str = None) -> logging.Logger:
    """Create a logger with both console and file output."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    from config import Config
    level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    fmt = logging.Formatter(
        '[%(asctime)s] [%(levelname)-5s] %(message)s',
        datefmt='%H:%M:%S'
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler
    log_path = log_file or Config.LOG_FILE
    try:
        os.makedirs(os.path.dirname(log_path) if os.path.dirname(log_path) else '.', exist_ok=True)
        fh = logging.FileHandler(log_path, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)-5s] %(name)s — %(message)s'
        ))
        logger.addHandler(fh)
    except Exception as e:
        logger.warning(f"Could not create log file {log_path}: {e}")

    return logger


# Global logger instance
log = setup_logger()
