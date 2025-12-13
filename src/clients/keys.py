#!/usr/bin/python3
"""Centralized API key management for all clients."""

import os
import logging
from typing import Optional

import constants

# Configure logging
logger = logging.getLogger(__name__)


def load_key(key_name: str, required: bool = False) -> Optional[str]:
    """Load API key from file.

    Args:
        key_name: Name of the key file without extension (e.g., 'openai', 'google', 'anthropic')
        required: If True, raises RuntimeError when key is missing

    Returns:
        API key string or None if not found (when required=False)

    Raises:
        RuntimeError: If required=True and key file is not found

    Example:
        # Graceful degradation
        api_key = load_key('openai', required=False)
        if not api_key:
            logger.warning("OpenAI key not available, some features disabled")

        # Fail fast
        api_key = load_key('anthropic', required=True)
    """
    key_path = os.path.join(constants.KEY_DIR, f"{key_name}.key")

    try:
        with open(key_path) as f:
            key = f.read().strip()
            if key:
                logger.debug(f"Loaded API key from {key_path}")
                return key
            else:
                logger.warning(f"API key file {key_path} is empty")
                if required:
                    raise RuntimeError(f"API key file {key_path} is empty")
                return None
    except FileNotFoundError:
        logger.warning(f"API key file not found at {key_path}")
        if required:
            raise RuntimeError(
                f"API key file not found at {key_path}. "
                f"Please create this file with your {key_name} API key."
            )
        return None
    except Exception as e:
        logger.error(f"Error loading API key from {key_path}: {e}")
        if required:
            raise RuntimeError(f"Error loading API key from {key_path}: {e}")
        return None
