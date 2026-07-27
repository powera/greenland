#!/usr/bin/env python3
"""
Tests for wordfreq.tools.sentence_word_linker module.

Tests the unified lemma resolution cascade. LLM disambiguation is not tested
here since it requires a live model; only the DB-based strategies are covered.
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import (
    Base,
    DerivativeForm,
    Lemma,
    Sentence,
    SentencePatternWord,
    SentenceTranslation,
    SentenceWord,
)
from wordfreq.tools.sentence_word_linker import (
    PART_OF_SPEECH_TO_POS,
    find_lemma_by_text,
    resolve_lemma_for_word,
    resolve_lemmas_for_sentence,
)


class TestFindLemmaByText(unittest.TestCase):
    """Test find_lemma_by_text (the consolidated _find_lemma_for_word)."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.lemma_eat = Lemma(
            lemma_text="eat",
            definition_text="to consume food",
            pos_type="verb",
            guid="V01_001",
        )
        self.lemma_apple = Lemma(
            lemma_text="apple",
            definition_text="a fruit",
            pos_type="noun",
            guid="N01_001",
        )
        self.lemma_set_verb = Lemma(
            lemma_text="set",
            definition_text="to put in a position",
            pos_type="verb",
            guid="V01_002",
        )
        self.lemma_set_noun = Lemma(
            lemma_text="set",
            definition_text="a group of things",
            pos_type="noun",
            guid="N01_002",
        )
        self.session.add_all(
            [self.lemma_eat, self.lemma_apple, self.lemma_set_verb, self.lemma_set_noun]
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_exact_match(self) -> None:
        result = find_lemma_by_text(self.session, "eat", "verb")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.guid, "V01_001")

    def test_case_insensitive_match(self) -> None:
        result = find_lemma_by_text(self.session, "Eat", "verb")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.guid, "V01_001")

    def test_pos_filtering(self) -> None:
        """'set' with part of speech 'verb' should return the verb lemma."""
        result = find_lemma_by_text(self.session, "set", "verb")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.guid, "V01_002")

    def test_pos_filtering_noun(self) -> None:
        """'set' with part of speech 'noun' should return the noun lemma."""
        result = find_lemma_by_text(self.session, "set", "noun")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.guid, "N01_002")

    def test_empty_text_returns_none(self) -> None:
        result = find_lemma_by_text(self.session, "", "verb")
        self.assertIsNone(result)

    def test_nonexistent_returns_none(self) -> None:
        result = find_lemma_by_text(self.session, "xyzzy", "noun")
        self.assertIsNone(result)

    def test_source_lemma_takes_priority(self) -> None:
        """If source_lemma text matches, use it even if DB has alternatives."""
        result = find_lemma_by_text(self.session, "eat", "verb", source_lemma=self.lemma_eat)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.id, self.lemma_eat.id)

    def test_source_lemma_strips_disambiguation(self) -> None:
        """Source lemma with '(animal)' should still match bare text."""
        lemma_mouse = Lemma(
            lemma_text="mouse (animal)",
            definition_text="a small rodent",
            pos_type="noun",
            guid="N01_003",
        )
        self.session.add(lemma_mouse)
        self.session.commit()

        result = find_lemma_by_text(self.session, "mouse", "noun", source_lemma=lemma_mouse)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.guid, "N01_003")

    def test_source_lemma_not_used_if_text_differs(self) -> None:
        """Source lemma should not match when text is different."""
        result = find_lemma_by_text(self.session, "apple", "noun", source_lemma=self.lemma_eat)
        self.assertIsNotNone(result)
        assert result is not None
        # Should find apple from DB, not return eat
        self.assertEqual(result.guid, "N01_001")

    def test_grammatical_english_word_returns_none(self) -> None:
        """Configured grammatical words should not be linked to lemmas."""
        article_lemma = Lemma(
            lemma_text="the",
            definition_text="definite article",
            pos_type="noun",
            guid="N01_004",
        )
        self.session.add(article_lemma)
        self.session.commit()

        result = find_lemma_by_text(self.session, "the", "noun")
        self.assertIsNone(result)


class TestResolveLemmaForWord(unittest.TestCase):
    """Test the cascade in resolve_lemma_for_word (no LLM)."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.lemma_teacher = Lemma(
            lemma_text="teacher",
            definition_text="a person who teaches",
            pos_type="noun",
            guid="N36_014",
            difficulty_level=4,
        )
        self.lemma_bank_finance = Lemma(
            lemma_text="bank",
            definition_text="financial institution",
            pos_type="noun",
            guid="N07_001",
            disambiguation="finance",
        )
        self.lemma_bank_river = Lemma(
            lemma_text="bank",
            definition_text="edge of a river",
            pos_type="noun",
            guid="N07_002",
            disambiguation="river",
        )
        self.lemma_see = Lemma(
            lemma_text="see",
            definition_text="to perceive with eyes",
            pos_type="verb",
            guid="V10_001",
        )
        self.session.add_all(
            [
                self.lemma_teacher,
                self.lemma_bank_finance,
                self.lemma_bank_river,
                self.lemma_see,
            ]
        )
        self.session.flush()

        # Derivative forms for teacher across languages
        self.session.add_all(
            [
                DerivativeForm(
                    lemma_id=self.lemma_teacher.id,
                    derivative_form_text="teacher",
                    language_code="en",
                    grammatical_form="singular",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_teacher.id,
                    derivative_form_text="mokytojas",
                    language_code="lt",
                    grammatical_form="nominative_singular",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_teacher.id,
                    derivative_form_text="mokytoją",
                    language_code="lt",
                    grammatical_form="accusative_singular",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_teacher.id,
                    derivative_form_text="professeur",
                    language_code="fr",
                    grammatical_form="singular",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_teacher.id,
                    derivative_form_text="老师",
                    language_code="zh",
                    grammatical_form="base",
                ),
            ]
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_guid_resolution(self) -> None:
        """GUID should resolve with confidence 1.0."""
        result = resolve_lemma_for_word(self.session, guid="N36_014", english_text="teacher")
        self.assertEqual(result.method, "guid")
        self.assertEqual(result.confidence, 1.0)
        self.assertIsNotNone(result.lemma)
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "N36_014")

    def test_guid_not_found_falls_through(self) -> None:
        """Missing GUID should fall through to text matching."""
        result = resolve_lemma_for_word(
            self.session, guid="NONEXISTENT", english_text="teacher", part_of_speech="noun"
        )
        # Should still resolve via text
        self.assertIsNotNone(result.lemma)
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "N36_014")
        self.assertEqual(result.method, "exact_text")

    def test_source_lemma_resolution(self) -> None:
        result = resolve_lemma_for_word(
            self.session,
            english_text="teacher",
            source_lemma=self.lemma_teacher,
        )
        self.assertEqual(result.method, "source_lemma")
        self.assertEqual(result.confidence, 0.95)

    def test_exact_text_single_match(self) -> None:
        """Unambiguous text should resolve with high confidence."""
        result = resolve_lemma_for_word(self.session, english_text="teacher", part_of_speech="noun")
        self.assertEqual(result.method, "exact_text")
        self.assertEqual(result.confidence, 0.9)
        self.assertIsNotNone(result.lemma)
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "N36_014")

    def test_polysemous_word_both_disambiguated(self) -> None:
        """'bank' with two disambiguated senses: should default to first."""
        result = resolve_lemma_for_word(self.session, english_text="bank", part_of_speech="noun")
        # Both candidates have disambiguation, so falls through to fallback
        self.assertIsNotNone(result.lemma)
        self.assertEqual(len(result.candidates), 2)
        # Lower confidence due to ambiguity
        self.assertLessEqual(result.confidence, 0.5)

    def test_polysemous_prefers_no_disambiguation(self) -> None:
        """When one candidate lacks disambiguation marker, prefer it."""
        # Add a third "bank" without disambiguation
        lemma_bank_plain = Lemma(
            lemma_text="bank",
            definition_text="generic bank",
            pos_type="noun",
            guid="N07_003",
        )
        self.session.add(lemma_bank_plain)
        self.session.commit()

        result = resolve_lemma_for_word(self.session, english_text="bank", part_of_speech="noun")
        self.assertIsNotNone(result.lemma)
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "N07_003")
        self.assertEqual(result.confidence, 0.8)

    def test_derivative_form_matching(self) -> None:
        """Cross-language derivative forms should resolve the lemma."""
        result = resolve_lemma_for_word(
            self.session,
            english_text="",
            forms_by_language={
                "lt": "mokytoją",
                "fr": "professeur",
                "zh": "老师",
            },
            min_derivative_languages=2,
        )
        self.assertEqual(result.method, "derivative_form")
        self.assertIsNotNone(result.lemma)
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "N36_014")

    def test_derivative_form_single_language_insufficient(self) -> None:
        """Single language derivative match should not resolve with min=2."""
        result = resolve_lemma_for_word(
            self.session,
            english_text="",
            forms_by_language={"lt": "mokytoją"},
            min_derivative_languages=2,
        )
        self.assertEqual(result.method, "unresolved")
        self.assertIsNone(result.lemma)

    def test_unresolved_returns_none_lemma(self) -> None:
        result = resolve_lemma_for_word(
            self.session, english_text="xyzzy_nonexistent", part_of_speech="noun"
        )
        self.assertEqual(result.method, "unresolved")
        self.assertIsNone(result.lemma)
        self.assertEqual(result.confidence, 0.0)

    def test_english_grammatical_word_is_not_resolved(self) -> None:
        """English grammatical words should short-circuit to unresolved lemma links."""
        article_lemma = Lemma(
            lemma_text="the",
            definition_text="definite article",
            pos_type="noun",
            guid="N36_099",
        )
        self.session.add(article_lemma)
        self.session.commit()

        result = resolve_lemma_for_word(self.session, english_text="the", part_of_speech="noun")
        self.assertEqual(result.method, "grammatical_word")
        self.assertIsNone(result.lemma)
        self.assertEqual(result.confidence, 1.0)

    def test_spanish_and_french_grammatical_words_are_skipped_in_derivatives(self) -> None:
        """Configured ES/FR grammatical tokens should not drive derivative matches."""
        article_lemma = Lemma(
            lemma_text="article placeholder",
            definition_text="fake article lemma for test coverage",
            pos_type="noun",
            guid="N36_100",
        )
        self.session.add(article_lemma)
        self.session.flush()
        self.session.add_all(
            [
                DerivativeForm(
                    lemma_id=article_lemma.id,
                    derivative_form_text="el",
                    language_code="es",
                    grammatical_form="base",
                ),
                DerivativeForm(
                    lemma_id=article_lemma.id,
                    derivative_form_text="le",
                    language_code="fr",
                    grammatical_form="base",
                ),
            ]
        )
        self.session.commit()

        result = resolve_lemma_for_word(
            self.session,
            english_text="",
            forms_by_language={"es": "el", "fr": "le"},
            min_derivative_languages=2,
        )
        self.assertEqual(result.method, "unresolved")
        self.assertIsNone(result.lemma)

    def test_spanish_tier3_function_word_can_still_resolve_by_derivative_match(self) -> None:
        """Tier-3 words (also-lemma) should not be skipped as pure grammatical tokens."""
        preposition_lemma = Lemma(
            lemma_text="in",
            definition_text="inside, within",
            pos_type="preposition",
            guid="P36_001",
        )
        self.session.add(preposition_lemma)
        self.session.flush()
        self.session.add_all(
            [
                DerivativeForm(
                    lemma_id=preposition_lemma.id,
                    derivative_form_text="en",
                    language_code="es",
                    grammatical_form="base",
                ),
                DerivativeForm(
                    lemma_id=preposition_lemma.id,
                    derivative_form_text="dans",
                    language_code="fr",
                    grammatical_form="base",
                ),
            ]
        )
        self.session.commit()

        result = resolve_lemma_for_word(
            self.session,
            english_text="",
            forms_by_language={"es": "en", "fr": "dans"},
            min_derivative_languages=2,
        )
        self.assertEqual(result.method, "derivative_form")
        self.assertIsNotNone(result.lemma)
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "P36_001")

    def test_guid_takes_precedence_over_text(self) -> None:
        """Even if text would match 'see', GUID for teacher should win."""
        result = resolve_lemma_for_word(
            self.session,
            guid="N36_014",
            english_text="see",
            part_of_speech="verb",
        )
        self.assertEqual(result.method, "guid")
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "N36_014")

    def test_derivative_single_match_resolves(self) -> None:
        """When only one lemma matches in derivatives, resolve directly."""
        # Add derivative forms for bank (finance) only
        self.session.add_all(
            [
                DerivativeForm(
                    lemma_id=self.lemma_bank_finance.id,
                    derivative_form_text="bankas",
                    language_code="lt",
                    grammatical_form="nominative_singular",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_bank_finance.id,
                    derivative_form_text="banque",
                    language_code="fr",
                    grammatical_form="singular",
                ),
            ]
        )
        self.session.commit()

        result = resolve_lemma_for_word(
            self.session,
            english_text="bank",
            part_of_speech="noun",
            forms_by_language={"lt": "bankas", "fr": "banque"},
            min_derivative_languages=2,
        )
        self.assertIsNotNone(result.lemma)
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "N07_001")
        self.assertEqual(result.method, "derivative_form")
        self.assertEqual(result.confidence, 0.85)

    def test_derivative_intersects_with_text_candidates(self) -> None:
        """When >1 derivative matches AND >1 text matches, intersection narrows."""
        # Add a non-bank lemma that shares a derivative form with bank_finance
        lemma_bench = Lemma(
            lemma_text="bench",
            definition_text="a long seat",
            pos_type="noun",
            guid="N07_010",
        )
        self.session.add(lemma_bench)
        self.session.flush()

        # Both bank_finance and bench have "bankas" in Lithuanian
        # (contrived: "bankas" could be a bench form in some language)
        self.session.add_all(
            [
                DerivativeForm(
                    lemma_id=self.lemma_bank_finance.id,
                    derivative_form_text="bankas",
                    language_code="lt",
                    grammatical_form="nominative_singular",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_bank_finance.id,
                    derivative_form_text="banque",
                    language_code="fr",
                    grammatical_form="singular",
                ),
                DerivativeForm(
                    lemma_id=lemma_bench.id,
                    derivative_form_text="bankas",
                    language_code="lt",
                    grammatical_form="nominative_singular",
                ),
                DerivativeForm(
                    lemma_id=lemma_bench.id,
                    derivative_form_text="banque",
                    language_code="fr",
                    grammatical_form="singular",
                ),
            ]
        )
        self.session.commit()

        # derivative_matches = [bank_finance, bench] (both match lt+fr forms)
        # exact_candidates from text "bank" = [bank_finance, bank_river]
        # intersection = [bank_finance] (the only one in both sets)
        result = resolve_lemma_for_word(
            self.session,
            english_text="bank",
            part_of_speech="noun",
            forms_by_language={"lt": "bankas", "fr": "banque"},
            min_derivative_languages=2,
        )
        self.assertIsNotNone(result.lemma)
        assert result.lemma is not None
        self.assertEqual(result.lemma.guid, "N07_001")
        self.assertEqual(result.method, "derivative_form")
        self.assertEqual(result.confidence, 0.9)


class TestResolveLemmasForSentence(unittest.TestCase):
    """Test resolve_lemmas_for_sentence with pattern_words and sentence_words."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Lemmas
        self.lemma_teacher = Lemma(
            lemma_text="teacher",
            definition_text="a person who teaches",
            pos_type="noun",
            guid="N36_014",
        )
        self.lemma_see = Lemma(
            lemma_text="see",
            definition_text="to perceive with eyes",
            pos_type="verb",
            guid="V10_001",
        )
        self.lemma_yesterday = Lemma(
            lemma_text="yesterday",
            definition_text="the day before today",
            pos_type="adverb",
            guid="D03_002",
        )
        self.session.add_all([self.lemma_teacher, self.lemma_see, self.lemma_yesterday])
        self.session.flush()

        # Sentence: "We saw the teacher yesterday."
        self.sentence = Sentence(pattern_type="guided", tense="past")
        self.session.add(self.sentence)
        self.session.flush()

        # English translation
        self.session.add(
            SentenceTranslation(
                sentence_id=self.sentence.id,
                language_code="en",
                translation_text="We saw the teacher yesterday.",
            )
        )

        # Pattern words (from guided generation) - with GUIDs
        self.session.add_all(
            [
                SentencePatternWord(
                    sentence_id=self.sentence.id,
                    lemma_id=self.lemma_see.id,
                    position=0,
                    slot_name="verb",
                    english_text="see",
                ),
                SentencePatternWord(
                    sentence_id=self.sentence.id,
                    lemma_id=self.lemma_teacher.id,
                    position=1,
                    slot_name="noun",
                    english_text="teacher",
                ),
                SentencePatternWord(
                    sentence_id=self.sentence.id,
                    lemma_id=self.lemma_yesterday.id,
                    position=2,
                    slot_name="other",
                    english_text="yesterday",
                ),
            ]
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_resolves_all_pattern_words_via_guid(self) -> None:
        """All pattern words with lemma_id should resolve via GUID."""
        results = resolve_lemmas_for_sentence(self.session, self.sentence.id)

        self.assertEqual(len(results), 3)
        for resolved in results:
            self.assertIsNotNone(resolved.lemma)
            self.assertEqual(resolved.method, "guid")
            self.assertEqual(resolved.confidence, 1.0)

    def test_positions_and_slots_preserved(self) -> None:
        results = resolve_lemmas_for_sentence(self.session, self.sentence.id)

        self.assertEqual(results[0].position, 0)
        self.assertEqual(results[0].slot_name, "verb")
        self.assertEqual(results[0].english_text, "see")

        self.assertEqual(results[1].position, 1)
        self.assertEqual(results[1].slot_name, "noun")
        self.assertEqual(results[1].english_text, "teacher")

        self.assertEqual(results[2].position, 2)
        self.assertEqual(results[2].slot_name, "other")
        self.assertEqual(results[2].english_text, "yesterday")

    def test_null_lemma_pattern_word_falls_to_text(self) -> None:
        """Pattern word with no lemma_id should fall through to text match."""
        # Add a pattern word without lemma_id (like "work horse" in the examples)
        # Need a pending_import to satisfy the check constraint
        from storage.models.imports import PendingImport

        pending = PendingImport(
            english_word="shape",
            definition="a geometric form",
            disambiguation_translation="forma",
            disambiguation_language="lt",
            pos_type="noun",
            source="test",
        )
        self.session.add(pending)
        self.session.flush()

        pw = SentencePatternWord(
            sentence_id=self.sentence.id,
            pending_import_id=pending.id,
            position=3,
            slot_name="noun",
            english_text="shape",
        )
        self.session.add(pw)
        self.session.commit()

        results = resolve_lemmas_for_sentence(self.session, self.sentence.id)

        # 4 results: 3 with GUID + 1 text-based
        self.assertEqual(len(results), 4)
        shape_result = results[3]
        self.assertEqual(shape_result.english_text, "shape")
        # "shape" is not in our test DB, so unresolved
        self.assertEqual(shape_result.method, "unresolved")
        self.assertIsNone(shape_result.lemma)


class TestResolveLemmasForSentenceFromWords(unittest.TestCase):
    """Test resolve_lemmas_for_sentence when only sentence_words exist (no pattern)."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.lemma_teacher = Lemma(
            lemma_text="teacher",
            definition_text="a person who teaches",
            pos_type="noun",
            guid="N36_014",
        )
        self.session.add(self.lemma_teacher)
        self.session.flush()

        # Sentence with only sentence_words (no pattern_words)
        self.sentence = Sentence(pattern_type="SVO", tense="present")
        self.session.add(self.sentence)
        self.session.flush()

        self.session.add(
            SentenceTranslation(
                sentence_id=self.sentence.id,
                language_code="en",
                translation_text="The teacher spoke.",
            )
        )

        # Sentence words for English with lemma linked
        self.session.add(
            SentenceWord(
                sentence_id=self.sentence.id,
                lemma_id=self.lemma_teacher.id,
                language_code="en",
                position=0,
                part_of_speech="noun",
                english_text="teacher",
                declined_form="teacher",
            )
        )
        # Word without lemma
        self.session.add(
            SentenceWord(
                sentence_id=self.sentence.id,
                language_code="en",
                position=1,
                part_of_speech="verb",
                english_text="spoke",
                declined_form="spoke",
            )
        )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def test_resolves_from_sentence_words(self) -> None:
        """When no pattern_words exist, sentence_words are used."""
        results = resolve_lemmas_for_sentence(self.session, self.sentence.id)

        self.assertEqual(len(results), 2)
        # "teacher" should resolve via GUID from the linked lemma
        self.assertEqual(results[0].english_text, "teacher")
        self.assertIsNotNone(results[0].lemma)
        assert results[0].lemma is not None
        self.assertEqual(results[0].lemma.guid, "N36_014")

        # "spoke" - no lemma in DB, unresolved
        self.assertEqual(results[1].english_text, "spoke")
        self.assertIsNone(results[1].lemma)

    def test_deduplicates_by_english_text(self) -> None:
        """Same english_text across languages should not produce duplicates."""
        # Add French sentence word for same english_text "teacher"
        self.session.add(
            SentenceWord(
                sentence_id=self.sentence.id,
                language_code="fr",
                position=0,
                part_of_speech="noun",
                english_text="teacher",
                declined_form="professeur",
            )
        )
        self.session.commit()

        results = resolve_lemmas_for_sentence(self.session, self.sentence.id)

        # Should still be 2 results, not 3
        self.assertEqual(len(results), 2)


class TestWordRoleToPosMapping(unittest.TestCase):
    """Test the PART_OF_SPEECH_TO_POS constant for completeness."""

    def test_verb_maps_to_verb(self) -> None:
        self.assertEqual(PART_OF_SPEECH_TO_POS["verb"], "verb")

    def test_adjective_maps_to_adjective(self) -> None:
        self.assertEqual(PART_OF_SPEECH_TO_POS["adjective"], "adjective")

    def test_adverb_maps_to_adverb(self) -> None:
        self.assertEqual(PART_OF_SPEECH_TO_POS["adverb"], "adverb")

    def test_other_has_no_pos_filter(self) -> None:
        self.assertEqual(PART_OF_SPEECH_TO_POS["other"], "")


if __name__ == "__main__":
    unittest.main()
