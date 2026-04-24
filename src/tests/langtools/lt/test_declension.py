import unittest

from langtools.lt.declension import (
    decline_noun,
    get_declension_requirements,
    get_supported_declension_classes,
)


class TestLithuanianMechanicalDeclension(unittest.TestCase):
    def test_declines_masc_as(self) -> None:
        forms = decline_noun("vilkas")
        assert forms is not None
        self.assertEqual(forms["genitive_singular"], "vilko")
        self.assertEqual(forms["dative_plural"], "vilkams")
        self.assertEqual(forms["declension_class"], "masc_as")
        self.assertEqual(forms["gender"], "masculine")

    def test_declines_fem_e(self) -> None:
        forms = decline_noun("upė")
        assert forms is not None
        self.assertEqual(forms["accusative_singular"], "upę")
        self.assertEqual(forms["locative_plural"], "upėse")

    def test_declines_masc_us(self) -> None:
        forms = decline_noun("sūnus")
        assert forms is not None
        self.assertEqual(forms["genitive_singular"], "sūnaus")
        self.assertEqual(forms["locative_singular"], "sūnuje")
        self.assertEqual(forms["nominative_plural"], "sūnūs")

    def test_requires_gender_for_ambiguous_is(self) -> None:
        self.assertIsNone(decline_noun("pilis"))
        feminine_forms = decline_noun("pilis", grammatical_gender="feminine")
        assert feminine_forms is not None
        self.assertEqual(feminine_forms["genitive_singular"], "pilies")

    def test_skips_irregular(self) -> None:
        self.assertIsNone(decline_noun("žmogus"))

    def test_respects_known_gender(self) -> None:
        self.assertIsNone(decline_noun("vilkas", grammatical_gender="feminine"))

    def test_requirements_shape(self) -> None:
        requirements = get_declension_requirements()
        self.assertIn("declension_class", requirements)
        self.assertIn("irregular_flag", requirements)

    def test_supported_classes_include_major_regular_sets(self) -> None:
        classes = get_supported_declension_classes()
        self.assertIn("masc_as", classes)
        self.assertIn("masc_us", classes)
        self.assertIn("masc_ys", classes)
        self.assertIn("fem_a", classes)
        self.assertIn("fem_ė", classes)


if __name__ == "__main__":
    unittest.main()
