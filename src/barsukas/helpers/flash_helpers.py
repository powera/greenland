"""Utilities for flash messages with logging."""

import logging
import inspect
from pathlib import Path
from flask import flash

logger = logging.getLogger(__name__)


def flash_and_log(message: str, category: str = "info", log_level: str = None):
    """Flash a message to the user and log it with caller location.

    Args:
        message: The message to flash and log
        category: Flash category ("error", "success", "warning", "info")
        log_level: Optional logging level override. If not provided, maps from category:
                   - "error" -> WARNING
                   - "warning" -> WARNING
                   - "success" -> INFO
                   - "info" -> INFO
    """
    # Flash the message to the user
    flash(message, category)

    # Get caller information
    frame = inspect.currentframe()
    caller_frame = frame.f_back
    caller_filename = caller_frame.f_code.co_filename
    caller_lineno = caller_frame.f_lineno

    # Get just the filename (relative to project if possible)
    caller_file = Path(caller_filename).name
    location = f"{caller_file}:{caller_lineno}"

    # Determine log level if not explicitly provided
    if log_level is None:
        log_level = "WARNING" if category in ("error", "warning") else "INFO"

    # Log the message with location
    log_func = getattr(logger, log_level.lower(), logger.info)
    log_func(f"[{category.upper()}] {location}: {message}")
