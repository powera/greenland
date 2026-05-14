"""Shared position-code alphabet for non-Latin script families.

For scripts whose codepoints are not contiguous in canonical alphabet order
(Cyrillic supplementary block, Brahmic varnamala, Thai consonants), each letter
is remapped to a single ASCII character drawn from ``POSITION_ALPHABET``.  The
remapped string compares correctly under SQLite's default binary collation and
reproduces canonical alphabet order.

The alphabet is constructed so a sort key compared after ``.upper()`` produces
the same relative ordering as compared after ``.lower()`` — i.e. case-folding
the whole key (in either direction) never changes how it sorts against any
other key from this alphabet.

Achieving this means every non-letter symbol must sit either strictly *below*
``A`` (0x41) or strictly *above* ``z`` (0x7A).  Anything in the gap
``[ \\ ] ^ _ ``` (0x5B-0x60) would compare above ``A-Z`` but below ``a-z`` and
flip orderings under ``.lower()``.  The alphabet is also strictly monotonic in
ASCII binary order, so direct binary comparison reproduces alphabet order.
"""

from typing import Dict, List

# 56 chars: 27 symbols below 'A', 26 uppercase letters, 3 symbols above 'z'.
# Excludes whitespace, the three quote characters (" ' `), and the chars
# flagged by the user (-, (, ), \, [, ], ^, |).  Notably also excludes _
# because it sits in the 0x5B-0x60 gap between Z and a and would break the
# upper/lower ordering symmetry.
POSITION_ALPHABET: str = "!#$%&*+,./" "0123456789" ":;<=>?@" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "{}~"

assert POSITION_ALPHABET == "".join(
    sorted(POSITION_ALPHABET)
), "POSITION_ALPHABET must be in strict ASCII order"
# Every char must sit outside the 0x5B-0x60 gap, otherwise .lower() would
# reorder it relative to A-Z.
assert all(
    ord(c) < ord("A") or ("A" <= c <= "Z") or ord(c) > ord("z") for c in POSITION_ALPHABET
), "POSITION_ALPHABET must avoid the 0x5B-0x60 gap between Z and a"
# Sanity: applying .upper() then sorting, vs .lower() then sorting, must
# produce the same permutation of the alphabet.
_upper_sorted = sorted(POSITION_ALPHABET, key=str.upper)
_lower_sorted = sorted(POSITION_ALPHABET, key=str.lower)
assert (
    _upper_sorted == _lower_sorted == list(POSITION_ALPHABET)
), "POSITION_ALPHABET ordering must be invariant under .upper()/.lower()"


def build_position_codes(letters: List[str]) -> Dict[str, str]:
    """Map each letter to its single-character position code.

    ``letters[i]`` is mapped to ``POSITION_ALPHABET[i]``.

    Raises ``ValueError`` if the alphabet has more letters than the position
    alphabet can encode (currently 57).
    """
    if len(letters) > len(POSITION_ALPHABET):
        raise ValueError(
            f"alphabet of {len(letters)} letters exceeds POSITION_ALPHABET capacity "
            f"({len(POSITION_ALPHABET)})"
        )
    return {letter: POSITION_ALPHABET[index] for index, letter in enumerate(letters)}
