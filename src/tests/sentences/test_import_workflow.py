#!/usr/bin/env python3
"""Tests for the sentence import stage model.

The stage is derived from the data rather than stored, so these tests build a
sentence in a particular state and assert which stage reports as next. The
distinction that matters most is *blocked* versus *incomplete*: a blocked stage
must let the sequencer move past it, or the workflow stalls on sentences it can
never finish.
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sentences.import_workflow import (
    SentenceImportSpec,
    SentenceImportStage,
    evaluate_stage,
    next_incomplete_stage,
    progress_fingerprint,
    should_carry_lemma,
    unlinked_words,
)
from sentences.translate_and_decompose import PHASE3_MIN_LANGUAGES
from storage.models.imports import PendingImport, SentencePendingImport
from storage.models.schema import (
    Base,
    Lemma,
    Sentence,
    SentenceTranslation,
    SentenceWord,
    SentenceWordHint,
)
from words.pending_imports.approval import delete_pending_import
from words.pending_imports.sentence_links import link_sentence_to_pending_import


class SentenceWorkflowTestCase(unittest.TestCase):
    """Shared fixture: one sentence, built up stage by stage."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.sentence = Sentence(guid="S_00001")
        self.session.add(self.sentence)
        self.session.commit()

        self.spec = SentenceImportSpec(
            target_languages=("en", "lt"),
            decompose_languages=("en",),
        )

    def tearDown(self) -> None:
        self.session.close()

    def add_translation(self, language_code: str, text: str) -> None:
        self.session.add(
            SentenceTranslation(
                sentence_id=self.sentence.id,
                language_code=language_code,
                translation_text=text,
            )
        )
        self.session.commit()

    def stage_word(self, english_text: str, *, position: int = 0) -> PendingImport:
        """Stage a word the way pending_staging does: a pending row plus a link."""
        pending = PendingImport(
            english_word=english_text,
            definition=english_text,
            disambiguation_translation=english_text,
            disambiguation_language="en",
            pos_type="noun",
        )
        self.session.add(pending)
        self.session.flush()
        link_sentence_to_pending_import(
            self.session,
            self.sentence.id,
            int(pending.id),
            english_text=english_text,
            slot_name="noun",
        )
        self.session.commit()
        return pending

    def stage_word_the_old_way(self, english_text: str, *, position: int = 0) -> PendingImport:
        """Stage a word as databases did before the link table existed.

        The hint column is no longer written, but rows staged that way are
        still out there and must keep reporting STAGE and PROMOTE correctly.
        """
        pending = PendingImport(
            english_word=english_text,
            definition=english_text,
            disambiguation_translation=english_text,
            disambiguation_language="en",
            pos_type="noun",
        )
        self.session.add(pending)
        self.session.flush()
        self.session.add(
            SentenceWordHint(
                sentence_id=self.sentence.id,
                position=position,
                pending_import_id=pending.id,
                english_text=english_text,
                slot_name="noun",
            )
        )
        self.session.commit()
        return pending

    def add_word(
        self,
        position: int,
        english_text: str,
        *,
        part_of_speech: str = "noun",
        lemma_id: int = None,  # type: ignore[assignment]
        language_code: str = "en",
    ) -> SentenceWord:
        word = SentenceWord(
            sentence_id=self.sentence.id,
            language_code=language_code,
            position=position,
            part_of_speech=part_of_speech,
            english_text=english_text,
            declined_form=english_text,
            lemma_id=lemma_id,
        )
        self.session.add(word)
        self.session.commit()
        return word


class TestStageSequence(SentenceWorkflowTestCase):
    """The sequencer returns stages in order as each one is satisfied."""

    def test_ingest_blocks_without_translation(self) -> None:
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.INGEST, spec=self.spec
        )
        self.assertFalse(status.complete)
        self.assertIsNotNone(status.blocked_reason)
        # Blocked counts as settled, so the sequencer does not stop here.
        self.assertTrue(status.settled)

    def test_translate_is_next_once_ingested(self) -> None:
        self.add_translation("en", "The dog barks.")
        self.assertEqual(
            next_incomplete_stage(self.session, self.sentence.id, spec=self.spec),
            SentenceImportStage.TRANSLATE,
        )

    def test_translate_reports_missing_languages(self) -> None:
        self.add_translation("en", "The dog barks.")
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.TRANSLATE, spec=self.spec
        )
        self.assertEqual(status.detail["missing_languages"], ["lt"])

    def test_decompose_is_next_once_enough_languages_exist(self) -> None:
        """With the target languages covered and Phase 3 viable, decomposition is next."""
        self.add_translation("en", "The dog barks.")
        self.add_translation("lt", "Šuo loja.")
        # A third translation beyond the target set clears the Phase-3 minimum.
        self.add_translation("fr", "Le chien aboie.")
        self.assertEqual(
            next_incomplete_stage(self.session, self.sentence.id, spec=self.spec),
            SentenceImportStage.DECOMPOSE,
        )

    def test_decompose_blocks_below_minimum_languages(self) -> None:
        """Phase 3 skips by design under three languages; that is blocked, not pending."""
        self.add_translation("en", "The dog barks.")
        self.add_translation("lt", "Šuo loja.")
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.DECOMPOSE, spec=self.spec
        )
        self.assertFalse(status.complete)
        self.assertIsNotNone(status.blocked_reason)
        self.assertEqual(status.detail["available_languages"], 2)
        self.assertLess(status.detail["available_languages"], PHASE3_MIN_LANGUAGES)
        self.assertTrue(status.settled)

    def test_blocked_decompose_does_not_stall_the_sequence(self) -> None:
        """With decomposition blocked, the sequencer moves on rather than looping."""
        self.add_translation("en", "The dog barks.")
        self.add_translation("lt", "Šuo loja.")
        stage = next_incomplete_stage(self.session, self.sentence.id, spec=self.spec)
        self.assertNotEqual(stage, SentenceImportStage.DECOMPOSE)


class TestLinkStage(SentenceWorkflowTestCase):
    """LINK completes when every word that should carry a lemma has one."""

    def setUp(self) -> None:
        super().setUp()
        self.add_translation("en", "The dog barks.")
        self.add_translation("lt", "Šuo loja.")
        self.add_translation("fr", "Le chien aboie.")

        self.lemma = Lemma(
            lemma_text="dog", definition_text="an animal", pos_type="noun", guid="N01_001"
        )
        self.session.add(self.lemma)
        self.session.commit()

    def test_incomplete_while_a_word_is_unlinked(self) -> None:
        self.add_word(0, "dog")
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.LINK, spec=self.spec
        )
        self.assertFalse(status.complete)
        self.assertEqual(status.detail["unlinked"], {"en": 1})

    def test_complete_once_linked(self) -> None:
        self.add_word(0, "dog", lemma_id=self.lemma.id)
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.LINK, spec=self.spec
        )
        self.assertTrue(status.complete)

    def test_grammatical_words_are_exempt(self) -> None:
        """ "The" never becomes a lemma, so demanding one would never settle."""
        self.add_word(0, "the", part_of_speech="determiner")
        self.add_word(1, "dog", lemma_id=self.lemma.id)
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.LINK, spec=self.spec
        )
        self.assertTrue(status.complete)

    def test_should_carry_lemma_excludes_skipped_pos(self) -> None:
        word = self.add_word(0, "of", part_of_speech="preposition")
        self.assertFalse(should_carry_lemma(word))

    def test_unlinked_words_lists_only_linkable_ones(self) -> None:
        self.add_word(0, "the", part_of_speech="determiner")
        self.add_word(1, "dog")
        remaining = unlinked_words(self.session, self.sentence.id)
        self.assertEqual([word.english_text for word in remaining], ["dog"])


class TestStageAndPromote(SentenceWorkflowTestCase):
    """STAGE and PROMOTE track the pending imports a sentence waits on."""

    def setUp(self) -> None:
        super().setUp()
        self.add_translation("en", "The dog barks.")
        self.add_translation("lt", "Šuo loja.")
        self.add_translation("fr", "Le chien aboie.")
        self.add_word(0, "dog")

    def test_stage_incomplete_before_staging(self) -> None:
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.STAGE, spec=self.spec
        )
        self.assertFalse(status.complete)
        self.assertEqual(status.detail["unstaged"], ["dog"])

    def test_stage_complete_once_a_link_carries_the_pending_import(self) -> None:
        self.stage_word("dog")
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.STAGE, spec=self.spec
        )
        self.assertTrue(status.complete)

    def test_stage_complete_for_a_word_staged_before_the_link_table(self) -> None:
        """Legacy hint rows still count, so old databases do not re-stage."""
        self.stage_word_the_old_way("dog")
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.STAGE, spec=self.spec
        )
        self.assertTrue(status.complete)

    def test_promote_incomplete_while_pending_exists(self) -> None:
        pending = self.stage_word("dog")
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.PROMOTE, spec=self.spec
        )
        self.assertFalse(status.complete)
        self.assertEqual(status.detail["pending_import_ids"], [pending.id])

    def test_promote_complete_once_the_word_becomes_a_lemma(self) -> None:
        """delete_pending_import applies the outcome, then removes the row.

        The sentence's word is linked to the new lemma on the way out, so the
        sentence needs no further pass to reach a resolved state.
        """
        pending = self.stage_word("dog")
        lemma = Lemma(
            lemma_text="dog", definition_text="an animal", pos_type="noun", guid="N01_001"
        )
        self.session.add(lemma)
        self.session.commit()

        delete_pending_import(self.session, pending, lemma_id=lemma.id)
        self.session.commit()

        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.PROMOTE, spec=self.spec
        )
        self.assertTrue(status.complete)

        # The word itself now carries the lemma, and the link is gone with the
        # pending row that owned it.
        word = self.session.query(SentenceWord).filter(SentenceWord.english_text == "dog").one()
        self.assertEqual(word.lemma_id, lemma.id)
        self.assertEqual(self.session.query(SentencePendingImport).count(), 0)

    def test_promote_complete_for_a_legacy_hint_release(self) -> None:
        """The same holds for a word staged before the link table existed."""
        pending = self.stage_word_the_old_way("dog")
        lemma = Lemma(
            lemma_text="dog", definition_text="an animal", pos_type="noun", guid="N01_002"
        )
        self.session.add(lemma)
        self.session.commit()

        delete_pending_import(self.session, pending, lemma_id=lemma.id)
        self.session.commit()

        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.PROMOTE, spec=self.spec
        )
        self.assertTrue(status.complete)

        hint = self.session.query(SentenceWordHint).one()
        self.assertEqual(hint.lemma_id, lemma.id)
        self.assertIsNone(hint.pending_import_id)


class TestIdiomsStageIsDeferred(SentenceWorkflowTestCase):
    def test_always_complete(self) -> None:
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.IDIOMS, spec=self.spec
        )
        self.assertTrue(status.complete)
        self.assertTrue(status.detail["deferred"])


class TestProgressFingerprint(SentenceWorkflowTestCase):
    """The fingerprint is what stops the promote/link loop when nothing changes."""

    def test_changes_when_a_word_is_linked(self) -> None:
        self.add_translation("en", "The dog barks.")
        lemma = Lemma(
            lemma_text="dog", definition_text="an animal", pos_type="noun", guid="N01_001"
        )
        self.session.add(lemma)
        self.session.commit()
        word = self.add_word(0, "dog")

        before = progress_fingerprint(self.session, self.sentence.id)
        word.lemma_id = lemma.id
        self.session.commit()
        after = progress_fingerprint(self.session, self.sentence.id)

        self.assertNotEqual(before, after)

    def test_stable_when_nothing_changes(self) -> None:
        self.add_translation("en", "The dog barks.")
        self.add_word(0, "dog")
        first = progress_fingerprint(self.session, self.sentence.id)
        second = progress_fingerprint(self.session, self.sentence.id)
        self.assertEqual(first, second)


class TestSpecFromPayload(unittest.TestCase):
    def test_defaults_applied_for_missing_keys(self) -> None:
        spec = SentenceImportSpec.from_payload({})
        self.assertIn("en", spec.target_languages)
        self.assertEqual(spec.decompose_languages, ("en",))
        self.assertFalse(spec.auto_promote)

    def test_comma_string_languages_are_split(self) -> None:
        spec = SentenceImportSpec.from_payload({"target_languages": "en, LT ,fr"})
        self.assertEqual(spec.target_languages, ("en", "lt", "fr"))

    def test_max_iterations_never_below_one(self) -> None:
        spec = SentenceImportSpec.from_payload({"max_iterations": 0})
        self.assertEqual(spec.max_iterations, 1)

    def test_bad_max_iterations_falls_back_to_default(self) -> None:
        spec = SentenceImportSpec.from_payload({"max_iterations": "not a number"})
        self.assertEqual(spec.max_iterations, 3)


class TestSequencerReachesStage(SentenceWorkflowTestCase):
    """The LINK/STAGE deadlock: the sequencer must always advance.

    A word with no lemma in the database leaves LINK incomplete no matter how
    many times linking runs, because linking is not what fixes it -- STAGE is.
    ``next_incomplete_stage`` is a pure read and cannot tell "never ran" from
    "ran and changed nothing", so on its own it hands LINK back forever and the
    sentence never reaches STAGE. These tests pin both halves of the fix.
    """

    def setUp(self) -> None:
        super().setUp()
        self.add_translation("en", "My dog is Rover.")
        self.add_translation("lt", "Mano suo yra Roveris.")
        # "Rover" is a content word with no lemma: exactly the case that hung.
        self.add_word(0, "Rover", part_of_speech="noun")

    def test_link_alone_never_settles(self) -> None:
        """Without the orchestrator's skip, LINK is returned indefinitely."""
        for _ in range(5):
            self.assertIs(
                next_incomplete_stage(self.session, self.sentence.id, spec=self.spec),
                SentenceImportStage.LINK,
            )

    def test_sequencer_skips_an_attempted_stage_and_reaches_stage(self) -> None:
        """Once LINK has had its turn, STAGE is next rather than LINK again."""
        from workqueue.handlers.sentences.import_workflow import _next_runnable_stage

        attempted: set = set()
        first = _next_runnable_stage(
            self.session, self.sentence.id, spec=self.spec, attempted=attempted
        )
        self.assertIs(first, SentenceImportStage.LINK)
        attempted.add(first)

        second = _next_runnable_stage(
            self.session, self.sentence.id, spec=self.spec, attempted=attempted
        )
        self.assertIs(second, SentenceImportStage.STAGE)

    def test_link_is_blocked_not_incomplete_once_the_word_is_staged(self) -> None:
        """A staged word is promotion's problem, so LINK stops asking for it."""
        self.stage_word("Rover")

        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.LINK, spec=self.spec
        )
        self.assertFalse(status.complete)
        self.assertIsNotNone(status.blocked_reason)
        # Blocked counts as settled, so the sequencer moves past LINK.
        self.assertTrue(status.settled)
        self.assertNotEqual(
            next_incomplete_stage(self.session, self.sentence.id, spec=self.spec),
            SentenceImportStage.LINK,
        )

    def test_link_still_incomplete_while_a_word_is_unstaged(self) -> None:
        """Linking must get its turn before staging does."""
        status = evaluate_stage(
            self.session, self.sentence.id, SentenceImportStage.LINK, spec=self.spec
        )
        self.assertFalse(status.complete)
        self.assertIsNone(status.blocked_reason)
        self.assertEqual(status.detail["unlinked"], {"en": 1})


if __name__ == "__main__":
    unittest.main()
