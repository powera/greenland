"""Tests for Spanish syllable and written-accent helpers."""

import unittest

from langtools.es.orthography import (
    accent_nucleus,
    has_written_accent,
    needs_written_accent,
    respell_with_stress,
    strip_accents,
    stressed_nucleus,
    syllable_nuclei,
)


def _stressed_vowel(word: str) -> str:
    index = stressed_nucleus(word)
    assert index is not None, word
    return word[index]


class TestSyllableNuclei(unittest.TestCase):
    def test_simple_words(self) -> None:
        self.assertEqual(syllable_nuclei("casa"), [1, 3])
        self.assertEqual(syllable_nuclei("hablar"), [1, 4])
        self.assertEqual(syllable_nuclei("joven"), [1, 3])

    def test_diphthong_counts_as_one_syllable(self) -> None:
        # vue-lo, cau-sa, viu-da
        self.assertEqual(len(syllable_nuclei("vuelo")), 2)
        self.assertEqual(len(syllable_nuclei("causa")), 2)
        self.assertEqual(len(syllable_nuclei("viuda")), 2)

    def test_diphthong_nucleus_is_the_strong_vowel(self) -> None:
        self.assertEqual("vuelo"[syllable_nuclei("vuelo")[0]], "e")
        self.assertEqual("causa"[syllable_nuclei("causa")[0]], "a")
        # Two weak vowels: the second one carries the syllable.
        self.assertEqual("viuda"[syllable_nuclei("viuda")[0]], "u")

    def test_two_strong_vowels_split(self) -> None:
        # ca-er, le-er, te-a-tro
        self.assertEqual(len(syllable_nuclei("caer")), 2)
        self.assertEqual(len(syllable_nuclei("leer")), 2)
        self.assertEqual(len(syllable_nuclei("teatro")), 3)

    def test_accented_weak_vowel_breaks_the_diphthong(self) -> None:
        self.assertEqual(len(syllable_nuclei("reír")), 2)
        self.assertEqual(len(syllable_nuclei("país")), 2)
        self.assertEqual(len(syllable_nuclei("continúo")), 4)

    def test_triphthong(self) -> None:
        # es-tu-diáis
        self.assertEqual(len(syllable_nuclei("estudiais")), 3)


class TestStressPlacement(unittest.TestCase):
    def test_written_accent_wins(self) -> None:
        self.assertEqual(_stressed_vowel("común"), "ú")
        self.assertEqual(_stressed_vowel("fácil"), "á")
        self.assertEqual(_stressed_vowel("habló"), "ó")

    def test_words_ending_in_vowel_n_or_s_are_llanas(self) -> None:
        self.assertEqual(stressed_nucleus("casa"), 1)
        self.assertEqual(stressed_nucleus("joven"), 1)
        self.assertEqual(stressed_nucleus("gratis"), 2)

    def test_other_endings_are_agudas(self) -> None:
        self.assertEqual(_stressed_vowel("hablar"), "a")
        self.assertEqual(_stressed_vowel("azul"), "u")
        self.assertEqual(_stressed_vowel("feliz"), "i")

    def test_monosyllables(self) -> None:
        self.assertEqual(stressed_nucleus("gris"), 2)
        self.assertEqual(stressed_nucleus("ve"), 1)

    def test_word_without_vowels(self) -> None:
        self.assertIsNone(stressed_nucleus(""))
        self.assertIsNone(stressed_nucleus("xyz"))


class TestAccentRules(unittest.TestCase):
    def test_esdrujulas_always_take_the_accent(self) -> None:
        self.assertTrue(needs_written_accent("jovenes", 1))
        self.assertTrue(needs_written_accent("levantate", 3))

    def test_llanas_take_it_only_on_a_consonant_ending(self) -> None:
        self.assertFalse(needs_written_accent("casa", 1))
        self.assertTrue(needs_written_accent("facil", 1))

    def test_agudas_take_it_on_a_vowel_n_or_s_ending(self) -> None:
        self.assertTrue(needs_written_accent("hablo", 4))
        self.assertTrue(needs_written_accent("comun", 3))
        self.assertFalse(needs_written_accent("hablar", 4))

    def test_monosyllables_never_take_it(self) -> None:
        self.assertFalse(needs_written_accent("ve", 1))
        self.assertFalse(needs_written_accent("frio", 3))


class TestRespellWithStress(unittest.TestCase):
    """Adding a syllable moves the spelling, not the stress."""

    def test_plurals(self) -> None:
        cases = [
            ("joven", "es", "jóvenes"),
            ("común", "es", "comunes"),
            ("francés", "es", "franceses"),
            ("alemán", "es", "alemanes"),
            ("fácil", "es", "fáciles"),
            ("azul", "es", "azules"),
        ]
        for word, suffix, expected in cases:
            index = stressed_nucleus(word)
            assert index is not None
            self.assertEqual(respell_with_stress(strip_accents(word) + suffix, index), expected)

    def test_enclitics(self) -> None:
        cases = [
            ("levanta", "te", "levántate"),
            ("levantando", "se", "levantándose"),
            ("levantar", "se", "levantarse"),
            ("pon", "te", "ponte"),
            ("ve", "te", "vete"),
        ]
        for word, clitic, expected in cases:
            index = stressed_nucleus(word)
            assert index is not None
            self.assertEqual(respell_with_stress(strip_accents(word) + clitic, index), expected)

    def test_stressed_weak_vowel_gets_the_hiatus_accent(self) -> None:
        # vestid + os: the i must stay its own syllable.
        index = stressed_nucleus("vestid")
        assert index is not None
        self.assertEqual(respell_with_stress("vesti" + "os", index), "vestíos")


class TestAccentUtilities(unittest.TestCase):
    def test_strip_accents(self) -> None:
        self.assertEqual(strip_accents("común"), "comun")
        self.assertEqual(strip_accents("español"), "español")
        self.assertEqual(strip_accents("pingüino"), "pingüino")

    def test_has_written_accent(self) -> None:
        self.assertTrue(has_written_accent("común"))
        self.assertFalse(has_written_accent("comun"))
        self.assertFalse(has_written_accent("pingüino"))

    def test_accent_nucleus(self) -> None:
        self.assertEqual(accent_nucleus("jovenes", 1), "jóvenes")
        self.assertEqual(accent_nucleus("jóvenes", 1), "jóvenes")


if __name__ == "__main__":
    unittest.main()
