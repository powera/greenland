#!/usr/bin/python3

"""Tests for sanitize_lithuanian_word and the alphabet it is built on.

Moved here from audiotools.audio_utils: sanitizing a Lithuanian word is
orthography, not audio, even though the audio CLIs are what use it for
filenames.
"""

from langtools.lt.letters import LETTERS_UPPER
from langtools.lt.utils import LITHUANIAN_CHARS, sanitize_lithuanian_word


def test_charset_is_derived_from_the_alphabet() -> None:
    """LITHUANIAN_CHARS must not drift from the canonical alphabet."""
    assert LITHUANIAN_CHARS == "".join(LETTERS_UPPER).lower()


def test_every_lithuanian_letter_survives() -> None:
    """A word made of the whole alphabet passes through unchanged."""
    alphabet = "".join(LETTERS_UPPER).lower()
    assert sanitize_lithuanian_word(alphabet) == alphabet


def test_lowercases_and_keeps_diacritics() -> None:
    assert sanitize_lithuanian_word("Ąžuolas") == "ąžuolas"


def test_spaces_become_underscores() -> None:
    """Multi-word phrases stay a single filename."""
    assert sanitize_lithuanian_word("labas rytas") == "labas_rytas"


def test_strips_unsafe_characters() -> None:
    assert sanitize_lithuanian_word("kava!!!") == "kava"
    assert sanitize_lithuanian_word("a/b:c") == "abc"


def test_keeps_hyphen_and_underscore() -> None:
    assert sanitize_lithuanian_word("bala-bala_ba") == "bala-bala_ba"


def test_rejects_nothing_left() -> None:
    assert sanitize_lithuanian_word("???") == ""
    assert sanitize_lithuanian_word("   ") == ""


def test_rejects_overlong_names() -> None:
    """A filename over 100 characters is refused rather than truncated."""
    assert sanitize_lithuanian_word("a" * 100) == "a" * 100
    assert sanitize_lithuanian_word("a" * 101) == ""
