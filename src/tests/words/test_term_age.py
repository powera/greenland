"""Tests for the deterministic term-age (lexical stratum) scorer.

Assertions compare against the module's own constants rather than hardcoded
floats, so retuning the weights does not silently invalidate the tests.
"""

import unittest

from langtools.ja.script_analysis import JapaneseScriptType
from storage.models.enums import NounSubtype
from words.term_age import (
    ANCIENT_CONSENSUS_WEIGHT,
    CONFIDENT_BAND_MIN_CONFIDENCE,
    NAMED_ENTITY_SUBTYPES,
    NEUTRAL_SCORE,
    LexicalStratum,
    ancient_signal,
    japanese_signal,
    score_term_age,
    stratum_for_score,
    subtype_signal,
)

ALL_CONVENTIONAL = {
    "la": "conventional",
    "sa": "conventional",
    "grc": "conventional",
    "ar-classical": "conventional",
    "non": "conventional",
}
ALL_MODERN = {
    "la": "modern_loan",
    "sa": "late_construction",
    "grc": "late_construction",
    "ar-classical": "late_construction",
    "non": "late_construction",
}


class TestAncientSignal(unittest.TestCase):
    """The classical-language consensus, the strongest available signal."""

    def test_unanimous_conventional_is_maximally_ancient(self) -> None:
        modernity, conventional, evidence, _reasons = ancient_signal(ALL_CONVENTIONAL)
        self.assertEqual(modernity, -1.0)
        self.assertEqual(conventional, 5)
        self.assertEqual(evidence, 5)

    def test_unanimous_coinage_is_maximally_modern(self) -> None:
        modernity, conventional, evidence, _reasons = ancient_signal(ALL_MODERN)
        self.assertEqual(modernity, 1.0)
        self.assertEqual(conventional, 0)
        self.assertEqual(evidence, 5)

    def test_absent_evidence_returns_none_not_zero(self) -> None:
        """No evidence must be distinguishable from evidence that averages to 0."""
        modernity, _conventional, evidence, reasons = ancient_signal({})
        self.assertIsNone(modernity)
        self.assertEqual(evidence, 0)
        self.assertIn("ancient_no_evidence", reasons)

    def test_null_status_is_not_evidence(self) -> None:
        """A translation without a judgement must not vote."""
        _modernity, _conventional, evidence, _reasons = ancient_signal({"la": None, "sa": None})
        self.assertEqual(evidence, 0)

    def test_non_ancient_languages_are_ignored(self) -> None:
        _modernity, _conventional, evidence, _reasons = ancient_signal(
            {"de": "conventional", "ja": "conventional"}
        )
        self.assertEqual(evidence, 0)

    def test_unknown_status_value_is_reported_not_crashed(self) -> None:
        _modernity, _conventional, evidence, reasons = ancient_signal({"la": "bogus"})
        self.assertEqual(evidence, 0)
        self.assertTrue(any("ancient_status_unknown_value" in reason for reason in reasons))


class TestJapaneseSignal(unittest.TestCase):
    """Japanese orthography, including its documented failure modes."""

    def test_katakana_pulls_modern(self) -> None:
        script, modernity, _reasons = japanese_signal("コンピューター", "technology_digital")
        self.assertEqual(script, JapaneseScriptType.KATAKANA)
        self.assertGreater(modernity, 0.0)

    def test_kanji_pulls_ancient(self) -> None:
        script, modernity, _reasons = japanese_signal("塩", "material_substance")
        self.assertEqual(script, JapaneseScriptType.KANJI)
        self.assertLess(modernity, 0.0)

    def test_absent_translation_is_neutral(self) -> None:
        script, modernity, reasons = japanese_signal(None, "animal")
        self.assertIsNone(script)
        self.assertEqual(modernity, 0.0)
        self.assertIn("japanese_absent", reasons)

    def test_katakana_suppressed_for_named_entities(self) -> None:
        """Berlin is katakana because it transliterates a foreign name.

        Regression guard for the confound that motivated NAMED_ENTITY_SUBTYPES:
        these carry pos_subtype 'city'/'country', never 'proper_noun'.
        """
        for subtype in (NounSubtype.CITY.value, NounSubtype.COUNTRY.value):
            with self.subTest(subtype=subtype):
                script, modernity, reasons = japanese_signal("ベルリン", subtype)
                self.assertEqual(script, JapaneseScriptType.KATAKANA)
                self.assertEqual(modernity, 0.0)
                self.assertTrue(
                    any("katakana_suppressed_named_entity" in reason for reason in reasons)
                )

    def test_generic_place_nouns_are_not_suppressed(self) -> None:
        """PLACE_NAME covers generic nouns (room, street), not proper names."""
        self.assertNotIn(NounSubtype.PLACE_NAME.value, NAMED_ENTITY_SUBTYPES)


class TestSubtypeSignal(unittest.TestCase):
    def test_ancient_and_modern_subtypes_pull_opposite_ways(self) -> None:
        ancient_pull, _ = subtype_signal("body_part")
        modern_pull, _ = subtype_signal("technology_digital")
        self.assertLess(ancient_pull, 0.0)
        self.assertGreater(modern_pull, 0.0)

    def test_unknown_subtype_is_neutral(self) -> None:
        pull, reasons = subtype_signal("not_a_real_subtype")
        self.assertEqual(pull, 0.0)
        self.assertTrue(any("subtype_neutral" in reason for reason in reasons))

    def test_mixed_stratum_subtypes_pull_less_than_clear_ones(self) -> None:
        """vehicle spans cart and bus, so it must not outweigh a clear signal."""
        mixed_pull, _ = subtype_signal("vehicle")
        clear_pull, _ = subtype_signal("technology_digital")
        self.assertLess(abs(mixed_pull), abs(clear_pull))


class TestStratumBanding(unittest.TestCase):
    def test_outer_bands_require_corroboration(self) -> None:
        """One weak signal must not buy a confident ANCIENT_CORE/MODERN label."""
        low = CONFIDENT_BAND_MIN_CONFIDENCE / 2
        self.assertEqual(stratum_for_score(0.05, low), LexicalStratum.TRADITIONAL)
        self.assertEqual(stratum_for_score(0.95, low), LexicalStratum.EARLY_MODERN)

    def test_outer_bands_allowed_when_corroborated(self) -> None:
        self.assertEqual(stratum_for_score(0.05, 1.0), LexicalStratum.ANCIENT_CORE)
        self.assertEqual(stratum_for_score(0.95, 1.0), LexicalStratum.MODERN)


class TestScoreTermAge(unittest.TestCase):
    def test_ancient_concept_scores_ancient_core(self) -> None:
        result = score_term_age(
            lemma_text="ship",
            pos_subtype="vehicle",
            japanese_translation="船",
            ancient_statuses=ALL_CONVENTIONAL,
        )
        self.assertEqual(result.stratum, LexicalStratum.ANCIENT_CORE)
        self.assertEqual(result.ancient_conventional_count, 5)

    def test_modern_concept_scores_modern(self) -> None:
        result = score_term_age(
            lemma_text="bicycle",
            pos_subtype="vehicle",
            japanese_translation="自転車",
            ancient_statuses=ALL_MODERN,
        )
        self.assertEqual(result.stratum, LexicalStratum.MODERN)

    def test_classical_consensus_outweighs_subtype_prior(self) -> None:
        """Unanimous classical evidence must dominate a mildly-modern prior."""
        result = score_term_age(
            lemma_text="ship",
            pos_subtype="vehicle",
            ancient_statuses=ALL_CONVENTIONAL,
        )
        self.assertLess(result.score, NEUTRAL_SCORE)
        self.assertEqual(result.stratum, LexicalStratum.ANCIENT_CORE)

    def test_no_signals_yields_unknown_at_zero_confidence(self) -> None:
        result = score_term_age(lemma_text="thing")
        self.assertEqual(result.stratum, LexicalStratum.UNKNOWN)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("no_signals_fired", result.reasons)

    def test_score_is_clamped_to_unit_interval(self) -> None:
        for statuses, subtype, text in (
            (ALL_CONVENTIONAL, "body_part", "眼"),
            (ALL_MODERN, "technology_digital", "コンピューター"),
        ):
            with self.subTest(text=text):
                result = score_term_age(
                    lemma_text=text,
                    pos_subtype=subtype,
                    japanese_translation=text,
                    ancient_statuses=statuses,
                )
                self.assertGreaterEqual(result.score, 0.0)
                self.assertLessEqual(result.score, 1.0)

    def test_ancient_consensus_weight_exceeds_other_signals(self) -> None:
        """The weighting that makes classical evidence decisive."""
        japanese_only = score_term_age(
            lemma_text="x", pos_subtype="animal", japanese_translation="クマ"
        )
        self.assertLess(
            abs(japanese_only.score - NEUTRAL_SCORE),
            ANCIENT_CONSENSUS_WEIGHT,
        )


class TestDocumentedConfounds(unittest.TestCase):
    """The known failure modes, pinned so they stay intended behavior.

    These are not bugs to fix by reweighting - they are limits of what Japanese
    orthography can tell you, and the reason the classical consensus outranks it.
    """

    def test_katakana_animal_names_are_pulled_back_by_subtype_prior(self) -> None:
        """クマ (bear) is katakana by biological-name convention, not novelty."""
        bear = score_term_age(lemma_text="bear", pos_subtype="animal", japanese_translation="クマ")
        unmitigated = score_term_age(
            lemma_text="bear", pos_subtype=None, japanese_translation="クマ"
        )
        self.assertLess(bear.score, unmitigated.score)

    def test_kanji_compound_for_modern_concept_is_rescued_by_classical_evidence(
        self,
    ) -> None:
        """自転車 is kanji but modern; only classical evidence catches that."""
        without_evidence = score_term_age(
            lemma_text="bicycle", pos_subtype="vehicle", japanese_translation="自転車"
        )
        with_evidence = score_term_age(
            lemma_text="bicycle",
            pos_subtype="vehicle",
            japanese_translation="自転車",
            ancient_statuses=ALL_MODERN,
        )
        self.assertNotEqual(with_evidence.stratum, LexicalStratum.ANCIENT_CORE)
        self.assertGreater(with_evidence.score, without_evidence.score)

    def test_majority_classical_evidence_outvotes_katakana(self) -> None:
        """spoon: conventional in la/sa/grc, a coinage in ar-classical/non.

        The consensus is an average, so mixed-but-informative evidence lands
        near zero; undamped, katakana (スプーン) then outvoted three classical
        languages that plainly had the word and spoon/cup/fork scored MODERN.
        """
        spoon = score_term_age(
            lemma_text="spoon",
            pos_subtype="small_movable_object",
            japanese_translation="スプーン",
            ancient_statuses={
                "la": "conventional",
                "sa": "conventional",
                "grc": "conventional",
                "ar-classical": "modern_loan",
                "non": "late_construction",
            },
        )
        self.assertNotEqual(spoon.stratum, LexicalStratum.MODERN)
        self.assertIn("weak_signals_damped_by_classical_evidence", spoon.reasons)

    def test_katakana_marks_cultural_novelty_not_age(self) -> None:
        """チーズ/パン are katakana because dairy and bread were foreign to Japan.

        Without classical evidence the Japanese signal misreads these ancient
        foods as modern; with it, they are pulled back out of the modern band.
        This is the coverage argument for populating la/sa.
        """
        bread_ja_only = score_term_age(
            lemma_text="bread", pos_subtype="food", japanese_translation="パン"
        )
        bread_with_evidence = score_term_age(
            lemma_text="bread",
            pos_subtype="food",
            japanese_translation="パン",
            ancient_statuses={"la": "conventional", "grc": "conventional", "non": "conventional"},
        )
        self.assertGreater(bread_ja_only.score, bread_with_evidence.score)
        self.assertNotEqual(bread_with_evidence.stratum, LexicalStratum.MODERN)


if __name__ == "__main__":
    unittest.main()
