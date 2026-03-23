"""English compatibility wrappers for the shared rhyme-key helpers."""

from langtools.rhyme_keys import (
    IPA_VOWELS,
    compute_rhyme_key,
    rhyme_key_final_sound,
    rhyme_key_penultimate_sound,
)

__all__ = [
    "IPA_VOWELS",
    "compute_rhyme_key",
    "rhyme_key_final_sound",
    "rhyme_key_penultimate_sound",
]
