"""Tests for langtools.en.rhyme_key — IPA-to-rhyme-key extraction."""

import pytest

from langtools.en.rhyme_key import (
    compute_rhyme_key,
    rhyme_key_final_sound,
    rhyme_key_penultimate_sound,
)

# ---------------------------------------------------------------------------
# compute_rhyme_key
# ---------------------------------------------------------------------------


class TestComputeRhymeKey:
    """Core rhyme key extraction from IPA strings."""

    def test_monosyllable_no_stress(self) -> None:
        # /kæt/ → "æt"
        assert compute_rhyme_key("/kæt/") == "æt"

    def test_monosyllable_with_stress(self) -> None:
        assert compute_rhyme_key("/ˈkæt/") == "æt"

    def test_rhyming_pair(self) -> None:
        # cat and bat should produce the same key
        assert compute_rhyme_key("/kæt/") == compute_rhyme_key("/bæt/")

    def test_polysyllabic_initial_stress(self) -> None:
        # running: /ˈrʌnɪŋ/ → "ʌnɪŋ"
        assert compute_rhyme_key("/ˈrʌnɪŋ/") == "ʌnɪŋ"

    def test_polysyllabic_final_stress(self) -> None:
        # away: /əˈweɪ/ → "eɪ"
        assert compute_rhyme_key("/əˈweɪ/") == "eɪ"

    def test_dog(self) -> None:
        assert compute_rhyme_key("/dɔɡ/") == "ɔɡ"

    def test_brackets(self) -> None:
        # Square bracket notation should also work.
        assert compute_rhyme_key("[kæt]") == "æt"

    def test_no_delimiters(self) -> None:
        assert compute_rhyme_key("kæt") == "æt"

    def test_empty_string(self) -> None:
        assert compute_rhyme_key("") is None

    def test_whitespace_only(self) -> None:
        assert compute_rhyme_key("   ") is None

    def test_no_vowels(self) -> None:
        # Purely consonantal — unlikely but should return None.
        assert compute_rhyme_key("/skt/") is None

    def test_only_vowels(self) -> None:
        assert compute_rhyme_key("/aɪ/") == "aɪ"

    def test_tie_bar_stripped(self) -> None:
        # The tie bar (U+0361) should not affect the result.
        assert compute_rhyme_key("/t͡ʃɪn/") == "ɪn"

    def test_secondary_stress(self) -> None:
        # Falls back to secondary stress marker.
        assert compute_rhyme_key("/ˌʌndərˈstænd/") == "ænd"

    def test_computer(self) -> None:
        # /kəmˈpjuːtər/ → "uːtər"
        assert compute_rhyme_key("/kəmˈpjuːtər/") == "uːtər"

    def test_none_input(self) -> None:
        # Guard: should not crash on None-like empty values.
        assert compute_rhyme_key("") is None


# ---------------------------------------------------------------------------
# rhyme_key_final_sound
# ---------------------------------------------------------------------------


class TestRhymeKeyFinalSound:
    def test_consonant_ending(self) -> None:
        assert rhyme_key_final_sound("æt") == "t"

    def test_vowel_ending(self) -> None:
        assert rhyme_key_final_sound("eɪ") == "eɪ"

    def test_nasal_ending(self) -> None:
        assert rhyme_key_final_sound("ʌnɪŋ") == "ŋ"

    def test_long_vowel_ending(self) -> None:
        assert rhyme_key_final_sound("uː") == "uː"

    def test_empty(self) -> None:
        assert rhyme_key_final_sound("") == ""

    def test_single_consonant(self) -> None:
        assert rhyme_key_final_sound("t") == "t"

    def test_single_vowel(self) -> None:
        assert rhyme_key_final_sound("æ") == "æ"


# ---------------------------------------------------------------------------
# rhyme_key_penultimate_sound
# ---------------------------------------------------------------------------


class TestRhymeKeyPenultimateSound:
    def test_simple_cv(self) -> None:
        # "æt" → final is "t", penultimate is "æ"
        assert rhyme_key_penultimate_sound("æt") == "æ"

    def test_diphthong_then_consonant(self) -> None:
        # "aɪn" → final is "n", penultimate is "aɪ"
        assert rhyme_key_penultimate_sound("aɪn") == "aɪ"

    def test_bare_vowel(self) -> None:
        # "eɪ" → final is "eɪ", no penultimate
        assert rhyme_key_penultimate_sound("eɪ") == ""

    def test_multisyllable(self) -> None:
        # "ʌnɪŋ" → final is "ŋ", penultimate is "ɪ"
        assert rhyme_key_penultimate_sound("ʌnɪŋ") == "ɪ"

    def test_empty(self) -> None:
        assert rhyme_key_penultimate_sound("") == ""
