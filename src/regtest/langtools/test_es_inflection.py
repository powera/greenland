"""Tests for rule-based Spanish adjective inflection."""

import unittest

from langtools.es.inflection import build_adjective_forms


class TestSpanishAdjectiveForms(unittest.TestCase):
    def test_o_adjective_four_forms(self) -> None:
        self.assertEqual(
            build_adjective_forms("rojo"),
            {
                "singular_m": "rojo",
                "singular_f": "roja",
                "plural_m": "rojos",
                "plural_f": "rojas",
            },
        )

    def test_e_adjective_invariant_gender(self) -> None:
        self.assertEqual(
            build_adjective_forms("grande"),
            {
                "singular_m": "grande",
                "singular_f": "grande",
                "plural_m": "grandes",
                "plural_f": "grandes",
            },
        )

    def test_a_adjective_invariant_gender(self) -> None:
        forms = build_adjective_forms("belga")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "belga")
        self.assertEqual(forms["plural_m"], "belgas")

    def test_z_adjective_plural_ces(self) -> None:
        forms = build_adjective_forms("feliz")
        assert forms is not None
        self.assertEqual(forms["plural_m"], "felices")
        self.assertEqual(forms["plural_f"], "felices")

    def test_uncertain_consonant_returns_none(self) -> None:
        # -l adjectives (azul, español, ...) are left to the LLM.
        self.assertIsNone(build_adjective_forms("azul"))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(build_adjective_forms(""))


if __name__ == "__main__":
    unittest.main()
