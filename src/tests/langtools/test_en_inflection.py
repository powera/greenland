#!/usr/bin/env python3

"""Tests for English noun/adjective/adverb inflection (langtools.en.inflection).

The module holds spelling rules only; lexical properties (countability,
plurale tantum, irregular plurals, gradability) arrive as parameters from the
lemma's stored grammar facts, so the tests supply them explicitly.
"""

import unittest

from langtools.en.inflection import (
    HARD_CH_NOUNS,
    IRREGULAR_ADVERB_COMPARISON,
    IRREGULAR_COMPARISON,
    build_adjective_forms,
    build_adverb_forms,
    build_noun_forms,
    count_syllables,
)

# Field names matching FORM_SPECS in langtools/en/forms_config.py.  Defined
# here to avoid importing llm_forms (which pulls in storage/sqlalchemy).
NOUN_FORM_KEYS = {"singular", "plural"}
DEGREE_FORM_KEYS = {"positive", "comparative", "superlative"}


class TestNounRegularPlurals(unittest.TestCase):
    """Regular noun pluralization."""

    def test_plain_s(self) -> None:
        self.assertEqual(build_noun_forms("book"), {"singular": "book", "plural": "books"})

    def test_sibilant_takes_es(self) -> None:
        for singular, plural in (
            ("church", "churches"),
            ("box", "boxes"),
            ("bush", "bushes"),
            ("glass", "glasses"),
        ):
            with self.subTest(singular=singular):
                forms = build_noun_forms(singular)
                assert forms is not None
                self.assertEqual(forms["plural"], plural)

    def test_consonant_y_takes_ies(self) -> None:
        forms = build_noun_forms("city")
        assert forms is not None
        self.assertEqual(forms["plural"], "cities")

    def test_vowel_y_takes_s(self) -> None:
        forms = build_noun_forms("day")
        assert forms is not None
        self.assertEqual(forms["plural"], "days")

    def test_hard_ch_takes_plain_s(self) -> None:
        forms = build_noun_forms("stomach")
        assert forms is not None
        self.assertEqual(forms["plural"], "stomachs")

    def test_every_hard_ch_noun_takes_plain_s(self) -> None:
        for singular in HARD_CH_NOUNS:
            with self.subTest(singular=singular):
                forms = build_noun_forms(singular)
                assert forms is not None
                self.assertEqual(forms["plural"], singular + "s")

    def test_double_f_never_takes_ves(self) -> None:
        for singular, plural in (("giraffe", "giraffes"), ("cliff", "cliffs")):
            with self.subTest(singular=singular):
                forms = build_noun_forms(singular)
                assert forms is not None
                self.assertEqual(forms["plural"], plural)

    def test_only_registry_keys_emitted(self) -> None:
        forms = build_noun_forms("book")
        assert forms is not None
        self.assertEqual(set(forms), NOUN_FORM_KEYS)


class TestNounIrregularPluralFact(unittest.TestCase):
    """A supplied ``plural`` fact is used verbatim."""

    def test_suppletive_plural_from_fact(self) -> None:
        for singular, plural in (
            ("child", "children"),
            ("mouse", "mice"),
            ("foot", "feet"),
            ("tooth", "teeth"),
            ("person", "people"),
            ("ox", "oxen"),
        ):
            with self.subTest(singular=singular):
                self.assertEqual(
                    build_noun_forms(singular, irregular_plural=plural),
                    {"singular": singular, "plural": plural},
                )

    def test_unchanged_plural_from_fact(self) -> None:
        for singular in ("sheep", "deer", "fish", "aircraft"):
            with self.subTest(singular=singular):
                forms = build_noun_forms(singular, irregular_plural=singular)
                assert forms is not None
                self.assertEqual(forms["plural"], singular)

    def test_fact_beats_the_regular_spelling_rule(self) -> None:
        """Without the fact "leaf" falls through; with it, it is "leaves"."""
        self.assertIsNone(build_noun_forms("leaf"))
        self.assertEqual(
            build_noun_forms("leaf", irregular_plural="leaves"),
            {"singular": "leaf", "plural": "leaves"},
        )

    def test_fact_beats_a_regular_form_that_would_otherwise_be_produced(self) -> None:
        # "man" would regularly give "mans"; the fact overrides it.
        self.assertEqual(
            build_noun_forms("man", irregular_plural="men"),
            {"singular": "man", "plural": "men"},
        )

    def test_fact_value_is_stripped(self) -> None:
        forms = build_noun_forms("child", irregular_plural="  children  ")
        assert forms is not None
        self.assertEqual(forms["plural"], "children")


class TestNounNumberTypeFact(unittest.TestCase):
    """``number_type`` and ``countability`` control the plural slot."""

    def test_uncountable_number_type_has_no_plural(self) -> None:
        self.assertEqual(
            build_noun_forms("information", number_type="uncountable"),
            {"singular": "information"},
        )

    def test_singulare_tantum_has_no_plural(self) -> None:
        self.assertEqual(
            build_noun_forms("furniture", number_type="singulare_tantum"),
            {"singular": "furniture"},
        )

    def test_uncountable_countability_has_no_plural(self) -> None:
        self.assertEqual(
            build_noun_forms("widget", countability="uncountable"), {"singular": "widget"}
        )

    def test_plurale_tantum_repeats_the_lemma(self) -> None:
        for lemma in ("jeans", "scissors", "pants", "trousers"):
            with self.subTest(lemma=lemma):
                self.assertEqual(
                    build_noun_forms(lemma, number_type="plurale_tantum"),
                    {"singular": lemma, "plural": lemma},
                )

    def test_plurale_tantum_beats_the_ambiguous_ending_fallthrough(self) -> None:
        # "-s" is an ambiguous ending, so without the fact "jeans" declines.
        self.assertIsNone(build_noun_forms("jeans"))

    def test_number_type_both_takes_the_regular_rule(self) -> None:
        self.assertEqual(
            build_noun_forms("book", number_type="both"),
            {"singular": "book", "plural": "books"},
        )

    def test_countable_fact_does_not_suppress_the_plural(self) -> None:
        """ "iron" the appliance is countable, and pluralizes regularly."""
        self.assertEqual(
            build_noun_forms("iron", countability="countable"),
            {"singular": "iron", "plural": "irons"},
        )


class TestNounFallthrough(unittest.TestCase):
    """Cases the rules must decline to answer."""

    def test_ambiguous_endings_fall_through(self) -> None:
        for lemma in ("hippopotamus", "lithium", "canvas", "diabetes", "cactus", "potato"):
            with self.subTest(lemma=lemma):
                self.assertIsNone(build_noun_forms(lemma))

    def test_uncountable_word_without_a_fact_now_pluralizes(self) -> None:
        """With the surface-text table gone, spelling alone decides."""
        self.assertEqual(build_noun_forms("advice"), {"singular": "advice", "plural": "advices"})

    def test_multiword_lemma_falls_through(self) -> None:
        self.assertIsNone(build_noun_forms("air conditioner"))

    def test_hyphenated_lemma_falls_through(self) -> None:
        self.assertIsNone(build_noun_forms("brother-in-law"))

    def test_disambiguated_lemma_falls_through(self) -> None:
        self.assertIsNone(build_noun_forms("head (of cattle)"))

    def test_proper_noun_falls_through(self) -> None:
        for lemma in ("Amsterdam", "Monday", "Mr."):
            with self.subTest(lemma=lemma):
                self.assertIsNone(build_noun_forms(lemma))

    def test_facts_do_not_rescue_an_unsafe_lemma(self) -> None:
        self.assertIsNone(build_noun_forms("air conditioner", irregular_plural="air conditioners"))

    def test_empty_falls_through(self) -> None:
        self.assertIsNone(build_noun_forms(""))
        self.assertIsNone(build_noun_forms("   "))


class TestCountSyllables(unittest.TestCase):
    """The syllable heuristic driving adjective comparison."""

    def test_monosyllables(self) -> None:
        for word in ("big", "large", "wide", "strong", "true"):
            with self.subTest(word=word):
                self.assertEqual(count_syllables(word), 1)

    def test_disyllables(self) -> None:
        for word in ("happy", "common", "simple", "polite"):
            with self.subTest(word=word):
                self.assertEqual(count_syllables(word), 2)

    def test_polysyllables(self) -> None:
        self.assertGreaterEqual(count_syllables("beautiful"), 3)
        self.assertGreaterEqual(count_syllables("comfortable"), 3)

    def test_never_returns_zero(self) -> None:
        self.assertEqual(count_syllables("e"), 1)


class TestAdjectiveComparison(unittest.TestCase):
    """Adjective degree forms from the spelling rules."""

    def test_monosyllable_takes_er_est(self) -> None:
        self.assertEqual(
            build_adjective_forms("tall"),
            {"positive": "tall", "comparative": "taller", "superlative": "tallest"},
        )

    def test_final_consonant_doubling(self) -> None:
        for positive, comparative, superlative in (
            ("big", "bigger", "biggest"),
            ("thin", "thinner", "thinnest"),
            ("dim", "dimmer", "dimmest"),
            ("hot", "hotter", "hottest"),
        ):
            with self.subTest(positive=positive):
                self.assertEqual(
                    build_adjective_forms(positive),
                    {
                        "positive": positive,
                        "comparative": comparative,
                        "superlative": superlative,
                    },
                )

    def test_consonant_y_takes_ier_iest(self) -> None:
        self.assertEqual(
            build_adjective_forms("happy"),
            {"positive": "happy", "comparative": "happier", "superlative": "happiest"},
        )

    def test_silent_e_takes_r_st(self) -> None:
        forms = build_adjective_forms("large")
        assert forms is not None
        self.assertEqual(forms["comparative"], "larger")
        self.assertEqual(forms["superlative"], "largest")

    def test_polysyllable_takes_more_most(self) -> None:
        self.assertEqual(
            build_adjective_forms("beautiful"),
            {
                "positive": "beautiful",
                "comparative": "more beautiful",
                "superlative": "most beautiful",
            },
        )

    def test_disyllabic_suffix_takes_more_most(self) -> None:
        for positive in ("careful", "famous", "bored"):
            with self.subTest(positive=positive):
                forms = build_adjective_forms(positive)
                assert forms is not None
                self.assertEqual(forms["comparative"], f"more {positive}")

    def test_in_code_irregular_comparison_is_the_fallback(self) -> None:
        for positive, comparative, superlative in (
            ("good", "better", "best"),
            ("bad", "worse", "worst"),
            ("far", "farther", "farthest"),
            ("little", "less", "least"),
        ):
            with self.subTest(positive=positive):
                self.assertEqual(
                    build_adjective_forms(positive),
                    {
                        "positive": positive,
                        "comparative": comparative,
                        "superlative": superlative,
                    },
                )

    def test_every_irregular_entry_is_returned(self) -> None:
        for positive, expected in IRREGULAR_COMPARISON.items():
            with self.subTest(positive=positive):
                self.assertEqual(
                    build_adjective_forms(positive), {"positive": positive, **expected}
                )

    def test_only_registry_keys_emitted(self) -> None:
        forms = build_adjective_forms("tall")
        assert forms is not None
        self.assertEqual(set(forms), DEGREE_FORM_KEYS)


class TestAdjectiveGradabilityFact(unittest.TestCase):
    """Each ``gradability`` value drives a distinct outcome."""

    def test_non_gradable_gives_positive_only(self) -> None:
        for positive in ("dead", "unique", "square", "wooden"):
            with self.subTest(positive=positive):
                self.assertEqual(
                    build_adjective_forms(positive, gradability="non_gradable"),
                    {"positive": positive},
                )

    def test_non_gradable_beats_the_syllable_rule(self) -> None:
        # "dead" is a monosyllable, so without the fact it takes -er/-est.
        forms = build_adjective_forms("dead")
        assert forms is not None
        self.assertEqual(forms["comparative"], "deader")

    def test_periphrastic_forces_more_most(self) -> None:
        self.assertEqual(
            build_adjective_forms("glad", gradability="periphrastic"),
            {"positive": "glad", "comparative": "more glad", "superlative": "most glad"},
        )

    def test_synthetic_forces_er_est(self) -> None:
        self.assertEqual(
            build_adjective_forms("common", gradability="synthetic"),
            {"positive": "common", "comparative": "commoner", "superlative": "commonest"},
        )

    def test_explicit_forms_win_outright(self) -> None:
        self.assertEqual(
            build_adjective_forms("tall", comparative="taller than", superlative="tallest of"),
            {"positive": "tall", "comparative": "taller than", "superlative": "tallest of"},
        )

    def test_explicit_forms_override_the_in_code_irregular_table(self) -> None:
        self.assertEqual(
            build_adjective_forms("far", comparative="further", superlative="furthest"),
            {"positive": "far", "comparative": "further", "superlative": "furthest"},
        )

    def test_half_a_pair_declines(self) -> None:
        self.assertIsNone(build_adjective_forms("tall", comparative="taller"))
        self.assertIsNone(build_adjective_forms("tall", superlative="tallest"))

    def test_non_gradable_wins_over_supplied_forms(self) -> None:
        self.assertEqual(
            build_adjective_forms(
                "dead", gradability="non_gradable", comparative="deader", superlative="deadest"
            ),
            {"positive": "dead"},
        )


class TestAdjectiveFallthrough(unittest.TestCase):
    """Two-syllable adjectives without a clear rule must decline."""

    def test_ambiguous_disyllables_fall_through(self) -> None:
        for positive in ("common", "polite", "stubborn", "narrow", "simple"):
            with self.subTest(positive=positive):
                self.assertIsNone(build_adjective_forms(positive))

    def test_proper_and_multiword_fall_through(self) -> None:
        self.assertIsNone(build_adjective_forms("Dutch"))
        self.assertIsNone(build_adjective_forms("well known"))

    def test_empty_falls_through(self) -> None:
        self.assertIsNone(build_adjective_forms(""))


class TestAdverbComparison(unittest.TestCase):
    """Adverb degree forms from the spelling rules."""

    def test_in_code_irregular_adverbs_are_the_fallback(self) -> None:
        for positive, comparative, superlative in (
            ("well", "better", "best"),
            ("badly", "worse", "worst"),
            ("far", "farther", "farthest"),
            ("little", "less", "least"),
            ("much", "more", "most"),
        ):
            with self.subTest(positive=positive):
                self.assertEqual(
                    build_adverb_forms(positive),
                    {
                        "positive": positive,
                        "comparative": comparative,
                        "superlative": superlative,
                    },
                )

    def test_every_irregular_entry_is_returned(self) -> None:
        for positive, expected in IRREGULAR_ADVERB_COMPARISON.items():
            with self.subTest(positive=positive):
                self.assertEqual(build_adverb_forms(positive), {"positive": positive, **expected})

    def test_ly_manner_adverbs_take_more_most(self) -> None:
        self.assertEqual(
            build_adverb_forms("quickly"),
            {
                "positive": "quickly",
                "comparative": "more quickly",
                "superlative": "most quickly",
            },
        )


class TestAdverbGradabilityFact(unittest.TestCase):
    """Each ``gradability`` value drives a distinct outcome."""

    def test_non_gradable_gives_positive_only(self) -> None:
        for positive in ("never", "here", "today", "absolutely", "twice"):
            with self.subTest(positive=positive):
                self.assertEqual(
                    build_adverb_forms(positive, gradability="non_gradable"),
                    {"positive": positive},
                )

    def test_non_gradable_ly_adverb_is_not_compared(self) -> None:
        self.assertEqual(
            build_adverb_forms("daily", gradability="non_gradable"), {"positive": "daily"}
        )

    def test_synthetic_covers_the_flat_adverbs(self) -> None:
        for positive, comparative in (
            ("fast", "faster"),
            ("hard", "harder"),
            ("high", "higher"),
            ("early", "earlier"),
        ):
            with self.subTest(positive=positive):
                forms = build_adverb_forms(positive, gradability="synthetic")
                assert forms is not None
                self.assertEqual(set(forms), DEGREE_FORM_KEYS)
                self.assertEqual(forms["comparative"], comparative)

    def test_periphrastic_forces_more_most(self) -> None:
        self.assertEqual(
            build_adverb_forms("soon", gradability="periphrastic"),
            {"positive": "soon", "comparative": "more soon", "superlative": "most soon"},
        )

    def test_explicit_forms_win_outright(self) -> None:
        self.assertEqual(
            build_adverb_forms("far", comparative="further", superlative="furthest"),
            {"positive": "far", "comparative": "further", "superlative": "furthest"},
        )

    def test_half_a_pair_declines(self) -> None:
        self.assertIsNone(build_adverb_forms("quickly", comparative="more quickly"))


class TestAdverbFallthrough(unittest.TestCase):
    """Non-``-ly`` adverbs with no supplied fact must decline."""

    def test_unlisted_adverbs_fall_through(self) -> None:
        for positive in ("often", "seldom", "round", "nearby", "fast", "hard", "never", "today"):
            with self.subTest(positive=positive):
                self.assertIsNone(build_adverb_forms(positive))

    def test_already_comparative_forms_fall_through(self) -> None:
        for positive in ("earlier", "less", "more", "most", "sooner"):
            with self.subTest(positive=positive):
                self.assertIsNone(build_adverb_forms(positive))

    def test_multiword_adverb_falls_through(self) -> None:
        self.assertIsNone(build_adverb_forms("this morning"))

    def test_empty_falls_through(self) -> None:
        self.assertIsNone(build_adverb_forms(""))


class TestTableHygiene(unittest.TestCase):
    """Structural invariants over the few remaining in-code tables."""

    def test_tables_are_non_empty(self) -> None:
        for table in (HARD_CH_NOUNS, IRREGULAR_COMPARISON, IRREGULAR_ADVERB_COMPARISON):
            with self.subTest(table=table):
                self.assertGreater(len(table), 0)

    def test_all_entries_are_lowercase(self) -> None:
        for table in (HARD_CH_NOUNS, IRREGULAR_COMPARISON, IRREGULAR_ADVERB_COMPARISON):
            for entry in table:
                with self.subTest(entry=entry):
                    self.assertEqual(entry, entry.lower())

    def test_irregular_comparison_entries_have_both_degrees(self) -> None:
        for table in (IRREGULAR_COMPARISON, IRREGULAR_ADVERB_COMPARISON):
            for positive, degrees in table.items():
                with self.subTest(positive=positive):
                    self.assertEqual(set(degrees), {"comparative", "superlative"})

    def test_hard_ch_nouns_all_end_in_ch(self) -> None:
        for entry in HARD_CH_NOUNS:
            with self.subTest(entry=entry):
                self.assertTrue(entry.endswith("ch"))


if __name__ == "__main__":
    unittest.main()
