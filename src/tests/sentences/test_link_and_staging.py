#!/usr/bin/env python3
"""Tests for the sentence import writers: linking and staging.

The stage predicates in ``test_import_workflow`` decide *what* still needs
doing. These cover the two functions that actually change the database:

* ``link_sentence_words`` turns the resolver's verdicts into ``lemma_id`` and
  hint rows, but only when confident enough;
* ``stage_unlinked_words`` creates a ``PendingImport`` for each word the
  resolver could not place, and -- the part that closes the import loop -- a
  hint pointing at it.

The behaviours worth protecting here are the ones the promote/link loop relies
on: linking is idempotent, it never overwrites a decision someone else made,
and a staged word always leaves a trail back to the sentence that needed it.
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sentences.link_writer import (
    LINK_CONFIDENCE_THRESHOLD,
    link_sentence_words,
    release_sentence_word_hints,
)
from sentences.pending_staging import stage_unlinked_words
from storage.models.imports import PendingImport
from storage.models.schema import (
    Base,
    DerivativeForm,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
    SentenceWordHint,
)
from wordfreq.tools.sentence_word_linker import ResolvedLemma


class WriterTestCase(unittest.TestCase):
    """A sentence with translations, ready to have words attached."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.sentence = Sentence(guid="S_00001")
        self.session.add(self.sentence)
        self.session.commit()

        for language_code, text in (
            ("en", "The dog sees the dog."),
            ("lt", "Šuo mato šunį."),
            ("fr", "Le chien voit le chien."),
        ):
            self.session.add(
                SentenceTranslation(
                    sentence_id=self.sentence.id,
                    language_code=language_code,
                    translation_text=text,
                )
            )
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def add_lemma(self, text: str, guid: str, *, pos_type: str = "noun", **kwargs) -> Lemma:
        lemma = Lemma(
            lemma_text=text,
            definition_text=f"definition of {text}",
            pos_type=pos_type,
            guid=guid,
            **kwargs,
        )
        self.session.add(lemma)
        self.session.commit()
        return lemma

    def add_word(
        self,
        position: int,
        english_text: str,
        *,
        language_code: str = "en",
        part_of_speech: str = "noun",
        declined_form: str = None,  # type: ignore[assignment]
        lemma_id: int = None,  # type: ignore[assignment]
    ) -> SentenceWord:
        word = SentenceWord(
            sentence_id=self.sentence.id,
            language_code=language_code,
            position=position,
            part_of_speech=part_of_speech,
            english_text=english_text,
            declined_form=declined_form or english_text,
            lemma_id=lemma_id,
        )
        self.session.add(word)
        self.session.commit()
        return word

    def hints(self) -> list:
        return (
            self.session.query(SentenceWordHint)
            .filter(SentenceWordHint.sentence_id == self.sentence.id)
            .order_by(SentenceWordHint.position)
            .all()
        )


class TestLinkWritesConfidentMatches(WriterTestCase):
    def test_exact_match_is_linked(self) -> None:
        lemma = self.add_lemma("dog", "N01_001")
        word = self.add_word(0, "dog")

        outcome = link_sentence_words(self.session, self.sentence.id)

        self.assertGreaterEqual(outcome.linked, 1)
        self.assertEqual(word.lemma_id, lemma.id)

    def test_a_confident_link_also_writes_a_hint(self) -> None:
        lemma = self.add_lemma("dog", "N01_001")
        self.add_word(0, "dog")

        link_sentence_words(self.session, self.sentence.id)

        hints = self.hints()
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].lemma_id, lemma.id)
        # slot_name is NOT NULL, so every written hint must carry one.
        self.assertTrue(hints[0].slot_name)

    def test_hints_can_be_suppressed(self) -> None:
        self.add_lemma("dog", "N01_001")
        self.add_word(0, "dog")

        link_sentence_words(self.session, self.sentence.id, write_hints=False)

        self.assertEqual(self.hints(), [])

    def test_word_with_no_matching_lemma_is_reported_unresolved(self) -> None:
        self.add_word(0, "aardvark")

        outcome = link_sentence_words(self.session, self.sentence.id)

        self.assertEqual(outcome.linked, 0)
        self.assertEqual([r.english_text for r in outcome.unresolved], ["aardvark"])


class TestLinkRespectsTheConfidenceThreshold(WriterTestCase):
    """Ambiguous matches are left alone rather than guessed at."""

    def test_ambiguous_candidates_are_not_linked(self) -> None:
        """Two disambiguated senses give the resolver no basis to choose."""
        self.add_lemma("mouse", "N01_001", disambiguation="animal")
        self.add_lemma("mouse", "N01_002", disambiguation="computer")
        word = self.add_word(0, "mouse")

        outcome = link_sentence_words(self.session, self.sentence.id)

        self.assertIsNone(word.lemma_id)
        self.assertEqual(outcome.linked, 0)
        self.assertEqual(outcome.ambiguous, 1)

    def test_ambiguous_slot_gets_no_hint(self) -> None:
        """A slot with no decision must leave no trace, or staging skips it."""
        self.add_lemma("mouse", "N01_001", disambiguation="animal")
        self.add_lemma("mouse", "N01_002", disambiguation="computer")
        self.add_word(0, "mouse")

        link_sentence_words(self.session, self.sentence.id)

        self.assertEqual(self.hints(), [])

    def test_lowering_the_threshold_admits_the_ambiguous_match(self) -> None:
        """Confirms the threshold is what withheld the link, not a missing candidate."""
        self.add_lemma("mouse", "N01_001", disambiguation="animal")
        self.add_lemma("mouse", "N01_002", disambiguation="computer")
        word = self.add_word(0, "mouse")

        outcome = link_sentence_words(self.session, self.sentence.id, confidence_threshold=0.1)

        self.assertEqual(outcome.linked, 1)
        self.assertIsNotNone(word.lemma_id)

    def test_default_threshold_sits_between_the_two_outcomes(self) -> None:
        self.assertGreater(LINK_CONFIDENCE_THRESHOLD, 0.5)
        self.assertLessEqual(LINK_CONFIDENCE_THRESHOLD, 0.75)


class TestLinkIsSafeToRepeat(WriterTestCase):
    """The promote/link loop re-runs linking, so repetition must be harmless."""

    def test_running_twice_links_nothing_new(self) -> None:
        self.add_lemma("dog", "N01_001")
        self.add_word(0, "dog")

        first = link_sentence_words(self.session, self.sentence.id)
        second = link_sentence_words(self.session, self.sentence.id)

        self.assertGreater(first.linked, 0)
        self.assertEqual(second.linked, 0)

    def test_running_twice_does_not_duplicate_hints(self) -> None:
        self.add_lemma("dog", "N01_001")
        self.add_word(0, "dog")

        link_sentence_words(self.session, self.sentence.id)
        link_sentence_words(self.session, self.sentence.id)

        self.assertEqual(len(self.hints()), 1)

    def test_an_existing_lemma_id_is_never_overwritten(self) -> None:
        """A human's choice, or an earlier pass's, outranks a fresh resolution."""
        chosen = self.add_lemma("dog", "N01_001")
        other = self.add_lemma("dog", "N01_002", disambiguation="slang")
        word = self.add_word(0, "dog", lemma_id=other.id)

        link_sentence_words(self.session, self.sentence.id)

        self.assertEqual(word.lemma_id, other.id)
        self.assertNotEqual(word.lemma_id, chosen.id)


class TestLinkAcrossLanguagesAndRepeatedWords(WriterTestCase):
    def test_a_slot_links_every_language_row_that_shares_its_gloss(self) -> None:
        """Slots are keyed by English gloss, so one decision covers all languages."""
        lemma = self.add_lemma("dog", "N01_001")
        english = self.add_word(0, "dog")
        lithuanian = self.add_word(0, "dog", language_code="lt", declined_form="šuo")

        link_sentence_words(self.session, self.sentence.id)

        self.assertEqual(english.lemma_id, lemma.id)
        self.assertEqual(lithuanian.lemma_id, lemma.id)

    def test_a_word_repeated_in_one_sentence_collapses_to_a_single_slot(self) -> None:
        """ "The dog sees the dog" is one slot, so it gets one hint, not two."""
        lemma = self.add_lemma("dog", "N01_001")
        first = self.add_word(0, "dog")
        second = self.add_word(1, "dog")

        link_sentence_words(self.session, self.sentence.id)

        self.assertEqual(first.lemma_id, lemma.id)
        self.assertEqual(second.lemma_id, lemma.id)
        self.assertEqual(len(self.hints()), 1)


class TestStagingCreatesTheBackLink(WriterTestCase):
    """Staging is what lets a sentence find its word again after promotion."""

    def unresolved(self, *words: str, slot_name: str = "noun") -> list:
        return [
            ResolvedLemma(
                position=index,
                english_text=word,
                lemma=None,
                method="unresolved",
                confidence=0.0,
                slot_name=slot_name,
            )
            for index, word in enumerate(words)
        ]

    def test_a_pending_import_is_created(self) -> None:
        outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )

        self.assertEqual(outcome.staged, 1)
        pending = self.session.query(PendingImport).one()
        self.assertEqual(pending.english_word, "aardvark")

    def test_a_hint_points_at_the_new_pending_import(self) -> None:
        outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )

        hints = self.hints()
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0].pending_import_id, outcome.pending_import_ids[0])
        self.assertEqual(hints[0].english_text, "aardvark")

    def test_a_word_already_a_lemma_is_not_staged(self) -> None:
        self.add_lemma("dog", "N01_001")

        outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("dog"),
            source="test",
        )

        self.assertEqual(outcome.staged, 0)
        self.assertEqual(outcome.already_in_database, 1)

    def test_a_word_present_only_as_a_derivative_form_is_not_staged(self) -> None:
        """ "Running" is not a lemma, but staging it would duplicate "run"."""
        lemma = self.add_lemma("run", "V01_001", pos_type="verb")
        self.session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="running",
                language_code="en",
                grammatical_form="present_participle",
            )
        )
        self.session.commit()

        outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("running", slot_name="verb"),
            source="test",
        )

        self.assertEqual(outcome.staged, 0)
        self.assertEqual(outcome.already_in_database, 1)

    def test_a_matching_form_of_a_different_part_of_speech_does_not_suppress_staging(
        self,
    ) -> None:
        """The noun "running" is a separate word from the verb "run"."""
        lemma = self.add_lemma("run", "V01_001", pos_type="verb")
        self.session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="running",
                language_code="en",
                grammatical_form="present_participle",
            )
        )
        self.session.commit()

        outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("running", slot_name="noun"),
            source="test",
        )

        self.assertEqual(outcome.staged, 1)

    def test_a_word_already_staged_is_not_staged_again(self) -> None:
        stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )
        outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )

        self.assertEqual(outcome.staged, 0)
        self.assertEqual(outcome.already_pending, 1)
        self.assertEqual(self.session.query(PendingImport).count(), 1)

    def test_a_second_sentence_attaches_to_the_existing_pending_row(self) -> None:
        """The pending row is shared across sentences; the hint is not.

        Without a hint of its own, the second sentence never reports STAGE
        complete and is never re-linked when the pending row is approved, so
        the import workflow spins on it forever.
        """
        stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )

        other = Sentence(guid="S_00002")
        self.session.add(other)
        self.session.commit()

        outcome = stage_unlinked_words(
            self.session,
            other.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )
        self.session.commit()

        self.assertEqual(outcome.staged, 0)
        self.assertEqual(outcome.already_pending, 1)
        self.assertEqual(outcome.hints_written, 1)

        pending = self.session.query(PendingImport).one()
        other_hints = (
            self.session.query(SentenceWordHint)
            .filter(SentenceWordHint.sentence_id == other.id)
            .all()
        )
        self.assertEqual(len(other_hints), 1)
        self.assertEqual(other_hints[0].pending_import_id, pending.id)

    def test_attaching_does_not_downgrade_an_already_linked_hint(self) -> None:
        """A hint that already names a lemma outranks a pending row."""
        lemma = self.add_lemma("aardvark", "N01_009")
        stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )

        other = Sentence(guid="S_00002")
        self.session.add(other)
        self.session.commit()
        self.session.add(
            SentenceWordHint(
                sentence_id=other.id,
                position=0,
                lemma_id=lemma.id,
                english_text="aardvark",
                slot_name="noun",
            )
        )
        self.session.commit()

        outcome = stage_unlinked_words(
            self.session,
            other.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )
        self.session.commit()

        self.assertEqual(outcome.hints_written, 0)
        hint = (
            self.session.query(SentenceWordHint)
            .filter(SentenceWordHint.sentence_id == other.id)
            .one()
        )
        self.assertEqual(hint.lemma_id, lemma.id)
        self.assertIsNone(hint.pending_import_id)

    def test_dry_run_attaches_no_hint_for_an_existing_pending_row(self) -> None:
        stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
        )

        other = Sentence(guid="S_00002")
        self.session.add(other)
        self.session.commit()

        outcome = stage_unlinked_words(
            self.session,
            other.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
            dry_run=True,
        )

        self.assertEqual(outcome.already_pending, 1)
        self.assertEqual(outcome.hints_written, 0)
        self.assertEqual(
            self.session.query(SentenceWordHint)
            .filter(SentenceWordHint.sentence_id == other.id)
            .count(),
            0,
        )

    def test_the_same_word_twice_in_one_call_is_staged_once(self) -> None:
        outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark", "aardvark"),
            source="test",
        )

        self.assertEqual(outcome.staged, 1)
        self.assertEqual(self.session.query(PendingImport).count(), 1)

    def test_dry_run_counts_without_writing(self) -> None:
        outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=self.unresolved("aardvark"),
            source="test",
            dry_run=True,
        )

        self.assertEqual(outcome.staged, 1)
        self.assertEqual(self.session.query(PendingImport).count(), 0)
        self.assertEqual(self.hints(), [])

    def test_a_word_with_no_part_of_speech_still_gets_a_hint(self) -> None:
        """slot_name is NOT NULL, so a blank part of speech must not break the write."""
        unresolved = [
            ResolvedLemma(
                position=0,
                english_text="aardvark",
                lemma=None,
                method="unresolved",
                confidence=0.0,
                slot_name=None,
            )
        ]

        stage_unlinked_words(self.session, self.sentence.id, unresolved=unresolved, source="test")

        hints = self.hints()
        self.assertEqual(len(hints), 1)
        self.assertTrue(hints[0].slot_name)


class TestLinkingThenStaging(WriterTestCase):
    """The two writers run back to back, on the same sentence."""

    def test_unresolved_output_feeds_staging(self) -> None:
        self.add_lemma("dog", "N01_001")
        self.add_word(0, "dog")
        self.add_word(1, "aardvark")

        link_outcome = link_sentence_words(self.session, self.sentence.id)
        stage_outcome = stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=link_outcome.unresolved,
            source="test",
        )

        self.assertEqual(stage_outcome.staged, 1)

        # One sentence, two words, two different fates: one linked to a lemma,
        # one staged for approval -- each with its own hint.
        hints = {hint.english_text: hint for hint in self.hints()}
        self.assertIsNotNone(hints["dog"].lemma_id)
        self.assertIsNotNone(hints["aardvark"].pending_import_id)

    def test_hint_positions_stay_unique(self) -> None:
        """Both writers append, and the pair is unique on (sentence_id, position)."""
        self.add_lemma("dog", "N01_001")
        self.add_word(0, "dog")
        self.add_word(1, "aardvark")

        link_outcome = link_sentence_words(self.session, self.sentence.id)
        stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=link_outcome.unresolved,
            source="test",
        )

        positions = [hint.position for hint in self.hints()]
        self.assertEqual(len(positions), len(set(positions)))


class TestReleasingHintsBeforeDeletingAPending(WriterTestCase):
    """Every path that deletes a PendingImport must release its hints first.

    The foreign key has no ON DELETE behavior, so a hint left pointing at a
    deleted row either raises (Postgres) or lingers (SQLite without the
    pragma). A lingering hint is the worse case: STAGE counts it as staged, so
    the sentence is never staged again.
    """

    def stage_one(self, word: str = "aardvark") -> PendingImport:
        stage_unlinked_words(
            self.session,
            self.sentence.id,
            unresolved=[
                ResolvedLemma(
                    position=0,
                    english_text=word,
                    lemma=None,
                    method="unresolved",
                    confidence=0.0,
                    slot_name="noun",
                )
            ],
            source="test",
        )
        self.session.commit()
        return self.session.query(PendingImport).one()

    def test_rejection_drops_the_hint(self) -> None:
        pending = self.stage_one()

        released = release_sentence_word_hints(self.session, pending.id, None)
        self.session.delete(pending)
        self.session.commit()

        self.assertEqual(released, 1)
        self.assertEqual(self.hints(), [])

    def test_synonym_acceptance_repoints_the_hint_at_the_lemma(self) -> None:
        lemma = self.add_lemma("anteater", "N01_010")
        pending = self.stage_one()

        released = release_sentence_word_hints(self.session, pending.id, lemma.id)
        self.session.delete(pending)
        self.session.commit()

        self.assertEqual(released, 1)
        hint = self.session.query(SentenceWordHint).one()
        self.assertEqual(hint.lemma_id, lemma.id)
        self.assertIsNone(hint.pending_import_id)


if __name__ == "__main__":
    unittest.main()
