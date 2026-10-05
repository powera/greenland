#!/usr/bin/env python3
"""Tests for jonvabalis's row selection and how it acts on a verdict.

The model call itself is not exercised.  What is covered is everything decided
around it: which queued rows are reviewed at all, what a duplicate verdict on
a spacing variant writes, which duplicate verdicts are refused, and the prompt
branch a subtype-review row gets.
"""

import json
import unittest
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.jonvabalis import (
    ONLY_SPACING_VARIANTS,
    ONLY_SUBTYPE_REVIEW,
    JonvabalisAgent,
    build_prompt,
    head_word_problem,
    is_spacing_variant,
    is_subtype_review,
    queried_word_is_missing,
    select_pending_rows,
    spacing_key,
)
from storage.backend.config import DataSourceConfig
from storage.models.imports import TARGET_KIND_LEMMA, PendingImport, WordExclusion
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, Lemma
from storage.models.variant_form import (
    VARIANT_KIND_EQUIVALENT,
    VARIANT_KIND_SPELLING,
    VariantForm,
)
from storage.translation_helpers import LANG_CODE_TO_LLM_FIELD
from words.lemma_creation import TRANSLATION_LANGUAGES
from words.pending_imports.staging import create_pending_import

SUBTYPE_REVIEW_NOTE = "add_word: noun_other needs subtype review before import"


class JonvabalisTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.guid_counter = 0

    def tearDown(self) -> None:
        self.session.close()

    def add_lemma(self, text: str, pos_type: str = "noun", pos_subtype: str = "concept") -> Lemma:
        self.guid_counter += 1
        lemma = Lemma(
            lemma_text=text,
            definition_text=f"the {text}",
            pos_type=pos_type,
            pos_subtype=pos_subtype,
            guid=f"N99_{self.guid_counter:03d}",
        )
        self.session.add(lemma)
        self.session.commit()
        return lemma

    def stage(self, word: str, queried_word: Any = None, **kwargs: Any) -> PendingImport:
        pending = create_pending_import(
            self.session,
            english_word=word,
            definition=kwargs.pop("definition", f"the {word}"),
            disambiguation_translation=word,
            disambiguation_language="en",
            target_kind=TARGET_KIND_LEMMA,
            pos_type=kwargs.pop("pos_type", "noun"),
            pos_subtype=kwargs.pop("pos_subtype", "concept"),
            queried_word=queried_word,
            **kwargs,
        )
        self.session.commit()
        return pending

    def agent(self) -> JonvabalisAgent:
        # The settling paths make no LLM call, so no client is built.
        agent = JonvabalisAgent.__new__(JonvabalisAgent)
        agent.config = DataSourceConfig()
        return agent


class TestHeadWordProblem(unittest.TestCase):
    def test_a_verb_row_may_use_the_infinitive_of_the_queried_word(self) -> None:
        sentence = "The company operates in several countries."
        self.assertIsNone(
            head_word_problem("operate", sentence, "operating", "conducting business", "verb")
        )
        self.assertIsNone(head_word_problem("run", "They run the shop.", "ran", "manage", "verb"))

    def test_only_a_verb_row_gets_the_infinitive(self) -> None:
        sentence = "The company operates in several countries."
        self.assertIsNotNone(
            head_word_problem("operate", sentence, "operating", "conducting business", "noun")
        )

    def test_an_unrelated_word_is_still_refused(self) -> None:
        self.assertIsNotNone(
            head_word_problem("manage", "They manage the shop.", "operating", "run", "verb")
        )


class TestRowKinds(JonvabalisTestCase):
    def test_spacing_key_folds_hyphens_and_spaces(self) -> None:
        self.assertEqual(spacing_key("Break-up"), "breakup")
        self.assertEqual(spacing_key("high school"), "highschool")

    def test_spacing_variant_needs_different_spellings_of_one_word(self) -> None:
        self.assertTrue(is_spacing_variant(self.stage("high school", "high-school")))
        self.assertFalse(is_spacing_variant(self.stage("ice skate", "ice skates")))
        self.assertFalse(is_spacing_variant(self.stage("realm", "world")))
        self.assertFalse(is_spacing_variant(self.stage("capital")))

    def test_subtype_review_is_read_from_the_note(self) -> None:
        self.assertTrue(is_subtype_review(self.stage("capital", notes=SUBTYPE_REVIEW_NOTE)))
        self.assertFalse(is_subtype_review(self.stage("realm", "world")))

    def test_a_spacing_variant_is_not_waiting_on_its_queried_word(self) -> None:
        self.assertFalse(queried_word_is_missing(self.session, self.stage("breakup", "break-up")))
        self.assertTrue(queried_word_is_missing(self.session, self.stage("destroy", "consumed")))


class TestSelectPendingRows(JonvabalisTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.add_lemma("world")
        self.add_lemma("capital")
        self.add_lemma("say", pos_type="verb", pos_subtype="communication")
        self.new_head_word = self.stage("realm", "world")
        self.existing_head_word = self.stage(
            "say", "state", pos_type="verb", pos_subtype="communication"
        )
        self.subtype_review_existing = self.stage(
            "capital", notes=SUBTYPE_REVIEW_NOTE, pos_subtype="noun_other"
        )
        self.spacing_neither_lemma = self.stage("breakup", "break-up")
        self.queried_missing = self.stage("destroy", "consumed")

    def selected_ids(self, **kwargs: Any) -> set:
        return {row.id for row in select_pending_rows(self.session, 100, **kwargs)}

    def test_selects_new_head_words_subtype_reviews_and_spacing_variants(self) -> None:
        self.assertEqual(
            self.selected_ids(),
            {
                self.new_head_word.id,
                self.subtype_review_existing.id,
                self.spacing_neither_lemma.id,
            },
        )

    def test_only_subtype_review(self) -> None:
        self.assertEqual(
            self.selected_ids(only=ONLY_SUBTYPE_REVIEW), {self.subtype_review_existing.id}
        )

    def test_only_spacing_variants(self) -> None:
        self.assertEqual(
            self.selected_ids(only=ONLY_SPACING_VARIANTS), {self.spacing_neither_lemma.id}
        )


class TestDuplicateVerdict(JonvabalisTestCase):
    def duplicate_of(self, pending: PendingImport, lemma: Lemma, relation: Any = None) -> Any:
        decision = {
            "verdict": "duplicate",
            "duplicate_of_lemma_id": lemma.id,
            "proposed_word_relation": relation,
            "confidence": 0.95,
        }
        return self.agent().apply_decision(self.session, pending, decision)

    def base_variant(self) -> VariantForm:
        return self.session.query(VariantForm).filter(VariantForm.is_base_form.is_(True)).one()

    def test_spacing_duplicate_records_the_other_spelling_and_clears_the_row(self) -> None:
        lemma = self.add_lemma("high school")
        pending = self.stage("high school", "high-school")

        outcome = self.duplicate_of(pending, lemma)

        self.assertTrue(outcome["success"], outcome)
        self.assertEqual(outcome["action"], "rejected")
        variant = self.base_variant()
        self.assertEqual(variant.lemma_id, lemma.id)
        self.assertEqual(variant.variant_form_text, "high-school")
        self.assertEqual(variant.variant_kind, VARIANT_KIND_SPELLING)
        self.assertEqual(variant.grammatical_form, "noun/en_singular")
        self.assertEqual(self.session.query(PendingImport).count(), 0)
        self.assertEqual(self.session.query(WordExclusion).count(), 0)

    def test_spacing_variant_gets_its_paradigm_where_the_rules_are_safe(self) -> None:
        """A closed spelling inflects by rule; a hyphenated one keeps its base form only."""
        lemma = self.add_lemma("make-up")
        self.duplicate_of(self.stage("make-up", "makeup"), lemma)
        texts = {variant.variant_form_text for variant in self.session.query(VariantForm)}
        self.assertEqual(texts, {"makeup", "makeups"})

    def test_queried_spelling_can_be_the_head(self) -> None:
        lemma = self.add_lemma("nonstandard", pos_type="adjective", pos_subtype="belief_cultural")
        pending = self.stage(
            "nonstandard", "non-standard", pos_type="adjective", pos_subtype="belief_cultural"
        )
        self.duplicate_of(pending, lemma)
        variant = self.base_variant()
        self.assertEqual(variant.variant_form_text, "non-standard")
        self.assertEqual(variant.grammatical_form, "adjective/en_positive")

    def test_an_equivalent_word_is_recorded_on_the_duplicate(self) -> None:
        lemma = self.add_lemma("distribute", pos_type="verb", pos_subtype="transfer")
        pending = self.stage("allocate", "distribute", pos_type="verb", pos_subtype="transfer")

        self.duplicate_of(pending, lemma, relation="equivalent")

        variant = self.base_variant()
        self.assertEqual(variant.lemma_id, lemma.id)
        self.assertEqual(variant.variant_form_text, "allocate")
        self.assertEqual(variant.variant_kind, VARIANT_KIND_EQUIVALENT)
        self.assertEqual(self.session.query(PendingImport).count(), 0)

    def test_the_queued_row_is_logged_against_the_duplicate(self) -> None:
        """The row is deleted; the log is the only record of what was queried."""
        lemma = self.add_lemma("distribute", pos_type="verb", pos_subtype="transfer")
        pending = self.stage("allocate", "distribute", pos_type="verb", pos_subtype="transfer")
        pending_id = pending.id

        self.duplicate_of(pending, lemma, relation="equivalent")

        entry = (
            self.session.query(OperationLog)
            .filter(OperationLog.operation_type == "pending_import_review")
            .one()
        )
        self.assertEqual(entry.lemma_id, lemma.id)
        fact = json.loads(entry.fact)
        self.assertEqual(fact["pending_id"], pending_id)
        self.assertEqual(fact["queried_word"], "distribute")
        self.assertEqual(fact["proposed_word"], "allocate")
        self.assertEqual(fact["action"], "rejected")

    def test_a_word_of_its_own_or_a_paraphrase_is_not_recorded(self) -> None:
        lemma = self.add_lemma("world")
        self.duplicate_of(self.stage("humanity", "world"), lemma, relation="own_word")
        defense = self.add_lemma("defense")
        self.duplicate_of(self.stage("protective measure", "defense"), defense, "equivalent")
        self.assertEqual(self.session.query(VariantForm).count(), 0)
        self.assertEqual(self.session.query(PendingImport).count(), 0)

    def test_a_duplicate_of_another_pos_stays_queued(self) -> None:
        """The model once called the adverb "worldwide" a duplicate of the adjective."""
        lemma = self.add_lemma("worldwide", pos_type="adjective", pos_subtype="location")
        pending = self.stage("worldwide", "world-wide", pos_type="adverb", pos_subtype="location")

        outcome = self.duplicate_of(pending, lemma)

        self.assertEqual(outcome["action"], "left_in_queue")
        self.assertEqual(self.session.query(PendingImport).count(), 1)
        self.assertEqual(self.session.query(VariantForm).count(), 0)


class TestDistinctVerdict(JonvabalisTestCase):
    def test_a_sense_sharing_text_and_subtype_stays_queued(self) -> None:
        """Approval would have merged it into the existing lemma and deleted the row."""
        self.add_lemma("phenomenology", pos_subtype="knowledge_domain")
        pending = self.stage(
            "phenomenological description", "phenomenology", pos_subtype="knowledge_domain"
        )
        decision = {
            "verdict": "distinct",
            "confidence": 0.95,
            "head_word": "phenomenology",
            "definition": "The description of subjective experience in applied fields.",
            "sample_sentence": "The clinician recorded the phenomenology of the symptoms.",
            "disambiguation": "subjective experience",
            "pos_subtype": "knowledge_domain",
            "translations": {LANG_CODE_TO_LLM_FIELD[code]: "x" for code in TRANSLATION_LANGUAGES},
        }

        outcome = self.agent().apply_decision(self.session, pending, decision)

        self.assertEqual(outcome["action"], "left_in_queue")
        self.assertIn("approval would merge", outcome["reason"])
        self.assertEqual(self.session.query(PendingImport).count(), 1)


class TestPromptBranches(JonvabalisTestCase):
    def test_subtype_review_row_is_not_framed_as_a_headword_question(self) -> None:
        pending = self.stage("capital", notes=SUBTYPE_REVIEW_NOTE, pos_subtype="noun_other")
        prompt = build_prompt(pending, [], [], [])
        self.assertIn("could not choose a subtype", prompt)
        self.assertNotIn("belong under a different English head word", prompt)

    def test_spacing_variant_row_asks_for_the_standard_spelling(self) -> None:
        prompt = build_prompt(self.stage("breakup", "break-up"), [], [], [])
        self.assertIn("standard modern US spelling", prompt)


if __name__ == "__main__":
    unittest.main()
