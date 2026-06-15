"""Tests for rule-based French adjective inflection."""

import unittest

from langtools.fr.inflection import build_adjective_forms


class TestFrenchAdjectiveForms(unittest.TestCase):
    def test_regular_consonant(self) -> None:
        self.assertEqual(
            build_adjective_forms("petit"),
            {
                "singular_m": "petit",
                "singular_f": "petite",
                "plural_m": "petits",
                "plural_f": "petites",
            },
        )

    def test_grand(self) -> None:
        forms = build_adjective_forms("grand")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "grande")
        self.assertEqual(forms["plural_f"], "grandes")

    def test_e_invariant_gender(self) -> None:
        self.assertEqual(
            build_adjective_forms("rouge"),
            {
                "singular_m": "rouge",
                "singular_f": "rouge",
                "plural_m": "rouges",
                "plural_f": "rouges",
            },
        )

    def test_eux_to_euse(self) -> None:
        forms = build_adjective_forms("heureux")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "heureuse")
        self.assertEqual(forms["plural_m"], "heureux")
        self.assertEqual(forms["plural_f"], "heureuses")

    def test_er_to_ere(self) -> None:
        forms = build_adjective_forms("cher")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "chère")
        self.assertEqual(forms["plural_f"], "chères")

    def test_f_to_ve(self) -> None:
        forms = build_adjective_forms("vif")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "vive")
        self.assertEqual(forms["plural_f"], "vives")

    def test_vowel_final(self) -> None:
        forms = build_adjective_forms("joli")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "jolie")
        self.assertEqual(forms["plural_f"], "jolies")

    def test_irregular_table(self) -> None:
        self.assertEqual(
            build_adjective_forms("beau"),
            {
                "singular_m": "beau",
                "singular_f": "belle",
                "plural_m": "beaux",
                "plural_f": "belles",
            },
        )

    def test_uncertain_ending_returns_none(self) -> None:
        # -l feminines are unpredictable (national/nationale vs nul/nulle).
        self.assertIsNone(build_adjective_forms("national"))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(build_adjective_forms(""))


if __name__ == "__main__":
    unittest.main()
