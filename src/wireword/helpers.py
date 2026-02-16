#!/usr/bin/env python3
"""
Helper functions for WireWord export.

Contains utility functions for formatting, normalization, and text processing
used by the WireWord exporter.
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def extract_conjugation_slot(grammatical_form_key: str) -> Optional[str]:
    """Extract the person/number slot from a WireWord conjugation key.

    Examples:
    - ``1s_present`` -> ``1s``
    - ``3s-m_present`` -> ``3s``
    - ``2p_future`` -> ``2p``
    """
    if "_" not in grammatical_form_key:
        return None

    slot = grammatical_form_key.split("_", 1)[0]
    slot = slot.split("-", 1)[0]
    return slot if slot in {"1s", "2s", "3s", "1p", "2p", "3p"} else None


def normalize_pos_type(pos_type: str) -> str:
    """
    Normalize POS type to match WireWord PartOfSpeech enum.

    Args:
        pos_type: Original POS type

    Returns:
        Normalized POS type
    """
    pos_mappings = {
        "noun": "noun",
        "verb": "verb",
        "adjective": "adjective",
        "adverb": "adverb",
        "pronoun": "pronoun",
        "preposition": "preposition",
        "conjunction": "conjunction",
        "interjection": "interjection",
        "numeral": "numeral",
        "particle": "particle",
    }

    return pos_mappings.get(pos_type.lower(), pos_type)


def convert_to_wireword_grammatical_form_key(grammatical_form: str) -> str:
    """
    Convert database grammatical form key format to WireWord format.

    Converts from database format like "verb/lt_3s_m_present" or "verb/fr_1s_present"
    to WireWord format like "3s-m_present" or "1s_present".

    The key transformations:
    - Remove "verb/{lang}_" prefix
    - Replace underscores between person/number components with hyphens (3s_m -> 3s-m)

    Args:
        grammatical_form: Database grammatical form key (e.g., "verb/lt_3s_m_present")

    Returns:
        WireWord format key (e.g., "3s-m_present")
    """
    # If already in WireWord format (no prefix), return as-is
    if not grammatical_form.startswith("verb/"):
        return grammatical_form

    # Remove "verb/{lang}_" prefix
    # Format: "verb/lt_1s_present" or "verb/fr_3p_future"
    parts = grammatical_form.split("_", 1)  # Split on first underscore only
    if len(parts) < 2:
        return grammatical_form  # Return original if format unexpected

    # parts[0] is "verb/lt" or "verb/fr"
    # parts[1] is "1s_present" or "3s_m_present" or similar
    key_without_prefix = parts[1]

    # Now convert underscores to hyphens in person/number part
    # e.g., "3s_m_present" -> "3s-m_present"
    # The pattern is: {person}{number}_{gender}_{tense}
    # We want hyphens between person/number/gender, but underscore before tense

    # Split by underscore to find components
    components = key_without_prefix.split("_")
    if len(components) == 2:
        # Simple case: "1s_present" or "1p_past"
        return key_without_prefix
    elif len(components) == 3:
        # Has gender: "3s_m_present" -> "3s-m_present"
        person_num = components[0]
        gender = components[1]
        tense = components[2]
        return f"{person_num}-{gender}_{tense}"
    else:
        # Unexpected format, return as-is
        return key_without_prefix


def format_verb_entry(entry: Dict[str, Any], is_last: bool = False) -> str:
    """
    Format a single verb entry with custom JSON formatting.

    Creates a format where:
    - Top-level verb fields are on separate lines with proper indentation
    - Each grammatical form entry is condensed to a single line
    - More vertical spacing between verb entries (like the old format)

    Args:
        entry: Verb entry dictionary
        is_last: Whether this is the last entry in the array

    Returns:
        Formatted string for this verb entry
    """
    lines = []
    lines.append("  {")

    # Determine the keys order - put grammatical_forms last
    keys_order = []
    for key in [
        "guid",
        "base_target",
        "base_english",
        "base_source",
        "corpus",
        "group",
        "level",
        "word_type",
    ]:
        if key in entry:
            keys_order.append(key)

    # Add any other keys except grammatical_forms
    for key in entry:
        if key not in keys_order and key != "grammatical_forms":
            keys_order.append(key)

    # Write the non-grammatical-forms fields
    has_grammatical_forms = "grammatical_forms" in entry
    for i, key in enumerate(keys_order):
        value_json = json.dumps(entry[key], ensure_ascii=False)
        # Add comma unless this is the last key and there are no grammatical_forms
        is_last_key = i == len(keys_order) - 1
        comma = "," if has_grammatical_forms or not is_last_key else ""
        lines.append(f'    "{key}": {value_json}{comma}')

    # Write grammatical_forms with each form on one line
    if has_grammatical_forms:
        lines.append('    "grammatical_forms": {')

        forms = entry["grammatical_forms"]
        form_keys = list(forms.keys())
        for j, form_key in enumerate(form_keys):
            form_value_json = json.dumps(
                forms[form_key], ensure_ascii=False, separators=(", ", ": ")
            )
            comma = "" if j == len(form_keys) - 1 else ","
            lines.append(f'      "{form_key}": {form_value_json}{comma}')

        lines.append("    }")

    # Close the verb entry object
    comma = "" if is_last else ","
    lines.append(f"  }}{comma}")

    return "\n".join(lines) + "\n"


def generate_simple_grammatical_form_label(grammatical_form: str, base_english: str) -> str:
    """
    Generate a simple readable English label for a grammatical form.

    This is a fallback that produces a basic label by cleaning up the
    grammatical form identifier. For production use, English translations
    should be stored in the database.

    Args:
        grammatical_form: The grammatical form identifier
        base_english: The base English word

    Returns:
        Simple readable English label
    """
    # Convert underscores to spaces and remove prefixes
    readable_form = grammatical_form.replace("_", " ").replace("/", " ")
    # Remove common prefixes like "verb lt" or "verb fr"
    for prefix in ["verb lt ", "verb fr ", "verb en ", "noun ", "adjective "]:
        if readable_form.startswith(prefix):
            readable_form = readable_form[len(prefix) :]
            break
    return f"{base_english} ({readable_form})"
