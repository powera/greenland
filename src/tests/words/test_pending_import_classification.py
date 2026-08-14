#!/usr/bin/env python3
"""Tests for deciding what a staged term becomes.

The rule tier runs on every staging path, so its answers are what keep "George"
out of the vocabulary queue without an LLM call. The behaviours worth
protecting: an existing row always wins over a shape guess, a sentence-initial
capital is not evidence, and a malformed LLM answer degrades to "lemma" rather
than raising.
"""

import unittest
from typing import Any, Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.concept import create_concept
from storage.crud.name_entity import create_name
from storage.models.imports import (
    TARGET_KIND_CONCEPT,
    TARGET_KIND_LEMMA,
    TARGET_KIND_NAME,
    PendingImport,
)
from storage.models.schema import Base, Lemma
from words.pending_imports.classification import (
    classify_pending_import,
    looks_like_proper_noun,
    parse_classification_response,
    suggest_target_kind,
)
from words.pending_imports.staging import create_pending_import


class StubResponse:
    """Minimal stand-in for a structured LLM response."""

    def __init__(self, structured_data: Optional[Dict[str, Any]]) -> None:
        self.structured_data = structured_data


class StubClient:
    """LLM client that returns one canned structured response."""

    def __init__(self, structured_data: Optional[Dict[str, Any]]) -> None:
        self.structured_data = structured_data
        self.calls = 0

    def generate_chat(self, **kwargs: Any) -> StubResponse:
        self.calls += 1
        return StubResponse(self.structured_data)


class ClassificationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()

    def stage(self, word: str, **kwargs: Any) -> PendingImport:
        return create_pending_import(
            self.session,
            english_word=word,
            definition=kwargs.pop("definition", word),
            disambiguation_translation=word,
            disambiguation_language="en",
            **kwargs,
        )


class TestProperNounShape(unittest.TestCase):
    def test_a_lowercase_word_is_not_proper(self) -> None:
        self.assertFalse(looks_like_proper_noun("aardvark"))

    def test_a_capitalized_word_is_proper(self) -> None:
        self.assertTrue(looks_like_proper_noun("George"))

    def test_a_sentence_initial_capital_is_not_evidence(self) -> None:
        """ "Bread is expensive" capitalizes bread for position, not for sense."""
        self.assertFalse(looks_like_proper_noun("Bread", "Bread is expensive."))

    def test_a_capital_elsewhere_in_the_sentence_still_counts(self) -> None:
        self.assertTrue(looks_like_proper_noun("George", "I saw George today."))

    def test_several_capitalized_words_are_proper_anywhere(self) -> None:
        self.assertTrue(looks_like_proper_noun("World War", "World War II ended in 1945."))

    def test_an_inner_capital_is_proper_anywhere(self) -> None:
        self.assertTrue(looks_like_proper_noun("McDonald", "McDonald arrived."))

    def test_empty_text_is_not_proper(self) -> None:
        self.assertFalse(looks_like_proper_noun("   "))


class TestRuleTier(ClassificationTestCase):
    def test_an_ordinary_word_is_vocabulary(self) -> None:
        suggestion = suggest_target_kind(self.session, "aardvark")
        self.assertEqual(suggestion.target_kind, TARGET_KIND_LEMMA)

    def test_a_capitalized_word_is_a_name(self) -> None:
        suggestion = suggest_target_kind(self.session, "George")
        self.assertEqual(suggestion.target_kind, TARGET_KIND_NAME)
        self.assertFalse(suggestion.is_certain)

    def test_an_existing_name_wins_and_carries_its_kind(self) -> None:
        create_name(self.session, name_text="George", kind="given_name")
        self.session.commit()

        suggestion = suggest_target_kind(self.session, "George")

        self.assertEqual(suggestion.target_kind, TARGET_KIND_NAME)
        self.assertEqual(suggestion.name_kind, "given_name")
        self.assertTrue(suggestion.is_certain)

    def test_an_existing_concept_wins(self) -> None:
        create_concept(self.session, title="Art Deco", concept_type="art_movement")

        suggestion = suggest_target_kind(self.session, "Art Deco")

        self.assertEqual(suggestion.target_kind, TARGET_KIND_CONCEPT)
        self.assertEqual(suggestion.concept_type, "art_movement")
        self.assertTrue(suggestion.is_certain)

    def test_an_existing_lemma_wins_over_capitalization(self) -> None:
        """ "Frank" the adjective is vocabulary, however the corpus wrote it."""
        self.session.add(
            Lemma(
                lemma_text="Frank",
                definition_text="open and honest",
                pos_type="adjective",
                guid="A01_001",
            )
        )
        self.session.commit()

        suggestion = suggest_target_kind(self.session, "Frank")

        self.assertEqual(suggestion.target_kind, TARGET_KIND_LEMMA)
        self.assertTrue(suggestion.is_certain)

    def test_a_verb_is_vocabulary_whatever_its_capitalization(self) -> None:
        suggestion = suggest_target_kind(self.session, "Sprint", pos_type="verb")
        self.assertEqual(suggestion.target_kind, TARGET_KIND_LEMMA)


class TestStagingAppliesTheRuleTier(ClassificationTestCase):
    def test_a_proper_noun_is_staged_as_a_name(self) -> None:
        pending = self.stage("George", example_sentence="I saw George today.")
        self.assertEqual(pending.target_kind, TARGET_KIND_NAME)

    def test_an_ordinary_word_is_staged_as_a_lemma(self) -> None:
        pending = self.stage("aardvark")
        self.assertEqual(pending.target_kind, TARGET_KIND_LEMMA)

    def test_an_explicit_kind_is_not_second_guessed(self) -> None:
        pending = self.stage("George", target_kind=TARGET_KIND_LEMMA)
        self.assertEqual(pending.target_kind, TARGET_KIND_LEMMA)

    def test_classification_can_be_switched_off(self) -> None:
        pending = self.stage("George", classify=False)
        self.assertEqual(pending.target_kind, TARGET_KIND_LEMMA)


class TestParsingTheLLMAnswer(unittest.TestCase):
    def test_a_name_answer_keeps_its_kind_and_gender(self) -> None:
        suggestion = parse_classification_response(
            {
                "target_kind": "name",
                "name_kind": "given_name",
                "gender": "masculine",
                "explanation": "a person",
            }
        )
        self.assertEqual(suggestion.target_kind, TARGET_KIND_NAME)
        self.assertEqual(suggestion.name_kind, "given_name")
        self.assertEqual(suggestion.gender, "masculine")

    def test_a_name_kind_on_a_lemma_answer_is_discarded(self) -> None:
        """The fields only mean anything for their own kind."""
        suggestion = parse_classification_response(
            {"target_kind": "lemma", "name_kind": "given_name"}
        )
        self.assertIsNone(suggestion.name_kind)

    def test_an_unknown_name_kind_is_dropped(self) -> None:
        suggestion = parse_classification_response(
            {"target_kind": "name", "name_kind": "spaceship"}
        )
        self.assertEqual(suggestion.target_kind, TARGET_KIND_NAME)
        self.assertIsNone(suggestion.name_kind)

    def test_an_unusable_answer_falls_back_to_vocabulary(self) -> None:
        """Staging vocabulary is the reversible option, so it is the fallback."""
        suggestion = parse_classification_response({"target_kind": "sandwich"})
        self.assertEqual(suggestion.target_kind, TARGET_KIND_LEMMA)


class TestLLMTier(ClassificationTestCase):
    def test_the_verdict_is_stored_on_the_row(self) -> None:
        pending = self.stage("aardvark")
        client = StubClient(
            {"target_kind": "concept", "concept_type": "event", "explanation": "a topic"}
        )

        suggestion = classify_pending_import(self.session, pending, client, model="test-model")

        self.assertEqual(suggestion.target_kind, TARGET_KIND_CONCEPT)
        self.assertEqual(pending.target_kind, TARGET_KIND_CONCEPT)
        self.assertEqual(pending.concept_type, "event")

    def test_a_failed_call_falls_back_to_the_rule_tier(self) -> None:
        """A model that cannot be reached must not block the stage."""
        pending = self.stage("George", example_sentence="I saw George today.")
        client = StubClient(None)  # No structured data -> the query raises.

        suggestion = classify_pending_import(self.session, pending, client, model="test-model")

        self.assertEqual(client.calls, 1)
        self.assertEqual(suggestion.target_kind, TARGET_KIND_NAME)
        self.assertEqual(pending.target_kind, TARGET_KIND_NAME)


if __name__ == "__main__":
    unittest.main()
