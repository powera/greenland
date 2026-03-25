"""Compatibility wrappers for IPA rhyme-key helpers."""

from ipa.rhyme_keys import (
    IPA_VOWELS,
    RHYME_KEY_LANGUAGES,
    compute_rhyme_key,
    rhyme_key_final_sound,
    rhyme_key_penultimate_sound,
    rhyme_keys_available,
)

__all__ = [
    "RHYME_KEY_LANGUAGES",
    "IPA_VOWELS",
    "rhyme_keys_available",
    "compute_rhyme_key",
    "rhyme_key_final_sound",
    "rhyme_key_penultimate_sound",
]
