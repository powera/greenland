#!/usr/bin/env python3
"""Tests for sentences.candidate_lookup.

Uses the shared fixture in candidate_lookup_fixture.py to seed an in-memory
SQLite DB with ~50 real release lemmas plus hand-authored ambiguous entries.
The lookup is multi-language: candidates are sourced from every translation
in the configured source languages and ranked by the count of those
languages that confirm each candidate.
"""

import unittest
from typing import ClassVar, Dict, List

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from sentences.candidate_lookup import (
    CandidateLemma,
    DEFAULT_SOURCE_LANGUAGES,
    find_candidate_lemmas_for_sentence,
    find_candidate_lemmas_from_translations,
)
from tests.sentences.candidate_lookup_fixture import (
    add_test_sentence,
    build_test_engine,
    seed_test_database,
)


def _guids(candidates: List[CandidateLemma]) -> List[str]:
    return [c.guid for c in candidates]


def _find_guid(candidates: List[CandidateLemma], guid: str) -> CandidateLemma:
    for candidate in candidates:
        if candidate.guid == guid:
            return candidate
    raise AssertionError(f"GUID {guid} not found among {_guids(candidates)}")


class CandidateLookupTestCase(unittest.TestCase):
    """Shared fixture bootstrap for candidate-lookup tests."""

    engine: ClassVar[Engine]
    seed_summary: ClassVar[Dict[str, int]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = build_test_engine()
        with Session(cls.engine) as session:
            cls.seed_summary = seed_test_database(session)

    def setUp(self) -> None:
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)


class TestFixtureIntegrity(CandidateLookupTestCase):
    def test_seed_loaded_enough_release_lemmas(self) -> None:
        self.assertGreaterEqual(
            self.seed_summary["release_lemmas"],
            40,
            "Expected at least 40 release lemmas in the seeded fixture",
        )

    def test_custom_lemmas_present(self) -> None:
        self.assertEqual(self.seed_summary["custom_lemmas"], 4)


class TestUnambiguousWord(CandidateLookupTestCase):
    def test_dog_candidate_returned(self) -> None:
        sentence = add_test_sentence(
            self.session,
            {"en": "The dog runs", "bn": "কুকুর দৌড়ায়", "uk": "Собака біжить", "kn": "ನಾಯಿ ಓಡುತ್ತದೆ"},
        )
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        dog = _find_guid(candidates, _release_dog_guid(self.session))
        self.assertEqual(dog.lemma_text, "dog")
        self.assertEqual(dog.pos, "noun")
        self.assertGreaterEqual(dog.match_score, 1)

    def test_translations_populated_for_source_languages(self) -> None:
        sentence = add_test_sentence(
            self.session,
            {"en": "The dog runs", "bn": "কুকুর দৌড়ায়"},
        )
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        dog = _find_guid(candidates, _release_dog_guid(self.session))
        # Release base entries include fr/es/lt/zh.
        for lang in ("fr", "es", "lt"):
            self.assertIn(lang, dog.translations)


class TestAmbiguityResolution(CandidateLookupTestCase):
    def test_modal_can_outranks_container_when_pivots_confirm_modal(self) -> None:
        sentence = add_test_sentence(
            self.session,
            {
                "en": "I can play today",
                "bn": "আমি আজ পারা",
                "uk": "Я можу грати сьогодні",
                "kn": "ನಾನು ಇಂದು ಸಾಧ್ಯ ಆಡಲು",
            },
        )
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        # Both senses come from the English token "can"; modal must score higher.
        modal = _find_guid(candidates, "TEST_CAN_MODAL")
        # Container may or may not be present depending on cap, but if it is,
        # its score must be strictly less than modal's.
        modal_idx = _guids(candidates).index("TEST_CAN_MODAL")
        if "TEST_CAN_CONTAINER" in _guids(candidates):
            container_idx = _guids(candidates).index("TEST_CAN_CONTAINER")
            self.assertLess(modal_idx, container_idx)
        self.assertGreaterEqual(modal.match_score, 1)

    def test_container_can_outranks_modal_when_pivots_confirm_container(self) -> None:
        sentence = add_test_sentence(
            self.session,
            {
                "en": "I see a can",
                "bn": "আমি একটি ক্যান দেখি",
                "uk": "Я бачу банка",
                "kn": "ನಾನು ಒಂದು ಕ್ಯಾನ್ ನೋಡುತ್ತೇನೆ",
            },
        )
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        container = _find_guid(candidates, "TEST_CAN_CONTAINER")
        container_idx = _guids(candidates).index("TEST_CAN_CONTAINER")
        if "TEST_CAN_MODAL" in _guids(candidates):
            modal_idx = _guids(candidates).index("TEST_CAN_MODAL")
            self.assertLess(container_idx, modal_idx)
        self.assertGreaterEqual(container.match_score, 1)


class TestNoExtraEvidence(CandidateLookupTestCase):
    def test_english_only_sentence_returns_both_senses_with_score_one(self) -> None:
        sentence = add_test_sentence(self.session, {"en": "I can play today"})
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        guids = set(_guids(candidates))
        # Both senses surface because both have lemma_text="can".
        self.assertIn("TEST_CAN_MODAL", guids)
        self.assertIn("TEST_CAN_CONTAINER", guids)
        for guid in ("TEST_CAN_MODAL", "TEST_CAN_CONTAINER"):
            candidate = _find_guid(candidates, guid)
            # English alone confirms the lemma_text match.
            self.assertEqual(candidate.match_score, 1)
            self.assertEqual(candidate.matched_languages, ["en"])


class TestMultiLanguageSourcing(CandidateLookupTestCase):
    def test_non_english_translation_can_source_a_candidate(self) -> None:
        # Sentence with no English translation at all: candidates should still
        # be sourced from the other languages' tokens.
        sentence = add_test_sentence(
            self.session,
            {"fr": "Le chien court", "es": "El perro corre"},
        )
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        # "dog" lemma's fr translation is "chien"; should be found.
        guids = set(_guids(candidates))
        self.assertTrue(
            any(c.lemma_text == "dog" for c in candidates),
            f"Expected the 'dog' lemma to be sourced from fr/es; got {guids}",
        )


class TestFilterBehavior(CandidateLookupTestCase):
    def test_function_words_with_no_lemmas_dropped(self) -> None:
        sentence = add_test_sentence(self.session, {"en": "I see the dog"})
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        lemma_texts = {c.lemma_text for c in candidates}
        # "i" / "the" have no Lemma rows so they cannot contribute candidates.
        self.assertNotIn("i", lemma_texts)
        self.assertNotIn("the", lemma_texts)
        self.assertIn("dog", lemma_texts)


class TestDerivativeFormPath(CandidateLookupTestCase):
    def test_inflected_english_surface_resolves_via_derivative_form(self) -> None:
        from storage.models.schema import DerivativeForm, Lemma

        play_lemma = (
            self.session.query(Lemma)
            .filter(Lemma.lemma_text == "play", Lemma.pos_type == "verb")
            .first()
        )
        assert play_lemma is not None, "release fixture must include 'play' verb"
        self.session.add(
            DerivativeForm(
                lemma_id=play_lemma.id,
                language_code="en",
                derivative_form_text="playing",
                grammatical_form="gerund",
            )
        )
        self.session.flush()

        sentence = add_test_sentence(self.session, {"en": "They are playing now"})
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        self.assertIn(play_lemma.guid, _guids(candidates))


class TestCapAndScoring(CandidateLookupTestCase):
    def test_max_candidates_respected(self) -> None:
        sentence = add_test_sentence(self.session, {"en": "I can play today"})
        candidates = find_candidate_lemmas_for_sentence(
            self.session, sentence.id, max_candidates=1
        )
        self.assertEqual(len(candidates), 1)

    def test_score_equals_number_of_confirming_languages(self) -> None:
        sentence = add_test_sentence(
            self.session,
            {
                "en": "The dog runs",
                "fr": "Le chien court",
                "es": "El perro corre",
            },
        )
        candidates = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        dog = _find_guid(candidates, _release_dog_guid(self.session))
        # en + fr + es all confirm. Sometimes more (lt/zh) via Lemma columns,
        # but at minimum these three.
        self.assertGreaterEqual(dog.match_score, 3)
        for lang in ("en", "fr", "es"):
            self.assertIn(lang, dog.matched_languages)


class TestDefaultSources(CandidateLookupTestCase):
    def test_default_source_languages_constant(self) -> None:
        self.assertEqual(
            DEFAULT_SOURCE_LANGUAGES,
            ["en", "fr", "lt", "zh", "es", "bn", "uk", "kn"],
        )


class TestInMemoryVariant(CandidateLookupTestCase):
    def test_from_translations_matches_from_sentence(self) -> None:
        translations = {
            "en": "I can play today",
            "bn": "আমি আজ পারা",
            "uk": "Я можу грати сьогодні",
            "kn": "ನಾನು ಇಂದು ಸಾಧ್ಯ ಆಡಲು",
        }
        sentence = add_test_sentence(self.session, translations)

        from_db = find_candidate_lemmas_for_sentence(self.session, sentence.id)
        in_memory = find_candidate_lemmas_from_translations(
            self.session,
            translations=translations,
        )
        self.assertEqual(_guids(from_db), _guids(in_memory))


def _release_dog_guid(session: Session) -> str:
    """Look up the release-data GUID for the 'dog' noun lemma."""
    from storage.models.schema import Lemma

    lemma = (
        session.query(Lemma)
        .filter(Lemma.lemma_text == "dog", Lemma.pos_type == "noun")
        .first()
    )
    assert lemma is not None and lemma.guid, "release fixture must include 'dog' noun"
    return lemma.guid


if __name__ == "__main__":
    unittest.main()
