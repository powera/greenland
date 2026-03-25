"""IPA rhyme-key helpers for supported languages."""

from __future__ import annotations

from typing import Optional

from langtools.rhyme_languages import RHYME_KEY_LANGUAGES

# Broad IPA vowel inventory covering the currently supported rhyme-key languages.
IPA_VOWELS: frozenset[str] = frozenset("iɪeɛæɑɒɔʊuʌəɜɚɝaoɐœøyʏɨɯɒ̃ɛ̃ɔ̃ɑ̃ɶɤɞɘɵɜ̃ɒ̈ʉɒ̈")

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
    """Return the index of the last IPA vowel character in *ipa*."""
    for index in range(len(ipa) - 1, -1, -1):
        if ipa[index] in IPA_VOWELS:
            return index
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


def rhyme_key_final_sound(rhyme_key: str) -> str:
    """Extract the final phoneme from a rhyme key for tier-1 navigation."""
    if not rhyme_key:
        return ""

    last = rhyme_key[-1]
    if last == "ː" and len(rhyme_key) >= 2:
        return rhyme_key[-2:]

    if last in IPA_VOWELS:
        index = len(rhyme_key) - 1
        while index > 0 and rhyme_key[index - 1] in IPA_VOWELS:
            index -= 1
        return rhyme_key[index:]

    return last


def rhyme_key_penultimate_sound(rhyme_key: str) -> str:
    """Extract the penultimate phoneme segment for tier-2 navigation."""
    if not rhyme_key:
        return ""

    final_sound = rhyme_key_final_sound(rhyme_key)
    prefix = rhyme_key[: len(rhyme_key) - len(final_sound)]
    if not prefix:
        return ""

    last_of_prefix = prefix[-1]
    if last_of_prefix == "ː" and len(prefix) >= 2:
        return prefix[-2:]

    if last_of_prefix in IPA_VOWELS:
        index = len(prefix) - 1
        while index > 0 and prefix[index - 1] in IPA_VOWELS:
            index -= 1
        return prefix[index:]

    return last_of_prefix
