#!/usr/bin/env python3
"""Tests for resolving a pending import into the thing it actually is.

Approval routes on ``target_kind``, and the two cheap routes -- name and
concept -- are the ones covered here: they need no LLM client, which is exactly
why they exist. The lemma route is left to the callers that can stub a model.

Deletion is covered hardest, because it is the part every path shares: a
pending row that goes away without settling its sentence links or its legacy
hints is what used to leave a sentence permanently waiting.
"""

import unittest
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.backend.config import DataSourceConfig
from storage.crud.concept import create_concept, get_concept_by_slug
from storage.crud.name_entity import create_name, find_name
from storage.models.concept import Concept
from storage.models.imports import (
    TARGET_KIND_CONCEPT,
    TARGET_KIND_LEMMA,
    TARGET_KIND_NAME,
    PendingImport,
    PendingImportSynonymCandidate,
    SentencePendingImport,
    WordExclusion,
)
from storage.models.name_entity import Name
from storage.models.schema import (
    Base,
    Lemma,
    Sentence,
    SentenceWord,
)
from words.pending_imports.approval import (
    approve_as_concept,
    approve_as_name,
    approve_pending_import,
    delete_pending_import,
    reject_pending_import,
)
from words.pending_imports.sentence_links import link_sentence_to_pending_import
from words.pending_imports.staging import create_pending_import


class ApprovalTestCase(unittest.TestCase):
    """One sentence with one unresolved word, and a term staged for it."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        self.sentence = Sentence(guid="S_00001")
        self.session.add(self.sentence)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()

    def add_word(self, english_text: str, *, position: int = 0) -> SentenceWord:
        word = SentenceWord(
            sentence_id=self.sentence.id,
            language_code="en",
            position=position,
            part_of_speech="noun",
            english_text=english_text,
            declined_form=english_text,
        )
        self.session.add(word)
        self.session.commit()
        return word

    def stage(self, word: str, *, link: bool = True, **kwargs: Any) -> PendingImport:
        pending = create_pending_import(
            self.session,
            english_word=word,
            definition=kwargs.pop("definition", f"the {word}"),
            disambiguation_translation=word,
            disambiguation_language="en",
            **kwargs,
        )
        if link:
            link_sentence_to_pending_import(
                self.session,
                self.sentence.id,
                int(pending.id),
                english_text=word,
                slot_name="noun",
            )
        self.session.commit()
        return pending


class TestApprovingAName(ApprovalTestCase):
    def test_a_name_row_is_created(self) -> None:
        pending = self.stage("George", target_kind=TARGET_KIND_NAME, name_kind="given_name")

        result = approve_as_name(self.session, pending)
        self.session.commit()

        self.assertTrue(result["success"])
        name = self.session.query(Name).one()
        self.assertEqual(name.name_text, "George")
        self.assertEqual(name.kind, "given_name")

    def test_a_missing_name_kind_falls_back_rather_than_failing(self) -> None:
        """``kind`` is NOT NULL and closed, so approval needs a safe default."""
        pending = self.stage("Fresh Mart", target_kind=TARGET_KIND_NAME)

        approve_as_name(self.session, pending)
        self.session.commit()

        self.assertEqual(self.session.query(Name).one().kind, "other")

    def test_an_existing_name_is_reused(self) -> None:
        """Renderings must stay stable, so a second staging is not a second name."""
        create_name(self.session, name_text="George", kind="given_name")
        self.session.commit()
        pending = self.stage("George", target_kind=TARGET_KIND_NAME, name_kind="given_name")

        result = approve_as_name(self.session, pending)
        self.session.commit()

        self.assertFalse(result["created"])
        self.assertEqual(self.session.query(Name).count(), 1)

    def test_the_waiting_sentence_word_is_linked_to_the_name(self) -> None:
        word = self.add_word("George")
        pending = self.stage("George", target_kind=TARGET_KIND_NAME, name_kind="given_name")

        approve_as_name(self.session, pending)
        self.session.commit()

        self.assertIsNotNone(word.name_id)
        self.assertIsNone(word.lemma_id)
        self.assertEqual(self.session.query(SentencePendingImport).count(), 0)

    def test_no_lemma_is_created(self) -> None:
        pending = self.stage("George", target_kind=TARGET_KIND_NAME, name_kind="given_name")

        approve_as_name(self.session, pending)
        self.session.commit()

        self.assertEqual(self.session.query(Lemma).count(), 0)


class TestApprovingAConcept(ApprovalTestCase):
    def test_a_concept_row_is_created_from_the_staged_gloss(self) -> None:
        pending = self.stage(
            "World War II",
            definition="the global conflict of 1939-1945",
            target_kind=TARGET_KIND_CONCEPT,
            concept_type="event",
        )

        result = approve_as_concept(self.session, pending)
        self.session.commit()

        self.assertTrue(result["success"])
        concept = self.session.query(Concept).one()
        self.assertEqual(concept.slug, "World_War_II")
        self.assertEqual(concept.summary, "the global conflict of 1939-1945")
        self.assertEqual(concept.concept_type, "event")

    def test_an_existing_concept_is_reused(self) -> None:
        create_concept(self.session, title="Art Deco")
        pending = self.stage("Art Deco", target_kind=TARGET_KIND_CONCEPT)

        result = approve_as_concept(self.session, pending)
        self.session.commit()

        self.assertTrue(result["success"])
        self.assertFalse(result["created"])
        self.assertEqual(self.session.query(Concept).count(), 1)

    def test_the_pending_row_and_its_links_are_gone(self) -> None:
        pending = self.stage("Art Deco", target_kind=TARGET_KIND_CONCEPT)

        approve_as_concept(self.session, pending)
        self.session.commit()

        self.assertEqual(self.session.query(PendingImport).count(), 0)
        self.assertEqual(self.session.query(SentencePendingImport).count(), 0)

    def test_a_word_that_becomes_a_concept_stops_counting_as_unlinked(self) -> None:
        """Otherwise the sentence stages the term again on its next pass."""
        from sentences.import_workflow import unlinked_words

        self.add_word("Art Deco")
        pending = self.stage("Art Deco", target_kind=TARGET_KIND_CONCEPT)

        approve_as_concept(self.session, pending)
        self.session.commit()

        self.assertIsNotNone(get_concept_by_slug(self.session, "Art_Deco"))
        self.assertEqual(unlinked_words(self.session, self.sentence.id), [])


class TestApprovalRouting(ApprovalTestCase):
    """``approve_pending_import`` dispatches on target_kind."""

    def config(self) -> DataSourceConfig:
        # Names and concepts never build an LLM client, so an empty config is
        # enough to prove the routing never reaches for one.
        return DataSourceConfig()

    def test_a_name_is_routed_to_the_name_path(self) -> None:
        pending = self.stage("George", target_kind=TARGET_KIND_NAME, name_kind="given_name")

        result = approve_pending_import(self.session, int(pending.id), self.config())

        self.assertTrue(result["success"])
        self.assertEqual(result["target_kind"], TARGET_KIND_NAME)
        self.assertIsNotNone(find_name(self.session, "George"))

    def test_a_concept_is_routed_to_the_concept_path(self) -> None:
        pending = self.stage("Art Deco", target_kind=TARGET_KIND_CONCEPT)

        result = approve_pending_import(self.session, int(pending.id), self.config())

        self.assertTrue(result["success"])
        self.assertEqual(result["target_kind"], TARGET_KIND_CONCEPT)

    def test_a_missing_row_is_reported_rather_than_raised(self) -> None:
        result = approve_pending_import(self.session, 4242, self.config())
        self.assertFalse(result["success"])

    def test_synonym_candidates_do_not_block_a_name(self) -> None:
        """Screening compares against lemmas, so it has nothing to say about names."""
        lemma = Lemma(
            lemma_text="george",
            definition_text="a made-up word",
            pos_type="noun",
            guid="N01_001",
        )
        self.session.add(lemma)
        self.session.flush()
        pending = self.stage("George", target_kind=TARGET_KIND_NAME, name_kind="given_name")
        self.session.add(
            PendingImportSynonymCandidate(
                pending_import_id=pending.id,
                lemma_id=lemma.id,
                candidate_text="george",
                same_pos=True,
                llm_synonym_category="strong",
                is_strong=True,
                status="active",
            )
        )
        self.session.commit()

        result = approve_pending_import(self.session, int(pending.id), self.config())

        self.assertTrue(result["success"])


class TestRejection(ApprovalTestCase):
    def test_the_word_is_excluded_and_the_row_removed(self) -> None:
        pending = self.stage("aardvark")

        result = reject_pending_import(self.session, int(pending.id))

        self.assertTrue(result["success"])
        self.assertEqual(self.session.query(PendingImport).count(), 0)
        self.assertEqual(self.session.query(WordExclusion).count(), 1)

    def test_the_sentence_link_goes_with_it(self) -> None:
        pending = self.stage("aardvark")

        reject_pending_import(self.session, int(pending.id))

        self.assertEqual(self.session.query(SentencePendingImport).count(), 0)

    def test_the_waiting_word_gains_nothing(self) -> None:
        """A rejected term becomes nothing, so the word stays unresolved."""
        word = self.add_word("aardvark")
        pending = self.stage("aardvark")

        reject_pending_import(self.session, int(pending.id))

        self.assertIsNone(word.lemma_id)
        self.assertIsNone(word.name_id)

    def test_exclusion_can_be_skipped(self) -> None:
        pending = self.stage("aardvark")

        reject_pending_import(self.session, int(pending.id), add_to_exclusions=False)

        self.assertEqual(self.session.query(WordExclusion).count(), 0)


class TestDeletionCleansUpEverything(ApprovalTestCase):
    """One choke point, so no caller can settle half of a pending row."""

    def test_synonym_candidates_are_removed_with_the_row(self) -> None:
        pending = self.stage("aardvark")
        self.session.add(
            PendingImportSynonymCandidate(
                pending_import_id=pending.id,
                candidate_text="anteater",
                same_pos=True,
                llm_synonym_category="near",
                status="active",
            )
        )
        self.session.commit()

        delete_pending_import(self.session, pending)
        self.session.commit()

        self.assertEqual(self.session.query(PendingImportSynonymCandidate).count(), 0)

    def test_links_from_several_sentences_are_all_removed(self) -> None:
        other = Sentence(guid="S_00002")
        self.session.add(other)
        self.session.commit()
        pending = self.stage("aardvark")
        link_sentence_to_pending_import(
            self.session,
            int(other.id),
            int(pending.id),
            english_text="aardvark",
        )
        self.session.commit()
        self.assertEqual(self.session.query(SentencePendingImport).count(), 2)

        delete_pending_import(self.session, pending)
        self.session.commit()

        self.assertEqual(self.session.query(SentencePendingImport).count(), 0)

    def test_every_waiting_sentence_is_resolved(self) -> None:
        other = Sentence(guid="S_00002")
        self.session.add(other)
        self.session.commit()
        other_word = SentenceWord(
            sentence_id=other.id,
            language_code="en",
            position=0,
            part_of_speech="noun",
            english_text="aardvark",
            declined_form="aardvark",
        )
        self.session.add(other_word)
        word = self.add_word("aardvark")
        lemma = Lemma(
            lemma_text="aardvark",
            definition_text="an animal",
            pos_type="noun",
            guid="N01_001",
        )
        self.session.add(lemma)
        self.session.flush()
        pending = self.stage("aardvark")
        link_sentence_to_pending_import(
            self.session,
            int(other.id),
            int(pending.id),
            english_text="aardvark",
        )
        self.session.commit()

        delete_pending_import(self.session, pending, lemma_id=int(lemma.id))
        self.session.commit()

        self.assertEqual(word.lemma_id, lemma.id)
        self.assertEqual(other_word.lemma_id, lemma.id)


if __name__ == "__main__":
    unittest.main()
