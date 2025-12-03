"""Helper functions for working with POS enums."""

import enum
from typing import List, Optional

from wordfreq.storage.models.enums import NounSubtype, VerbSubtype, AdjectiveSubtype, AdverbSubtype


# TODO: de-dupe
VALID_POS_TYPES = {
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "preposition",
    "conjunction",
    "interjection",
    "determiner",
    "article",
    "numeral",
    "auxiliary",
    "modal",
}


def get_subtype_enum(pos_type: str) -> Optional[enum.EnumMeta]:
    """Get the appropriate subtype enum class based on part of speech."""
    pos_type = pos_type.lower()
    if pos_type == "noun":
        return NounSubtype
    elif pos_type == "verb":
        return VerbSubtype
    elif pos_type == "adjective":
        return AdjectiveSubtype
    elif pos_type == "adverb":
        return AdverbSubtype
    return None


def get_subtype_values_for_pos(pos_type: str) -> List[str]:
    """
    Get all possible subtype values for a given part of speech.

    Args:
        pos_type: Part of speech (noun, verb, adjective, adverb)

    Returns:
        List of possible subtype values
    """
    enum_class = get_subtype_enum(pos_type)
    if enum_class:
        return [e.value for e in enum_class]
    return []


def get_all_pos_subtypes() -> List[str]:
    """
    Get all possible POS subtypes for each part of speech.

    Returns:
        List of all subtypes across all POS types
    """
    all_subtypes = set()
    all_subtypes.update(get_subtype_values_for_pos("noun"))
    all_subtypes.update(get_subtype_values_for_pos("verb"))
    all_subtypes.update(get_subtype_values_for_pos("adjective"))
    all_subtypes.update(get_subtype_values_for_pos("adverb"))
    all_subtypes.update(VALID_POS_TYPES)
    return sorted(list(all_subtypes))
