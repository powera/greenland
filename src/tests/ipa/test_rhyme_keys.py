"""Tests for IPA rhyme-key helpers."""

from ipa.rhyme_keys import (
    compute_rhyme_key,
    rhyme_key_final_sound,
    rhyme_key_penultimate_sound,
    rhyme_keys_available,
)


def test_compute_rhyme_key_for_english_word() -> None:
    assert compute_rhyme_key("/rɛd/", language_code="en") == "ɛd"


def test_compute_rhyme_key_for_french_without_stress_marker() -> None:
    assert compute_rhyme_key("/ʃɑ̃te/", language_code="fr") == "e"


def test_rhyme_key_sound_helpers() -> None:
    assert rhyme_key_final_sound("ɛd") == "d"
    assert rhyme_key_penultimate_sound("ɛd") == "ɛ"


def test_rhyme_key_language_support() -> None:
    assert rhyme_keys_available("en") is True
    assert rhyme_keys_available("de") is False
