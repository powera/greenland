"""
Centralized logging configuration for the project.

This module provides a consistent logging format across all modules.
Import and call configure_logging() at the start of your script.
"""

import logging


def configure_logging(level: int = logging.INFO, debug: bool = False) -> None:
    """
    Configure logging with a standardized format.

    Args:
        level: Logging level (default: logging.INFO)
        debug: If True, set level to DEBUG
    """
    if debug:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
        force=True,  # Override any existing configuration
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
