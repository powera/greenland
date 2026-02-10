#!/usr/bin/env python3
"""
Tests for wordfreq.tools.sentence_analysis module.

Tests the sentence analysis utilities for finding lemma associations.
Uses in-memory SQLite for realistic query testing.
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
    SentenceWord,
)
from sentences.analysis import (
    SUBSTRING_MATCH_LANGUAGES,
    _forms_match,
    discover_and_store_lemmas,
    find_candidate_lemmas_for_sentence,
    store_discovered_lemmas,
)


class TestFormsMatch(unittest.TestCase):
    """Test the _forms_match helper function (pure Python, no DB)."""

    def test_exact_match_case_insensitive(self):
        """Test case-insensitive exact matching for regular languages."""
        self.assertTrue(_forms_match("Hello", "hello", "en"))
        self.assertTrue(_forms_match("HELLO", "hello", "en"))
        self.assertTrue(_forms_match("hello", "HELLO", "en"))

    def test_exact_match_same_case(self):
        """Test exact matching with same case."""
        self.assertTrue(_forms_match("mangé", "mangé", "fr"))

    def test_no_match_different_words(self):
        """Test that different words don't match."""
        self.assertFalse(_forms_match("hello", "goodbye", "en"))
        self.assertFalse(_forms_match("manger", "parler", "fr"))

    def test_substring_match_chinese(self):
        """Test substring matching for Chinese."""
        # Chinese should match if one contains the other
        self.assertTrue(_forms_match("吃", "吃饭", "zh"))
        self.assertTrue(_forms_match("吃饭", "吃", "zh"))
        self.assertTrue(_forms_match("吃", "吃", "zh"))

    def test_substring_match_japanese(self):
        """Test substring matching for Japanese."""
        self.assertTrue(_forms_match("食べ", "食べる", "ja"))
        self.assertTrue(_forms_match("食べる", "食べ", "ja"))

    def test_substring_match_korean(self):
        """Test substring matching for Korean."""
        self.assertTrue(_forms_match("먹", "먹다", "ko"))
        self.assertTrue(_forms_match("먹다", "먹", "ko"))

    def test_no_substring_match_for_non_logographic(self):
        """Test that substring matching doesn't apply to non-CJK languages."""
        # "eat" is contained in "eating" but should not match for English
        self.assertFalse(_forms_match("eat", "eating", "en"))
        self.assertFalse(_forms_match("eating", "eat", "en"))
        # Same for French
        self.assertFalse(_forms_match("mang", "manger", "fr"))

    def test_substring_match_languages_constant(self):
        """Test that the SUBSTRING_MATCH_LANGUAGES constant is correct."""
        self.assertEqual(SUBSTRING_MATCH_LANGUAGES, {"zh", "ja", "ko"})


class TestFindCandidateLemmasForSentence(unittest.TestCase):
    """Test find_candidate_lemmas_for_sentence with in-memory SQLite."""

    def setUp(self):
        """Set up in-memory SQLite database with test data."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Create test lemmas
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
        self.lemma_drink = Lemma(
            lemma_text="drink",
            definition_text="to consume liquid",
            pos_type="verb",
            guid="V01_002",
        )
        self.session.add_all([self.lemma_eat, self.lemma_apple, self.lemma_drink])
        self.session.flush()

        # Create derivative forms for "eat" lemma in multiple languages
        self.session.add_all(
            [
                DerivativeForm(
                    lemma_id=self.lemma_eat.id,
                    derivative_form_text="eats",
                    language_code="en",
                    grammatical_form="3s_present",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_eat.id,
                    derivative_form_text="mange",
                    language_code="fr",
                    grammatical_form="3s_present",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_eat.id,
                    derivative_form_text="吃",
                    language_code="zh",
                    grammatical_form="base",
                ),
            ]
        )

        # Create derivative forms for "apple" lemma
        self.session.add_all(
            [
                DerivativeForm(
                    lemma_id=self.lemma_apple.id,
                    derivative_form_text="apple",
                    language_code="en",
                    grammatical_form="singular",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_apple.id,
                    derivative_form_text="pomme",
                    language_code="fr",
                    grammatical_form="singular",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_apple.id,
                    derivative_form_text="苹果",
                    language_code="zh",
                    grammatical_form="base",
                ),
            ]
        )

        # Create a test sentence
        self.sentence = Sentence(pattern_type="SVO", tense="present")
        self.session.add(self.sentence)
        self.session.flush()

        # Create sentence words (multilingual word breakdown)
        # Sentence: "He eats an apple" / "Il mange une pomme" / "他吃苹果"
        self.session.add_all(
            [
                # English breakdown
                SentenceWord(
                    sentence_id=self.sentence.id,
                    language_code="en",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="eats",
                ),
                SentenceWord(
                    sentence_id=self.sentence.id,
                    language_code="en",
                    position=1,
                    word_role="object",
                    english_text="apple",
                    declined_form="apple",
                ),
                # French breakdown
                SentenceWord(
                    sentence_id=self.sentence.id,
                    language_code="fr",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="mange",
                ),
                SentenceWord(
                    sentence_id=self.sentence.id,
                    language_code="fr",
                    position=1,
                    word_role="object",
                    english_text="apple",
                    declined_form="pomme",
                ),
                # Chinese breakdown
                SentenceWord(
                    sentence_id=self.sentence.id,
                    language_code="zh",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="吃",
                ),
                SentenceWord(
                    sentence_id=self.sentence.id,
                    language_code="zh",
                    position=1,
                    word_role="object",
                    english_text="apple",
                    declined_form="苹果",
                ),
            ]
        )
        self.session.commit()

    def tearDown(self):
        """Clean up database session."""
        self.session.close()

    def test_finds_matching_lemmas(self):
        """Test that matching lemmas are found across languages."""
        candidates = find_candidate_lemmas_for_sentence(
            self.session, self.sentence.id, min_language_matches=2
        )

        # Should find both "eat" and "apple" lemmas
        self.assertEqual(len(candidates), 2)
        lemma_texts = {c["lemma"].lemma_text for c in candidates}
        self.assertEqual(lemma_texts, {"eat", "apple"})

    def test_respects_min_language_matches(self):
        """Test that min_language_matches threshold is respected."""
        # With min_language_matches=3, should find both (they match in 3 languages)
        candidates = find_candidate_lemmas_for_sentence(
            self.session, self.sentence.id, min_language_matches=3
        )
        self.assertEqual(len(candidates), 2)

        # With min_language_matches=4, should find none
        candidates = find_candidate_lemmas_for_sentence(
            self.session, self.sentence.id, min_language_matches=4
        )
        self.assertEqual(len(candidates), 0)

    def test_returns_matched_languages(self):
        """Test that matched languages are correctly reported."""
        candidates = find_candidate_lemmas_for_sentence(
            self.session, self.sentence.id, min_language_matches=2
        )

        for candidate in candidates:
            # Each lemma should have matched in all 3 languages
            self.assertEqual(len(candidate["matched_languages"]), 3)
            self.assertEqual(set(candidate["matched_languages"]), {"en", "fr", "zh"})

    def test_returns_english_text_and_word_role(self):
        """Test that english_text and word_role are correctly returned."""
        candidates = find_candidate_lemmas_for_sentence(
            self.session, self.sentence.id, min_language_matches=2
        )

        eat_candidate = next(c for c in candidates if c["lemma"].lemma_text == "eat")
        self.assertEqual(eat_candidate["english_text"], "eat")
        self.assertEqual(eat_candidate["word_role"], "verb")

        apple_candidate = next(c for c in candidates if c["lemma"].lemma_text == "apple")
        self.assertEqual(apple_candidate["english_text"], "apple")
        self.assertEqual(apple_candidate["word_role"], "object")

    def test_case_insensitive_matching(self):
        """Test that matching is case-insensitive for non-CJK languages."""
        # Add a sentence word with different case
        sentence2 = Sentence(pattern_type="SVO", tense="present")
        self.session.add(sentence2)
        self.session.flush()

        self.session.add_all(
            [
                SentenceWord(
                    sentence_id=sentence2.id,
                    language_code="en",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="EATS",  # Uppercase
                ),
                SentenceWord(
                    sentence_id=sentence2.id,
                    language_code="fr",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="Mange",  # Mixed case
                ),
            ]
        )
        self.session.commit()

        candidates = find_candidate_lemmas_for_sentence(
            self.session, sentence2.id, min_language_matches=2
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["lemma"].lemma_text, "eat")

    def test_skips_words_with_existing_lemma(self):
        """Test that words already linked to a lemma are skipped."""
        # Create a sentence where one word already has a lemma
        sentence2 = Sentence(pattern_type="SVO", tense="present")
        self.session.add(sentence2)
        self.session.flush()

        self.session.add_all(
            [
                # This word already has a lemma assigned
                SentenceWord(
                    sentence_id=sentence2.id,
                    language_code="en",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="eats",
                    lemma_id=self.lemma_eat.id,
                ),
                SentenceWord(
                    sentence_id=sentence2.id,
                    language_code="fr",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="mange",
                    lemma_id=self.lemma_eat.id,
                ),
                # This word doesn't have a lemma
                SentenceWord(
                    sentence_id=sentence2.id,
                    language_code="en",
                    position=1,
                    word_role="object",
                    english_text="apple",
                    declined_form="apple",
                ),
                SentenceWord(
                    sentence_id=sentence2.id,
                    language_code="fr",
                    position=1,
                    word_role="object",
                    english_text="apple",
                    declined_form="pomme",
                ),
            ]
        )
        self.session.commit()

        candidates = find_candidate_lemmas_for_sentence(
            self.session, sentence2.id, min_language_matches=2
        )

        # Should only find "apple" since "eat" is already linked
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["lemma"].lemma_text, "apple")

    def test_empty_sentence_returns_empty(self):
        """Test that a sentence with no words returns empty list."""
        empty_sentence = Sentence(pattern_type="SVO", tense="present")
        self.session.add(empty_sentence)
        self.session.commit()

        candidates = find_candidate_lemmas_for_sentence(
            self.session, empty_sentence.id, min_language_matches=2
        )

        self.assertEqual(candidates, [])

    def test_no_matching_forms_returns_empty(self):
        """Test that sentence with no matching derivative forms returns empty."""
        sentence2 = Sentence(pattern_type="SVO", tense="present")
        self.session.add(sentence2)
        self.session.flush()

        self.session.add_all(
            [
                SentenceWord(
                    sentence_id=sentence2.id,
                    language_code="en",
                    position=0,
                    word_role="verb",
                    english_text="nonexistent",
                    declined_form="nonexistent_form",
                ),
            ]
        )
        self.session.commit()

        candidates = find_candidate_lemmas_for_sentence(
            self.session, sentence2.id, min_language_matches=1
        )

        self.assertEqual(candidates, [])


class TestStoreDiscoveredLemmas(unittest.TestCase):
    """Test store_discovered_lemmas function."""

    def setUp(self):
        """Set up in-memory SQLite database with test data."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Create test lemmas
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
        self.session.add_all([self.lemma_eat, self.lemma_apple])
        self.session.flush()

        # Create a test sentence
        self.sentence = Sentence(pattern_type="SVO", tense="present")
        self.session.add(self.sentence)
        self.session.commit()

    def tearDown(self):
        """Clean up database session."""
        self.session.close()

    def test_stores_discovered_lemmas(self):
        """Test that discovered lemmas are stored correctly."""
        candidates = [
            {
                "lemma": self.lemma_eat,
                "english_text": "eat",
                "matched_languages": ["en", "fr"],
                "word_role": "verb",
            },
            {
                "lemma": self.lemma_apple,
                "english_text": "apple",
                "matched_languages": ["en", "fr"],
                "word_role": "object",
            },
        ]

        added = store_discovered_lemmas(self.session, self.sentence.id, candidates, commit=True)

        self.assertEqual(added, 2)

        # Verify stored pattern words
        pattern_words = (
            self.session.query(SentencePatternWord)
            .filter(SentencePatternWord.sentence_id == self.sentence.id)
            .order_by(SentencePatternWord.position)
            .all()
        )

        self.assertEqual(len(pattern_words), 2)
        self.assertEqual(pattern_words[0].lemma_id, self.lemma_eat.id)
        self.assertEqual(pattern_words[0].slot_name, "discovered")
        self.assertEqual(pattern_words[0].english_text, "eat")
        self.assertEqual(pattern_words[0].position, 0)

        self.assertEqual(pattern_words[1].lemma_id, self.lemma_apple.id)
        self.assertEqual(pattern_words[1].slot_name, "discovered")
        self.assertEqual(pattern_words[1].english_text, "apple")
        self.assertEqual(pattern_words[1].position, 1)

    def test_skips_existing_lemmas(self):
        """Test that already-associated lemmas are skipped."""
        # Pre-add one lemma as a pattern word
        existing = SentencePatternWord(
            sentence_id=self.sentence.id,
            lemma_id=self.lemma_eat.id,
            position=0,
            slot_name="verb",
            english_text="eat",
        )
        self.session.add(existing)
        self.session.commit()

        candidates = [
            {
                "lemma": self.lemma_eat,  # Already exists
                "english_text": "eat",
                "matched_languages": ["en", "fr"],
                "word_role": "verb",
            },
            {
                "lemma": self.lemma_apple,  # New
                "english_text": "apple",
                "matched_languages": ["en", "fr"],
                "word_role": "object",
            },
        ]

        added = store_discovered_lemmas(self.session, self.sentence.id, candidates, commit=True)

        self.assertEqual(added, 1)  # Only apple should be added

        pattern_words = (
            self.session.query(SentencePatternWord)
            .filter(SentencePatternWord.sentence_id == self.sentence.id)
            .all()
        )
        self.assertEqual(len(pattern_words), 2)

    def test_empty_candidates_does_nothing(self):
        """Test that empty candidates list doesn't add anything."""
        added = store_discovered_lemmas(self.session, self.sentence.id, [], commit=True)

        self.assertEqual(added, 0)

        pattern_words = (
            self.session.query(SentencePatternWord)
            .filter(SentencePatternWord.sentence_id == self.sentence.id)
            .all()
        )
        self.assertEqual(len(pattern_words), 0)

    def test_continues_position_from_existing(self):
        """Test that position continues from existing pattern words."""
        # Pre-add some pattern words
        for i in range(3):
            pw = SentencePatternWord(
                sentence_id=self.sentence.id,
                lemma_id=self.lemma_eat.id if i == 0 else self.lemma_apple.id,
                position=i,
                slot_name="existing",
                english_text=f"word{i}",
            )
            self.session.add(pw)
        self.session.commit()

        # Create a new lemma to add
        new_lemma = Lemma(
            lemma_text="new",
            definition_text="new word",
            pos_type="noun",
            guid="N01_002",
        )
        self.session.add(new_lemma)
        self.session.commit()

        candidates = [
            {
                "lemma": new_lemma,
                "english_text": "new",
                "matched_languages": ["en"],
                "word_role": "object",
            },
        ]

        added = store_discovered_lemmas(self.session, self.sentence.id, candidates, commit=True)

        self.assertEqual(added, 1)

        # The new pattern word should have position 3
        new_pw = (
            self.session.query(SentencePatternWord)
            .filter(SentencePatternWord.lemma_id == new_lemma.id)
            .first()
        )
        self.assertEqual(new_pw.position, 3)


class TestDiscoverAndStoreLemmas(unittest.TestCase):
    """Test the discover_and_store_lemmas convenience function."""

    def setUp(self):
        """Set up in-memory SQLite database with test data."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Create test lemmas
        self.lemma_eat = Lemma(
            lemma_text="eat",
            definition_text="to consume food",
            pos_type="verb",
            guid="V01_001",
        )
        self.session.add(self.lemma_eat)
        self.session.flush()

        # Create derivative forms
        self.session.add_all(
            [
                DerivativeForm(
                    lemma_id=self.lemma_eat.id,
                    derivative_form_text="eats",
                    language_code="en",
                    grammatical_form="3s_present",
                ),
                DerivativeForm(
                    lemma_id=self.lemma_eat.id,
                    derivative_form_text="mange",
                    language_code="fr",
                    grammatical_form="3s_present",
                ),
            ]
        )

        # Create a test sentence with matching words
        self.sentence = Sentence(pattern_type="SVO", tense="present")
        self.session.add(self.sentence)
        self.session.flush()

        self.session.add_all(
            [
                SentenceWord(
                    sentence_id=self.sentence.id,
                    language_code="en",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="eats",
                ),
                SentenceWord(
                    sentence_id=self.sentence.id,
                    language_code="fr",
                    position=0,
                    word_role="verb",
                    english_text="eat",
                    declined_form="mange",
                ),
            ]
        )
        self.session.commit()

    def tearDown(self):
        """Clean up database session."""
        self.session.close()

    def test_discovers_and_stores_lemmas(self):
        """Test the combined discover and store operation."""
        result = discover_and_store_lemmas(
            self.session, self.sentence.id, min_language_matches=2, commit=True
        )

        self.assertEqual(result["found"], 1)
        self.assertEqual(result["added"], 1)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["lemma"].lemma_text, "eat")

        # Verify stored
        pattern_words = (
            self.session.query(SentencePatternWord)
            .filter(SentencePatternWord.sentence_id == self.sentence.id)
            .all()
        )
        self.assertEqual(len(pattern_words), 1)

    def test_reports_already_linked(self):
        """Test that already-linked lemmas are found but not re-added."""
        # First run
        result1 = discover_and_store_lemmas(
            self.session, self.sentence.id, min_language_matches=2, commit=True
        )
        self.assertEqual(result1["found"], 1)
        self.assertEqual(result1["added"], 1)

        # Second run - should find but not add
        result2 = discover_and_store_lemmas(
            self.session, self.sentence.id, min_language_matches=2, commit=True
        )
        self.assertEqual(result2["found"], 1)
        self.assertEqual(result2["added"], 0)  # Already exists


class TestSubstringMatchingChinese(unittest.TestCase):
    """Test substring matching for Chinese specifically."""

    def setUp(self):
        """Set up in-memory SQLite database with Chinese test data."""
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        # Create a lemma for "eat" with Chinese forms
        self.lemma_eat = Lemma(
            lemma_text="eat",
            definition_text="to consume food",
            pos_type="verb",
            guid="V01_001",
        )
        self.session.add(self.lemma_eat)
        self.session.flush()

        # Add Chinese derivative form "吃饭" (eat rice/meal)
        self.session.add(
            DerivativeForm(
                lemma_id=self.lemma_eat.id,
                derivative_form_text="吃饭",
                language_code="zh",
                grammatical_form="base",
            )
        )

        # Create sentence with just "吃" (substring of "吃饭")
        self.sentence = Sentence(pattern_type="SVO", tense="present")
        self.session.add(self.sentence)
        self.session.flush()

        self.session.add(
            SentenceWord(
                sentence_id=self.sentence.id,
                language_code="zh",
                position=0,
                word_role="verb",
                english_text="eat",
                declined_form="吃",  # Substring of derivative form "吃饭"
            )
        )
        self.session.commit()

    def tearDown(self):
        """Clean up database session."""
        self.session.close()

    def test_matches_substring_in_chinese(self):
        """Test that Chinese substring matching works."""
        candidates = find_candidate_lemmas_for_sentence(
            self.session, self.sentence.id, min_language_matches=1
        )

        # Should find "eat" even though sentence has "吃" and derivative has "吃饭"
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["lemma"].lemma_text, "eat")


if __name__ == "__main__":
    unittest.main()
