import unittest

from langtools.lt.adjectives import build_adverb_degrees, decline_adjective

POSITIVE_SLOTS = 7 * 2 * 2
ALL_SLOTS = POSITIVE_SLOTS + 2 * 8


class TestDeclineAdjective(unittest.TestCase):
    def test_as_class_with_degrees(self) -> None:
        forms = decline_adjective("pilkas")
        assert forms is not None
        self.assertEqual(len(forms), ALL_SLOTS)
        self.assertEqual(forms["genitive_singular_m"], "pilko")
        self.assertEqual(forms["dative_plural_m"], "pilkiems")
        self.assertEqual(forms["locative_singular_f"], "pilkoje")
        self.assertEqual(forms["comparative_accusative_singular_m"], "pilkesnį")
        self.assertEqual(forms["superlative_nominative_plural_m"], "pilkiausi")

    def test_superlative_palatalizes_dental_stem(self) -> None:
        forms = decline_adjective("baltas")
        assert forms is not None
        self.assertEqual(forms["dative_plural_m"], "baltiems")
        self.assertEqual(forms["superlative_nominative_singular_m"], "balčiausias")

    def test_ias_class_keeps_soft_stem(self) -> None:
        forms = decline_adjective("plokščias")
        assert forms is not None
        self.assertEqual(forms["nominative_plural_m"], "plokšči")
        self.assertEqual(forms["dative_plural_m"], "plokščiems")
        self.assertEqual(forms["comparative_nominative_singular_m"], "plokštesnis")
        self.assertEqual(forms["superlative_nominative_singular_m"], "plokščiausias")

    def test_us_class_palatalizes_only_before_back_vowels(self) -> None:
        forms = decline_adjective("platus")
        assert forms is not None
        self.assertEqual(forms["genitive_singular_m"], "plataus")
        self.assertEqual(forms["nominative_plural_m"], "platūs")
        self.assertEqual(forms["dative_plural_m"], "platiems")
        self.assertEqual(forms["nominative_singular_f"], "plati")
        self.assertEqual(forms["genitive_singular_f"], "plačios")
        self.assertEqual(forms["superlative_nominative_singular_m"], "plačiausias")

    def test_relational_is_class_has_no_degrees(self) -> None:
        forms = decline_adjective("medinis")
        assert forms is not None
        self.assertEqual(len(forms), POSITIVE_SLOTS)
        self.assertEqual(forms["nominative_plural_m"], "mediniai")
        self.assertEqual(forms["dative_plural_m"], "mediniams")
        self.assertEqual(forms["locative_singular_f"], "medinėje")

    def test_didelis_exceptions(self) -> None:
        forms = decline_adjective("didelis")
        assert forms is not None
        self.assertEqual(forms["nominative_plural_m"], "dideli")
        self.assertEqual(forms["dative_plural_m"], "dideliems")
        self.assertEqual(forms["comparative_nominative_singular_m"], "didesnis")
        self.assertEqual(forms["superlative_nominative_singular_m"], "didžiausias")

    def test_participles(self) -> None:
        present = decline_adjective("sergantis")
        assert present is not None
        self.assertEqual(present["genitive_singular_m"], "sergančio")
        self.assertEqual(present["nominative_plural_m"], "sergantys")
        self.assertEqual(present["dative_plural_m"], "sergantiems")
        self.assertNotIn("comparative_nominative_singular_m", present)

        past = decline_adjective("pavargęs")
        assert past is not None
        self.assertEqual(past["nominative_plural_m"], "pavargę")
        self.assertEqual(past["nominative_singular_f"], "pavargusi")
        self.assertEqual(past["locative_singular_m"], "pavargusiame")

    def test_non_gradable(self) -> None:
        kitas = decline_adjective("kitas")
        assert kitas is not None
        self.assertEqual(len(kitas), POSITIVE_SLOTS)
        by_fact = decline_adjective("geras", "non_gradable")
        assert by_fact is not None
        self.assertEqual(len(by_fact), POSITIVE_SLOTS)

    def test_refuses_unhandled_shapes(self) -> None:
        for word in ("kairysis", "pastarasis", "pasibjaustinąs", "Vilnius", "pasitikintis savimi"):
            with self.subTest(word=word):
                self.assertIsNone(decline_adjective(word))


class TestAdverbDegrees(unittest.TestCase):
    def test_derived_adverbs_compare(self) -> None:
        cases = {
            "gerai": ("geriau", "geriausiai"),
            "greitai": ("greičiau", "greičiausiai"),
            "plačiai": ("plačiau", "plačiausiai"),
            "arti": ("arčiau", "arčiausiai"),
            "toli": ("toliau", "toliausiai"),
        }
        for adverb, (comparative, superlative) in cases.items():
            with self.subTest(adverb=adverb):
                forms = build_adverb_degrees(adverb)
                assert forms is not None
                self.assertEqual(forms["positive"], adverb)
                self.assertEqual(forms["comparative"], comparative)
                self.assertEqual(forms["superlative"], superlative)

    def test_positive_only(self) -> None:
        for adverb in ("dabar", "paprastai", "daugiausiai", "lietuviškai"):
            with self.subTest(adverb=adverb):
                self.assertEqual(build_adverb_degrees(adverb), {"positive": adverb})
        self.assertEqual(build_adverb_degrees("gerai", "non_gradable"), {"positive": "gerai"})

    def test_refuses_multi_word(self) -> None:
        self.assertIsNone(build_adverb_degrees("vis dar"))


if __name__ == "__main__":
    unittest.main()
