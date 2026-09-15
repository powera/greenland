"""Spanish stress and written-accent helpers.

Spanish spelling marks stress with a written accent only when the stress
falls somewhere other than the default position, so adding or removing a
syllable can add or remove the accent mark without moving the stress:
``joven`` → ``jóvenes``, ``común`` → ``comunes``, ``levanta`` → ``levántate``.

Both the conjugator (enclitic pronouns) and the adjective inflector (plural
formation) need the same primitives, so they live here.
"""

from typing import List, Optional

PLAIN_VOWELS = "aeiou"
ACCENTED_VOWELS = "áéíóú"
STRONG_VOWELS = "aeoáéó"
WEAK_VOWELS = "iuü"

_PLAIN_TO_ACCENTED = dict(zip(PLAIN_VOWELS, ACCENTED_VOWELS))
_ACCENTED_TO_PLAIN = dict(zip(ACCENTED_VOWELS, PLAIN_VOWELS))

# A written accent on a weak vowel breaks the diphthong, so í/ú always form
# their own syllable nucleus (``re-ír``, ``pa-ís``).
_ALL_VOWELS = PLAIN_VOWELS + ACCENTED_VOWELS + "ü"

# Final letters after which an unaccented word is stressed on the
# next-to-last syllable.
_LLANA_FINALS = PLAIN_VOWELS + "ns"


def is_vowel(char: str) -> bool:
    """True if ``char`` is a Spanish vowel (accented or not)."""
    return char in _ALL_VOWELS


def has_written_accent(word: str) -> bool:
    """True if ``word`` carries a written accent on any vowel."""
    return any(char in ACCENTED_VOWELS for char in word)


def strip_accents(word: str) -> str:
    """Remove every written accent from ``word`` (ñ and ü are preserved)."""
    return "".join(_ACCENTED_TO_PLAIN.get(char, char) for char in word)


def syllable_nuclei(word: str) -> List[int]:
    """Return the index of the stress-bearing vowel of each syllable.

    Vowels in contact normally share a syllable (``vue-lo``, ``cau-sa``); two
    strong vowels form a hiatus and split (``ca-er``, ``le-er``), as does an
    accented weak vowel (``re-ír``).  The index returned for a diphthong is
    the vowel that would take a written accent.
    """
    nuclei: List[int] = []
    index = 0
    length = len(word)
    while index < length:
        if not is_vowel(word[index]):
            index += 1
            continue

        # Collect the run of vowels starting here, splitting it into syllables.
        group_start = index
        while index < length and is_vowel(word[index]):
            index += 1
        group = word[group_start:index]

        position = 0
        while position < len(group):
            vowel = group[position]
            # An accented weak vowel is always its own nucleus.
            if vowel in "íú":
                nuclei.append(group_start + position)
                position += 1
                continue
            if position + 1 < len(group):
                following = group[position + 1]
                strong_pair = vowel in STRONG_VOWELS and following in STRONG_VOWELS
                accented_weak = following in "íú"
                if not strong_pair and not accented_weak:
                    # Diphthong: the nucleus is the strong vowel, or the second
                    # vowel when both are weak (``cui-dar``, ``viu-da``).
                    if vowel in STRONG_VOWELS:
                        nuclei.append(group_start + position)
                    else:
                        nuclei.append(group_start + position + 1)
                    position += 2
                    # A triphthong takes a trailing weak vowel along.
                    if position < len(group) and group[position] in "iu":
                        position += 1
                    continue
            nuclei.append(group_start + position)
            position += 1

    return nuclei


def stressed_nucleus(word: str) -> Optional[int]:
    """Return the index of the stressed vowel, or ``None`` for a vowel-less word.

    A written accent wins; otherwise the default rules apply — words ending in
    a vowel, ``n`` or ``s`` are stressed on the next-to-last syllable, all
    others on the last.
    """
    nuclei = syllable_nuclei(word)
    if not nuclei:
        return None

    for index in nuclei:
        if word[index] in ACCENTED_VOWELS:
            return index

    if len(nuclei) == 1:
        return nuclei[0]
    if word and word[-1] in _LLANA_FINALS:
        return nuclei[-2]
    return nuclei[-1]


def accent_nucleus(word: str, index: int) -> str:
    """Return ``word`` with a written accent on the vowel at ``index``."""
    vowel = word[index]
    if vowel in ACCENTED_VOWELS:
        return word
    accented = _PLAIN_TO_ACCENTED.get(vowel)
    if accented is None:
        return word
    return word[:index] + accented + word[index + 1 :]


def needs_written_accent(word: str, stressed_index: int) -> bool:
    """True if ``word`` stressed at ``stressed_index`` must be written with an accent."""
    nuclei = syllable_nuclei(word)
    if not nuclei or stressed_index not in nuclei:
        return False
    position_from_end = len(nuclei) - 1 - nuclei.index(stressed_index)
    if position_from_end >= 2:
        # Esdrújula and beyond are always written with an accent.
        return True
    ends_llana = bool(word) and word[-1] in _LLANA_FINALS
    if position_from_end == 1:
        return not ends_llana
    return ends_llana and len(nuclei) > 1


def respell_with_stress(word: str, stressed_index: int) -> str:
    """Write ``word`` (given unaccented) with the accent its stress requires.

    ``stressed_index`` is the position of the stressed vowel, which does not
    move when a suffix or an enclitic pronoun is attached — only the spelling
    does (``joven`` → ``jóvenes``, ``vestid`` → ``vestíos``).
    """
    plain = strip_accents(word)
    if stressed_index >= len(plain) or not is_vowel(plain[stressed_index]):
        return plain

    if stressed_index not in syllable_nuclei(plain):
        # A stressed weak vowel absorbed into a diphthong needs the accent to
        # mark the hiatus: ``vestid`` + ``os`` → ``vestíos``.
        if plain[stressed_index] in "iu":
            return accent_nucleus(plain, stressed_index)
        return plain

    if needs_written_accent(plain, stressed_index):
        return accent_nucleus(plain, stressed_index)
    return plain
