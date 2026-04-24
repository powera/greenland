"""Tests for Italian noun/adjective derivative generation."""

import unittest

from langtools.it.derivative_forms import derive_adjective_forms, derive_noun_forms


class TestItalianNounDerivatives(unittest.TestCase):
    def test_regular_noun_plural(self) -> None:
        self.assertEqual(derive_noun_forms("gatto"), {"singular": "gatto", "plural": "gatti"})

    def test_irregular_noun_plural(self) -> None:
        self.assertEqual(derive_noun_forms("uomo"), {"singular": "uomo", "plural": "uomini"})

    def test_explicit_plural_fact(self) -> None:
        self.assertEqual(
            derive_noun_forms("braccio", explicit_plural="braccia"),
            {"singular": "braccio", "plural": "braccia"},
        )


class TestItalianAdjectiveDerivatives(unittest.TestCase):
    def test_o_ending_adjective(self) -> None:
        self.assertEqual(
            derive_adjective_forms("italiano"),
            {
                "singular_m": "italiano",
                "singular_f": "italiana",
                "plural_m": "italiani",
                "plural_f": "italiane",
            },
        )

    def test_e_ending_adjective(self) -> None:
        self.assertEqual(
            derive_adjective_forms("grande"),
            {
                "singular_m": "grande",
                "singular_f": "grande",
                "plural_m": "grandi",
                "plural_f": "grandi",
            },
        )


if __name__ == "__main__":
    unittest.main()
