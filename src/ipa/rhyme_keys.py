"""IPA rhyme-key helpers for supported languages."""

from __future__ import annotations

import unicodedata
from typing import Optional

from langtools.rhyme_languages import RHYME_KEY_LANGUAGES

# Single-codepoint IPA vowel base characters.  Do NOT include multi-codepoint
# sequences here (e.g. ɔ̃ = ɔ + U+0303): Python frozenset iteration would
# split them and accidentally admit bare combining diacritics as "vowels".
# Combining diacritics (Unicode category Mn) are handled separately via
# _is_combining() so that nasal/long vowels are treated as a single nucleus.
IPA_VOWELS: frozenset[str] = frozenset("iɪeɛæɑɒɔʊuʌəɜɚɝaoɐœøyʏɨɯɶɤɞɘɵʉ")

_IPA_DELIMITERS: str = "/[]"
_PRIMARY_STRESS: str = "ˈ"
_SECONDARY_STRESS: str = "ˌ"
_STRIP_CHARS: frozenset[str] = frozenset(
    "\u0361"  # combining double inverted breve (tie bar)
    "\u035c"  # combining double breve below (tie bar)
)


def rhyme_keys_available(language_code: str) -> bool:
    """Return whether rhyme keys are supported for the given language."""
    return language_code in RHYME_KEY_LANGUAGES


def _clean_ipa(raw: str) -> str:
    """Strip delimiters, tie bars, and surrounding whitespace from an IPA string."""
    cleaned = raw.strip().strip(_IPA_DELIMITERS).strip()
    return "".join(character for character in cleaned if character not in _STRIP_CHARS)


def _find_last_stress(ipa: str) -> Optional[int]:
    """Return the index of the last stress marker, or None if absent."""
    primary_index = ipa.rfind(_PRIMARY_STRESS)
    if primary_index >= 0:
        return primary_index

    secondary_index = ipa.rfind(_SECONDARY_STRESS)
    if secondary_index >= 0:
        return secondary_index

    return None


def _find_first_vowel(ipa: str, start: int = 0) -> Optional[int]:
    """Return the index of the first IPA vowel character at or after *start*."""
    for index in range(start, len(ipa)):
        if ipa[index] in IPA_VOWELS:
            return index
    return None


def _find_last_vowel(ipa: str) -> Optional[int]:
    """Return the index of the last IPA vowel nucleus start in *ipa*.

    Skips backwards over combining diacritics (Unicode category Mn) so that
    nasal/modified vowels like ɔ̃ (ɔ + U+0303) are treated as a single nucleus
    whose start index is the base vowel character.
    """
    index = len(ipa) - 1
    while index >= 0:
        if unicodedata.category(ipa[index]) == "Mn":
            index -= 1
            continue
        if ipa[index] in IPA_VOWELS:
            return index
        index -= 1
    return None


def compute_rhyme_key(ipa: str, language_code: str = "en") -> Optional[str]:
    """Derive a rhyme key from an IPA pronunciation string.

    For languages with lexical stress marked in IPA (`en`, `lt`, `es`), the key
    runs from the last stressed vowel nucleus to the end of the word. French
    typically omits lexical stress, so its fallback is the last vowel nucleus.
    """
    if not ipa or not ipa.strip() or not rhyme_keys_available(language_code):
        return None

    cleaned = _clean_ipa(ipa)
    if not cleaned:
        return None

    stress_index = _find_last_stress(cleaned)
    if stress_index is not None:
        vowel_index = _find_first_vowel(cleaned, stress_index + 1)
    elif language_code == "fr":
        vowel_index = _find_last_vowel(cleaned)
    else:
        vowel_index = _find_first_vowel(cleaned)

    if vowel_index is None:
        return None

    rhyme = cleaned[vowel_index:]
    rhyme = rhyme.replace(_PRIMARY_STRESS, "").replace(_SECONDARY_STRESS, "")
    return rhyme if rhyme else None


def _last_nucleus_start(s: str) -> int:
    """Return the start index of the last vowel nucleus (base vowel + combining marks).

    Walks backwards skipping combining diacritics, then back to include any
    leading combining marks that belong to the same nucleus.  Returns 0 if the
    whole string is one nucleus.
    """
    index = len(s) - 1
    # Skip trailing combining marks
    while index >= 0 and unicodedata.category(s[index]) == "Mn":
        index -= 1
    # index is now on the base vowel (or a consonant if no vowel found)
    return index


def _ends_with_vowel_nucleus(s: str) -> bool:
    """Return True if *s* ends with a vowel nucleus (base vowel + optional combining marks)."""
    idx = _last_nucleus_start(s)
    return idx >= 0 and s[idx] in IPA_VOWELS


def rhyme_key_final_sound(rhyme_key: str) -> str:
    """Extract the final phoneme from a rhyme key for tier-1 navigation."""
    if not rhyme_key:
        return ""

    # Handle long-vowel marker
    if rhyme_key.endswith("ː") and len(rhyme_key) >= 2:
        return rhyme_key[-2:]

    if _ends_with_vowel_nucleus(rhyme_key):
        # Walk back to collect the full trailing vowel sequence
        # (multiple adjacent vowels count as one diphthong/nucleus group)
        index = _last_nucleus_start(rhyme_key)
        # Include any preceding base vowels that form a diphthong
        while index > 0:
            prev = _last_nucleus_start(rhyme_key[:index])
            if prev >= 0 and rhyme_key[prev] in IPA_VOWELS:
                index = prev
            else:
                break
        return rhyme_key[index:]

    # Consonant ending: return just the last character (+ any combining marks)
    index = _last_nucleus_start(rhyme_key)
    return rhyme_key[index:]


def rhyme_key_penultimate_sound(rhyme_key: str) -> str:
    """Extract the penultimate phoneme segment for tier-2 navigation."""
    if not rhyme_key:
        return ""

    final_sound = rhyme_key_final_sound(rhyme_key)
    prefix = rhyme_key[: len(rhyme_key) - len(final_sound)]
    if not prefix:
        return ""

    if prefix.endswith("ː") and len(prefix) >= 2:
        return prefix[-2:]

    if _ends_with_vowel_nucleus(prefix):
        index = _last_nucleus_start(prefix)
        while index > 0:
            prev = _last_nucleus_start(prefix[:index])
            if prev >= 0 and prefix[prev] in IPA_VOWELS:
                index = prev
            else:
                break
        return prefix[index:]

    index = _last_nucleus_start(prefix)
    return prefix[index:]
