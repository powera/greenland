"""Utilities for flash messages with logging."""

import inspect
import logging
import traceback
from pathlib import Path
from typing import Optional

from flask import flash

logger = logging.getLogger(__name__)


def flash_and_log(message: str, category: str = "info", log_level: Optional[str] = None) -> None:
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
    if frame is None:
        return
    caller_frame = frame.f_back
    if caller_frame is None:
        return
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


def log_and_flash_error(e: Exception, context: str) -> None:
    """Flash an error message and log exception with traceback.

    Args:
        e: The exception that was raised
        context: Brief description of what operation failed (e.g., "checking translations")
    """
    # Get traceback info for file/line number
    tb = traceback.extract_tb(e.__traceback__)
    if tb:
        last_frame = tb[-1]
        error_location = f"{last_frame.filename}:{last_frame.lineno}"
        error_msg = f"Error {context}: {str(e)} (at {error_location})"
    else:
        error_msg = f"Error {context}: {str(e)}"

    # Flash to user
    flash(error_msg, "error")

    # Log to console with full traceback
    logger.warning(error_msg, exc_info=True)
