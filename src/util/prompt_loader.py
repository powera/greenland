#!/usr/bin/python3

"""Utility for loading prompt context files."""

import logging
import os
from pathlib import Path
from typing import Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

import constants

# Legacy prompts are stored within the wordfreq module
LEGACY_PROMPTS_DIR = Path(constants.SRC_DIR) / "wordfreq" / "prompts"

# New prompts are stored at the repo root
NEW_PROMPTS_DIR = Path(constants.SRC_DIR).parent / "prompts"

# Cache for loaded prompts to avoid redundant file reads
_prompt_cache: Dict[str, str] = {}


# Placeholder a classification context file carries in place of a hand-written
# subtype list. Expanded from storage.models.guid_prefixes, which is the single
# source of truth for what subtypes exist; see _expand_subtype_list.
SUBTYPE_LIST_PLACEHOLDER = "{subtype_list}"


def _expand_subtype_list(prompt_text: str, subtype: Optional[str]) -> str:
    """Substitute the generated subtype bullet list into a context file.

    Only files that opt in by carrying :data:`SUBTYPE_LIST_PLACEHOLDER` are
    touched, and only when ``subtype`` names a POS type that has subtypes, so
    every other prompt loads byte-for-byte as before.

    The list is generated rather than written out because the classification
    schema's enum is already generated from the same table: a hand-maintained
    copy in the prompt drifts, and had -- it offered subtypes with no GUID
    prefix while omitting most of the real ones.
    """
    if subtype is None or SUBTYPE_LIST_PLACEHOLDER not in prompt_text:
        return prompt_text

    # Imported here, not at module scope: storage.models pulls in SQLAlchemy and
    # the whole model registry, which a prompt read should not require.
    from storage.models.guid_prefixes import SUBTYPE_DEFS, render_subtype_list

    if subtype not in SUBTYPE_DEFS:
        return prompt_text
    return prompt_text.replace(SUBTYPE_LIST_PLACEHOLDER, render_subtype_list(subtype))


def _resolve_prompt_path(category: str, prompt_type: str, filename: str) -> Path:
    """
    Resolve the path to a prompt file, checking both new and legacy locations.

    Args:
        category: If "wordfreq", use legacy location. Otherwise use new location.
        prompt_type: Type of prompt (e.g., 'french_noun_forms' or 'language_forms/french/noun')
        filename: Name of the file (e.g., 'prompt.txt', 'context.txt', or subtype like 'noun.txt')

    Returns:
        Path to the prompt file
    """
    if category == "wordfreq":
        # Legacy location: src/wordfreq/prompts/{prompt_type}/{filename}
        return LEGACY_PROMPTS_DIR / prompt_type / filename
    else:
        # New location: prompts/{category}/{prompt_type}/{filename}
        return NEW_PROMPTS_DIR / category / prompt_type / filename


def get_context(category: str, prompt_type: str, subtype: Optional[str] = None) -> str:
    """
    Load a context prompt from a text file.

    Args:
        category: Category for prompts. 'wordfreq' uses legacy location (src/wordfreq/prompts/),
                  other categories use new location (prompts/{category}/)
        prompt_type: Type of prompt (e.g., 'definitions', 'french/noun')
        subtype: Optional subtype for further categorization (e.g., 'noun' for POS subtypes)

    Returns:
        The prompt text as a string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    # Determine the filename
    filename = f"{subtype}.txt" if subtype else "context.txt"

    # Resolve the file path based on category
    file_path = _resolve_prompt_path(category, prompt_type, filename)

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

        prompt_text = _expand_subtype_list(prompt_text, subtype)

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
        category: Category for prompts. 'wordfreq' uses legacy location (src/wordfreq/prompts/),
                  other categories use new location (prompts/{category}/)
        prompt_type: Type of prompt (e.g., 'definitions', 'french/noun')
        subtype: Optional subtype for further categorization (e.g., 'noun' for POS subtypes)

    Returns:
        The prompt template text as a string with placeholders like {word}, {definition}, etc.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
    """
    # Determine the filename
    filename = f"{subtype}.txt" if subtype else "prompt.txt"

    # Resolve the file path based on category
    file_path = _resolve_prompt_path(category, prompt_type, filename)

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
