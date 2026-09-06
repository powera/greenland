import unittest

from langtools.lt.utils import palatalize_final


class TestPalatalizeFinal(unittest.TestCase):
    """The t->č / d->dž rule shared by conjugation and declension."""

    def test_dental_stops_palatalize(self) -> None:
        self.assertEqual(palatalize_final("pet"), "peč")
        self.assertEqual(palatalize_final("pavyzd"), "pavyzdž")
        self.assertEqual(palatalize_final("gaid"), "gaidž")

    def test_other_consonants_unchanged(self) -> None:
        for stem in ("trauk", "arkl", "ryš", "griov", "kamuol"):
            with self.subTest(stem=stem):
                self.assertEqual(palatalize_final(stem), stem)

    def test_empty_stem(self) -> None:
        self.assertEqual(palatalize_final(""), "")

    def test_is_idempotent_on_already_palatalized(self) -> None:
        # "dž" ends in "ž", not "d", so a second pass must not re-fire.
        self.assertEqual(palatalize_final("pavyzdž"), "pavyzdž")
        self.assertEqual(palatalize_final("peč"), "peč")


if __name__ == "__main__":
    unittest.main()
