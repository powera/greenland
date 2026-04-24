#!/usr/bin/env python3
"""Tests for sentences.candidate_lookup.find_candidate_lemmas_by_english_word.

Uses the shared fixture in candidate_lookup_fixture.py to seed an in-memory
SQLite DB with ~50 real release lemmas plus hand-authored ambiguous entries.
"""

import unittest
from typing import ClassVar, Dict

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from sentences.candidate_lookup import (
    CandidateLemma,
    DEFAULT_PIVOT_LANGUAGES,
    find_candidate_lemmas_by_english_word,
    find_candidate_lemmas_from_translations,
)
from tests.sentences.candidate_lookup_fixture import (
    add_test_sentence,
    build_test_engine,
    seed_test_database,
)


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
    def test_single_candidate_returned_for_unambiguous_noun(self) -> None:
        sentence = add_test_sentence(
            self.session,
            {"en": "The dog runs", "bn": "কুকুর দৌড়ায়", "uk": "Собака біжить", "kn": "ನಾಯಿ ಓಡುತ್ತದೆ"},
        )
        result = find_candidate_lemmas_by_english_word(
            self.session, sentence.id, target_languages=["fr", "es"]
        )
        self.assertIn("dog", result)
        dog_candidates = result["dog"]
        self.assertEqual(len(dog_candidates), 1)
        self.assertEqual(dog_candidates[0].lemma_text, "dog")
        self.assertEqual(dog_candidates[0].pos, "noun")

    def test_target_language_translations_populated(self) -> None:
        sentence = add_test_sentence(
            self.session,
            {"en": "The dog runs", "bn": "কুকুর দৌড়ায়"},
        )
        result = find_candidate_lemmas_by_english_word(
            self.session, sentence.id, target_languages=["fr", "es", "lt"]
        )
        dog_candidate = result["dog"][0]
        # Release base entries include fr/es/lt.
        self.assertIn("fr", dog_candidate.translations)
        self.assertIn("es", dog_candidate.translations)
        self.assertIn("lt", dog_candidate.translations)


class TestAmbiguityResolution(CandidateLookupTestCase):
    def _find_guid(self, candidates: list[CandidateLemma], guid: str) -> CandidateLemma:
        for candidate in candidates:
            if candidate.guid == guid:
                return candidate
        raise AssertionError(f"GUID {guid} not found among {[c.guid for c in candidates]}")

    def test_modal_can_wins_when_pivots_confirm_modal(self) -> None:
        # Pivot translations render "can" in its modal sense — container
        # translations (ক্যান / банка / ಕ್ಯಾನ್) are deliberately absent.
        sentence = add_test_sentence(
            self.session,
            {
                "en": "I can play today",
                "bn": "আমি আজ পারা",
                "uk": "Я можу грати сьогодні",
                "kn": "ನಾನು ಇಂದು ಸಾಧ್ಯ ಆಡಲು",
            },
        )
        result = find_candidate_lemmas_by_english_word(
            self.session, sentence.id, target_languages=["fr", "es", "lt", "zh"]
        )
        self.assertIn("can", result)
        can_candidates = result["can"]
        # Modal must rank first.
        self.assertEqual(can_candidates[0].guid, "TEST_CAN_MODAL")
        # Modal scored by pivot evidence; container scored 0 so it was dropped.
        self.assertGreater(can_candidates[0].pivot_match_score, 0)
        guids = [c.guid for c in can_candidates]
        self.assertNotIn("TEST_CAN_CONTAINER", guids)

    def test_container_can_wins_when_pivots_confirm_container(self) -> None:
        sentence = add_test_sentence(
            self.session,
            {
                "en": "I see a can",
                "bn": "আমি একটি ক্যান দেখি",
                "uk": "Я бачу банка",
                "kn": "ನಾನು ಒಂದು ಕ್ಯಾನ್ ನೋಡುತ್ತೇನೆ",
            },
        )
        result = find_candidate_lemmas_by_english_word(
            self.session, sentence.id, target_languages=["fr", "es"]
        )
        self.assertIn("can", result)
        can_candidates = result["can"]
        self.assertEqual(can_candidates[0].guid, "TEST_CAN_CONTAINER")
        self.assertGreater(can_candidates[0].pivot_match_score, 0)


class TestNoPivotEvidence(CandidateLookupTestCase):
    def test_ambiguous_word_with_no_pivots_returns_all_candidates_zero_score(self) -> None:
        # English-only sentence — no pivot translations stored at all.
        sentence = add_test_sentence(self.session, {"en": "I can play today"})
        result = find_candidate_lemmas_by_english_word(
            self.session, sentence.id, target_languages=["fr", "es"]
        )
        self.assertIn("can", result)
        guids = {c.guid for c in result["can"]}
        # Both senses must remain when nothing can score them.
        self.assertIn("TEST_CAN_MODAL", guids)
        self.assertIn("TEST_CAN_CONTAINER", guids)
        for candidate in result["can"]:
            self.assertEqual(candidate.pivot_match_score, 0)

    def test_missing_pivot_translations_silently_ignored(self) -> None:
        # Only one pivot language stored — the other two are missing but
        # shouldn't cause errors.
        sentence = add_test_sentence(
            self.session,
            {"en": "I can play today", "uk": "Я можу грати сьогодні"},
        )
        result = find_candidate_lemmas_by_english_word(self.session, sentence.id)
        self.assertIn("can", result)
        modal = next(c for c in result["can"] if c.guid == "TEST_CAN_MODAL")
        self.assertGreaterEqual(modal.pivot_match_score, 1)
        self.assertIn("uk", modal.confirmed_pivots)


class TestFilterBehavior(CandidateLookupTestCase):
    def test_tokens_without_lemmas_not_keys(self) -> None:
        sentence = add_test_sentence(self.session, {"en": "I see the dog"})
        result = find_candidate_lemmas_by_english_word(self.session, sentence.id)
        # "i" and "the" have no Lemma rows, so they don't appear as keys —
        # not because we filter them as grammatical, but because the DB has
        # nothing to resolve them to.
        self.assertNotIn("i", result)
        self.assertNotIn("the", result)
        self.assertIn("dog", result)

    def test_modal_can_surfaces_as_key_despite_being_grammatical(self) -> None:
        # "can" is registered as a grammatical/function word in English, but
        # candidate_lookup must still surface it as a key because both senses
        # live in the lemma DB and need disambiguation.
        sentence = add_test_sentence(self.session, {"en": "I can swim"})
        result = find_candidate_lemmas_by_english_word(self.session, sentence.id)
        self.assertIn("can", result)

    def test_sentence_without_english_returns_empty(self) -> None:
        sentence = add_test_sentence(self.session, {"en": "placeholder", "uk": "Я бачу"})
        # Remove the English translation row and confirm empty result.
        from storage.models.schema import SentenceTranslation

        en_row = (
            self.session.query(SentenceTranslation)
            .filter_by(sentence_id=sentence.id, language_code="en")
            .first()
        )
        assert en_row is not None
        self.session.delete(en_row)
        self.session.flush()

        result = find_candidate_lemmas_by_english_word(self.session, sentence.id)
        self.assertEqual(result, {})


class TestDerivativeFormPath(CandidateLookupTestCase):
    def test_inflected_english_surface_resolves_via_derivative_form(self) -> None:
        # "play" base lemma exists in release data (V01_006). Add an English
        # derivative form "playing" so the surface-level token resolves back
        # to the lemma.
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
        result = find_candidate_lemmas_by_english_word(self.session, sentence.id)
        self.assertIn("playing", result)
        guids = {c.guid for c in result["playing"]}
        self.assertIn(play_lemma.guid, guids)


class TestCapAndTargetLanguages(CandidateLookupTestCase):
    def test_max_candidates_per_word_respected(self) -> None:
        sentence = add_test_sentence(self.session, {"en": "I can play today"})
        # With pivots absent, both "can" senses survive — cap at 1 should drop one.
        result = find_candidate_lemmas_by_english_word(
            self.session, sentence.id, max_candidates_per_word=1
        )
        self.assertIn("can", result)
        self.assertEqual(len(result["can"]), 1)

    def test_target_languages_do_not_affect_scoring(self) -> None:
        # Same input with/without target_languages should produce the same
        # ranking. Target languages only change which translations are
        # attached to the CandidateLemma output.
        sentence = add_test_sentence(
            self.session,
            {
                "en": "I can play today",
                "bn": "আমি আজ পারা",
                "uk": "Я можу грати сьогодні",
                "kn": "ನಾನು ಇಂದು ಸಾಧ್ಯ ಆಡಲು",
            },
        )
        no_targets = find_candidate_lemmas_by_english_word(self.session, sentence.id)
        with_targets = find_candidate_lemmas_by_english_word(
            self.session, sentence.id, target_languages=["fr", "es", "lt", "zh"]
        )
        self.assertEqual(
            [c.guid for c in no_targets["can"]],
            [c.guid for c in with_targets["can"]],
        )
        # With targets, fr/es/lt/zh translations are populated.
        target_entry = with_targets["can"][0]
        for lang in ("fr", "es", "lt", "zh"):
            self.assertIn(lang, target_entry.translations)


class TestDefaultPivots(CandidateLookupTestCase):
    def test_default_pivot_languages_constant(self) -> None:
        self.assertEqual(DEFAULT_PIVOT_LANGUAGES, ["bn", "uk", "kn"])


class TestInMemoryVariant(CandidateLookupTestCase):
    def test_from_translations_matches_from_sentence(self) -> None:
        translations = {
            "en": "I can play today",
            "bn": "আমি আজ পারা",
            "uk": "Я можу грати сьогодні",
            "kn": "ನಾನು ಇಂದು ಸಾಧ್ಯ ಆಡಲು",
        }
        sentence = add_test_sentence(self.session, translations)

        from_db = find_candidate_lemmas_by_english_word(
            self.session, sentence.id, target_languages=["fr", "es"]
        )
        in_memory = find_candidate_lemmas_from_translations(
            self.session,
            english_text=translations["en"],
            pivot_translations={
                "bn": translations["bn"],
                "uk": translations["uk"],
                "kn": translations["kn"],
            },
            target_languages=["fr", "es"],
        )
        self.assertEqual(
            {k: [c.guid for c in v] for k, v in from_db.items()},
            {k: [c.guid for c in v] for k, v in in_memory.items()},
        )


if __name__ == "__main__":
    unittest.main()
