"""Compatibility exports for missing-word candidate validation."""

from reports.missing_words import is_valid_frequency_candidate


def is_valid_word(word: str) -> bool:
    """Compatibility name for the missing-word report's candidate filter."""
    return is_valid_frequency_candidate(word)


__all__ = ["is_valid_word"]
