#!/usr/bin/python3

"""Utility for loading prompt context files."""

import os
import logging
from pathlib import Path
from typing import Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

import constants
# Prompts are now stored within the wordfreq module
PROMPTS_DIR = Path(constants.SRC_DIR) / "wordfreq" / "prompts"

# Cache for loaded prompts to avoid redundant file reads
_prompt_cache: Dict[str, str] = {}

def get_context(category: str, prompt_type: str, subtype: Optional[str] = None) -> str:
    """
    Load a context prompt from a text file.

    Args:
        category: Main category (currently only 'wordfreq' is supported)
        prompt_type: Type of prompt (e.g., 'antonym', 'definitions')
        subtype: Optional subtype for further categorization (e.g., 'noun' for POS subtypes)

    Returns:
        The prompt text as a string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    # Only wordfreq category is supported
    assert category == "wordfreq", f"Only 'wordfreq' category is supported, got '{category}'"

    # Determine the file path
    if subtype:
        file_path = PROMPTS_DIR / prompt_type / f"{subtype}.txt"
    else:
        file_path = PROMPTS_DIR / prompt_type / "context.txt"

    # Convert to string for cache key
    cache_key = str(file_path)

    # Return from cache if available
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    # Ensure the file exists
    if not file_path.exists():
        error_msg = f"Prompt file not found: {file_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    # Load the prompt from the file
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            prompt_text = f.read().strip()

        # Cache the result
        _prompt_cache[cache_key] = prompt_text

        return prompt_text
    except Exception as e:
        logger.error(f"Error loading prompt from {file_path}: {e}")
        raise

def get_prompt(category: str, prompt_type: str, subtype: Optional[str] = None) -> str:
    """
    Load a user prompt template from a text file.

    Args:
        category: Main category (currently only 'wordfreq' is supported)
        prompt_type: Type of prompt (e.g., 'definitions', 'chinese_translation')
        subtype: Optional subtype for further categorization (e.g., 'noun' for POS subtypes)

    Returns:
        The prompt template text as a string with placeholders like {word}, {definition}, etc.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    # Only wordfreq category is supported
    assert category == "wordfreq", f"Only 'wordfreq' category is supported, got '{category}'"

    # Determine the file path
    if subtype:
        file_path = PROMPTS_DIR / prompt_type / f"{subtype}.txt"
    else:
        file_path = PROMPTS_DIR / prompt_type / "prompt.txt"

    # Convert to string for cache key
    cache_key = str(file_path)

    # Return from cache if available
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    # Ensure the file exists
    if not file_path.exists():
        error_msg = f"Prompt file not found: {file_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    # Load the prompt from the file
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            prompt_text = f.read().strip()

        # Cache the result
        _prompt_cache[cache_key] = prompt_text

        return prompt_text
    except Exception as e:
        logger.error(f"Error loading prompt from {file_path}: {e}")
        raise
