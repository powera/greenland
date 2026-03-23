"""
Rhyme key computation from IPA pronunciations.

A "rhyme key" captures the phonetic material from the nucleus (vowel) of the
last stressed syllable through to the end of the word.  Words that share a
rhyme key rhyme with each other.

Examples (English):
    /kæt/      → "æt"       (cat)
    /bæt/      → "æt"       (bat)
    /ˈrʌnɪŋ/  → "ʌnɪŋ"    (running)
    /əˈweɪ/    → "eɪ"      (away)
    /dɔɡ/      → "ɔɡ"      (dog)

Currently supports English only; the language_code parameter is reserved
for future expansion.
"""

from typing import Optional

# IPA vowel characters found in English transcriptions.
# This includes monophthongs, schwas, and rhotacised vowels.
IPA_VOWELS: frozenset[str] = frozenset("iɪeɛæɑɒɔʊuʌəɜɚɝaoɐœøyʏ")

# Characters to strip from the outside of an IPA string.
_IPA_DELIMITERS: str = "/[]"

# Stress markers (primary and secondary).
_PRIMARY_STRESS: str = "ˈ"
_SECONDARY_STRESS: str = "ˌ"

# Characters that are removed entirely before rhyme-key extraction because
# they do not affect rhyme identity.
_STRIP_CHARS: frozenset[str] = frozenset(
    "\u0361"  # combining double inverted breve (tie bar)
    "\u035c"  # combining double breve below (tie bar)
)


def _clean_ipa(raw: str) -> str:
    """Strip delimiters, tie bars, and surrounding whitespace from an IPA string."""
    cleaned = raw.strip().strip(_IPA_DELIMITERS).strip()
    return "".join(ch for ch in cleaned if ch not in _STRIP_CHARS)


def _find_last_stress(ipa: str) -> Optional[int]:
    """Return the index of the last stress marker, or None if absent."""
    # Prefer primary stress; fall back to secondary.
    idx = ipa.rfind(_PRIMARY_STRESS)
    if idx >= 0:
        return idx
    idx = ipa.rfind(_SECONDARY_STRESS)
    if idx >= 0:
        return idx
    return None


def _find_first_vowel(ipa: str, start: int = 0) -> Optional[int]:
    """Return the index of the first IPA vowel character at or after *start*."""
    for i in range(start, len(ipa)):
        if ipa[i] in IPA_VOWELS:
            return i
    return None


def compute_rhyme_key(ipa: str, language_code: str = "en") -> Optional[str]:
    """Derive a rhyme key from an IPA pronunciation string.

    The rhyme key is the substring from the vowel nucleus of the last
    stressed syllable through to the end of the word.  For monosyllabic
    words (or words without an explicit stress marker) the key is taken
    from the first vowel onward.

    Returns ``None`` when *ipa* is empty or contains no recognisable vowel.
    """
    if not ipa or not ipa.strip():
        return None

    cleaned = _clean_ipa(ipa)
    if not cleaned:
        return None

    stress_idx = _find_last_stress(cleaned)

    if stress_idx is not None:
        # Start scanning for the vowel nucleus after the stress marker.
        vowel_idx = _find_first_vowel(cleaned, stress_idx + 1)
    else:
        # No stress marker → monosyllable; take from first vowel.
        vowel_idx = _find_first_vowel(cleaned)

    if vowel_idx is None:
        return None

    rhyme = cleaned[vowel_idx:]

    # Remove any stray stress markers that ended up inside the rhyme
    # (e.g. from unusual transcriptions with multiple stress marks).
    rhyme = rhyme.replace(_PRIMARY_STRESS, "").replace(_SECONDARY_STRESS, "")

    return rhyme if rhyme else None


def rhyme_key_final_sound(rhyme_key: str) -> str:
    """Extract the final phoneme from a rhyme key for tier-1 navigation.

    For consonant-final keys (e.g. "æt") this returns the last character.
    For vowel-final keys (e.g. "eɪ") this returns the trailing vowel
    cluster (the whole coda-less ending).

    This is a rough grouping aid for the UI, not a phonological analysis.
    """
    if not rhyme_key:
        return ""

    # Walk backwards collecting the final segment.
    # If the last char is a vowel, collect the whole trailing vowel cluster.
    # If the last char is a consonant, return just that consonant.
    last = rhyme_key[-1]

    # Length mark ː attaches to the preceding segment.
    if last == "ː" and len(rhyme_key) >= 2:
        return rhyme_key[-2:]

    if last in IPA_VOWELS:
        # Collect trailing vowel cluster (diphthong/long vowel).
        i = len(rhyme_key) - 1
        while i > 0 and rhyme_key[i - 1] in IPA_VOWELS:
            i -= 1
        return rhyme_key[i:]

    return last


def rhyme_key_penultimate_sound(rhyme_key: str) -> str:
    """Extract the second-to-last phoneme segment for tier-2 navigation.

    Given a rhyme key like "æt", the final sound is "t" and the
    penultimate is "æ".  This returns the vowel nucleus that precedes
    the final consonant(s), which is the main distinguishing feature
    among rhyme keys that share the same ending consonant.
    """
    if not rhyme_key:
        return ""

    final = rhyme_key_final_sound(rhyme_key)
    prefix = rhyme_key[: len(rhyme_key) - len(final)]

    if not prefix:
        # The rhyme key is purely the final sound (e.g., a bare vowel).
        return ""

    # The penultimate segment is the trailing vowel cluster of the prefix
    # (the nucleus), or the last character if it's a consonant.
    last_of_prefix = prefix[-1]

    if last_of_prefix == "ː" and len(prefix) >= 2:
        return prefix[-2:]

    if last_of_prefix in IPA_VOWELS:
        i = len(prefix) - 1
        while i > 0 and prefix[i - 1] in IPA_VOWELS:
            i -= 1
        return prefix[i:]

    return last_of_prefix
