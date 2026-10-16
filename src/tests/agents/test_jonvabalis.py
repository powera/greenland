#!/usr/bin/env python3
"""Tests for jonvabalis's row selection and how it acts on a verdict.

The model call itself is not exercised.  What is covered is everything decided
around it: which queued rows are reviewed at all, what a duplicate verdict on
a spacing variant writes, which duplicate verdicts are refused, and the prompt
branch a subtype-review row gets.
"""

import json
import unittest
from typing import Any, Dict

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.jonvabalis import (
    ONLY_SPACING_VARIANTS,
    PARKING_LEVEL,
    ONLY_SUBTYPE_REVIEW,
    JonvabalisAgent,
    build_context,
    build_prompt,
    head_word_problem,
    is_spacing_variant,
    queried_word_variant,
    is_subtype_review,
    select_pending_rows,
    spacing_key,
)
from clients.types import LLMCall
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
from quality.level_placement import PlacementSuggestion
from words.pending_imports.staging import create_pending_import
from workqueue.handlers.jonvabalis import JONVABALIS_JOB, review_state
from workqueue.llm_batch import Done, StageContext
from workqueue.registry import get_llm_job

SUBTYPE_REVIEW_NOTE = "add_word: noun_other needs subtype review before import"

pytestmark = pytest.mark.usefixtures("require_lemma_write_scope")


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
    def test_a_head_word_sharing_no_word_with_the_row_is_accepted(self) -> None:
        """'place value' was queued as 'numerical place' from 'digit'."""
        self.assertIsNone(
            head_word_problem("place value", "In 4,582, the 5 has a place value of hundreds.")
        )

    def test_a_parenthesised_head_word_is_refused(self) -> None:
        self.assertIsNotNone(head_word_problem("world (realm)", "A world of magic."))

    def test_the_sample_sentence_must_use_the_head_word(self) -> None:
        self.assertIsNotNone(head_word_problem("manage", "They run the shop."))


class TestQueriedWordVariant(unittest.TestCase):
    def test_an_equivalent_queried_word_is_recorded(self) -> None:
        self.assertEqual(
            queried_word_variant("exponent", "advocate", "equivalent", "noun"), "exponent"
        )

    def test_a_queried_word_of_its_own_is_not(self) -> None:
        self.assertIsNone(queried_word_variant("digit", "place value", "own_word", "noun"))

    def test_a_spelling_or_verb_form_of_the_head_word_is_not(self) -> None:
        self.assertIsNone(queried_word_variant("break-up", "breakup", "equivalent", "noun"))
        self.assertIsNone(queried_word_variant("operating", "operate", "equivalent", "verb"))


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
        # add_word queued every sense of "gather", so it has no lemma yet.
        self.queried_not_lemma = self.stage("accumulate", "gather")
        self.subtype_review_not_lemma = self.stage(
            "ledger", "ledger", notes=SUBTYPE_REVIEW_NOTE, pos_subtype="noun_other"
        )

    def selected_ids(self, **kwargs: Any) -> set:
        return {row.id for row in select_pending_rows(self.session, 100, **kwargs)}

    def test_selects_new_head_words_subtype_reviews_and_spacing_variants(self) -> None:
        self.assertEqual(
            self.selected_ids(),
            {
                self.new_head_word.id,
                self.subtype_review_existing.id,
                self.spacing_neither_lemma.id,
                self.queried_not_lemma.id,
                self.subtype_review_not_lemma.id,
            },
        )

    def test_only_subtype_review(self) -> None:
        self.assertEqual(
            self.selected_ids(only=ONLY_SUBTYPE_REVIEW),
            {self.subtype_review_existing.id, self.subtype_review_not_lemma.id},
        )

    def test_only_spacing_variants(self) -> None:
        self.assertEqual(
            self.selected_ids(only=ONLY_SPACING_VARIANTS), {self.spacing_neither_lemma.id}
        )

    def test_pos_type_narrows_the_selection(self) -> None:
        verb_row = self.stage("proclaim", "say", pos_type="verb", pos_subtype="communication")
        self.assertEqual(self.selected_ids(pos_type="verb"), {verb_row.id})


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
    @staticmethod
    def distinct(head_word: str, sample_sentence: str, **fields: Any) -> Dict[str, Any]:
        return {
            "verdict": "distinct",
            "confidence": 0.95,
            "head_word": head_word,
            "definition": f"A new sense of {head_word}.",
            "sample_sentence": sample_sentence,
            "translations": {LANG_CODE_TO_LLM_FIELD[code]: "x" for code in TRANSLATION_LANGUAGES},
            **fields,
        }

    def test_a_sense_sharing_text_and_subtype_is_created_beside_it(self) -> None:
        """Approval alone would have merged it into the existing lemma and deleted the row."""
        existing = self.add_lemma("phenomenology", pos_subtype="knowledge_domain")
        pending = self.stage(
            "phenomenological description", "phenomenology", pos_subtype="knowledge_domain"
        )
        decision = self.distinct(
            "phenomenology",
            "The clinician recorded the phenomenology of the symptoms.",
            disambiguation="subjective experience",
            pos_subtype="knowledge_domain",
        )

        outcome = self.agent().apply_decision(self.session, pending, decision)

        self.assertEqual(outcome["action"], "approved")
        self.assertNotEqual(outcome["lemma_id"], existing.id)
        created = self.session.get(Lemma, outcome["lemma_id"])
        assert created is not None
        self.assertEqual(created.lemma_text, "phenomenology")
        self.assertEqual(created.disambiguation, "subjective experience")
        self.assertEqual(self.session.query(PendingImport).count(), 0)

    def test_an_existing_head_word_the_model_was_not_shown_stays_queued(self) -> None:
        """Its senses were not in the prompt, so one may already be this sense."""
        self.add_lemma("place value")
        pending = self.stage("numerical place", "digit")
        decision = self.distinct(
            "place value",
            "In 4,582, the 5 has a place value of hundreds.",
            disambiguation="position",
            pos_subtype="quantitative_concept",
        )

        outcome = self.agent().apply_decision(self.session, pending, decision)

        self.assertEqual(outcome["action"], "left_in_queue")
        self.assertIn("not shown", outcome["reason"])
        self.assertEqual(self.session.query(PendingImport).count(), 1)

    def test_an_equivalent_queried_word_is_recorded_on_the_new_lemma(self) -> None:
        self.add_lemma("exponent", pos_subtype="quantitative_concept")
        pending = self.stage("advocate", "exponent", pos_subtype="human")
        decision = self.distinct(
            "advocate",
            "She is a leading advocate for renewable energy.",
            pos_subtype="human",
            queried_word_relation="equivalent",
        )

        outcome = self.agent().apply_decision(self.session, pending, decision)

        self.assertEqual(outcome["action"], "approved")
        # The paradigm may store "exponents" beside "exponent".
        variants = self.session.query(VariantForm).all()
        self.assertTrue(variants)
        self.assertEqual({variant.lemma_id for variant in variants}, {outcome["lemma_id"]})
        self.assertEqual({variant.variant_kind for variant in variants}, {VARIANT_KIND_EQUIVALENT})


class _FakePlacer:
    """Stands in for quality.level_placement.LevelPlacer: no index, no model."""

    def __init__(self, session: Session, level: Any = None, error: Any = None) -> None:
        self.session = session
        self.level = level
        self.error = error
        self.recorded: list = []

    def place_lemma(self, lemma: Lemma) -> PlacementSuggestion:
        if self.error is not None:
            raise self.error
        return PlacementSuggestion(
            level=self.level,
            fit="good" if self.level else "none",
            alternatives=(),
            reasoning="because",
            shortlist=(120,),
        )

    def record(self, lemma: Lemma, level: int) -> None:
        self.recorded.append((lemma.id, level))


class TestLevelPlacement(JonvabalisTestCase):
    def approve(self, placer: Any) -> Dict[str, Any]:
        pending = self.stage("badger", "brock", pos_subtype="animal")
        decision = TestDistinctVerdict.distinct(
            "badger", "A badger dug under the fence.", pos_subtype="animal"
        )
        agent = self.agent()
        if placer is not None:
            agent.place_levels = True
            agent._placer = placer
        return agent.apply_decision(self.session, pending, decision)

    def level_of(self, outcome: Dict[str, Any]) -> Any:
        lemma = self.session.get(Lemma, outcome["lemma_id"])
        assert lemma is not None
        return lemma.difficulty_level

    def test_an_approved_lemma_moves_to_the_placed_level(self) -> None:
        placer = _FakePlacer(self.session, level=120)
        outcome = self.approve(placer)

        self.assertEqual(outcome["action"], "approved")
        self.assertEqual(self.level_of(outcome), 120)
        self.assertEqual(outcome["placement"]["fit"], "good")
        self.assertEqual(placer.recorded, [(outcome["lemma_id"], 120)])

    def test_no_fitting_level_leaves_it_parked(self) -> None:
        outcome = self.approve(_FakePlacer(self.session, level=None))

        self.assertEqual(self.level_of(outcome), PARKING_LEVEL)
        self.assertIsNone(outcome["placement"]["level"])

    def test_a_failed_placement_keeps_the_approval(self) -> None:
        outcome = self.approve(_FakePlacer(self.session, error=RuntimeError("model down")))

        self.assertEqual(outcome["action"], "approved")
        self.assertEqual(self.level_of(outcome), PARKING_LEVEL)
        self.assertIn("model down", outcome["placement"]["error"])

    def test_placement_is_off_unless_asked_for(self) -> None:
        outcome = self.approve(None)

        self.assertEqual(self.level_of(outcome), PARKING_LEVEL)
        self.assertNotIn("placement", outcome)


class TestPromptBranches(JonvabalisTestCase):
    def test_subtype_review_row_is_not_framed_as_a_headword_question(self) -> None:
        pending = self.stage("capital", notes=SUBTYPE_REVIEW_NOTE, pos_subtype="noun_other")
        prompt = build_prompt(pending, [], [])
        self.assertIn("could not choose a subtype", prompt)
        self.assertNotIn("belong under a different English head word", prompt)

    def test_spacing_variant_row_asks_for_the_standard_spelling(self) -> None:
        prompt = build_prompt(self.stage("breakup", "break-up"), [], [])
        self.assertIn("standard modern US spelling", prompt)

    def test_context_holds_no_row_data(self) -> None:
        # The context is the cached prefix, so nothing from a row may leak into it.
        context = build_context("noun")
        self.assertIn("Subtypes for noun:", context)
        self.assertTrue(build_context("adjective").startswith(context.split("\n\nSubtypes")[0]))
        prompt = build_prompt(self.stage("capital"), [], [])
        self.assertNotIn("Subtypes for", prompt)
        self.assertNotIn("capital", context)


class TestBatchJob(JonvabalisTestCase):
    """Every prompt of a batch is built before any verdict is applied."""

    ctx = StageContext(model="gpt-test", via="batch")

    def setUp(self) -> None:
        super().setUp()
        self.add_lemma("heritage")
        self.add_lemma("descent")
        self.stage_fns = JONVABALIS_JOB.stages[0]

    def prepare(self, pending: PendingImport) -> Dict[str, Any]:
        state = review_state(pending)
        call = self.stage_fns.prepare(self.session, state, self.ctx)
        self.assertIsInstance(call, LLMCall)
        return state

    def test_a_head_word_another_row_of_the_batch_created_stays_queued(self) -> None:
        """Both rows judged "ancestry" new; only the first verdict may stand."""
        first = self.prepare(self.stage("ancestry", "heritage", pos_subtype="concept_idea"))
        second = self.prepare(self.stage("ancestry", "descent", pos_subtype="concept_idea"))
        # With a tag: an untagged verdict is already held by the check that a
        # head word with a sense needs one.
        decision = TestDistinctVerdict.distinct(
            "ancestry",
            "She traced her ancestry to Lithuania.",
            pos_subtype="concept_idea",
            disambiguation="lineage",
        )

        applied = self.stage_fns.apply(self.session, first, decision, self.ctx)
        self.session.commit()
        assert isinstance(applied, Done)
        self.assertEqual(applied.status, "written")
        stale = self.stage_fns.apply(self.session, second, dict(decision), self.ctx)

        assert isinstance(stale, Done)
        self.assertEqual(stale.status, "skipped")
        self.assertIn("after the prompt was built", stale.detail)
        self.assertEqual(self.session.query(Lemma).filter_by(lemma_text="ancestry").count(), 1)
        self.assertEqual(self.session.query(PendingImport).count(), 1)

    def test_a_row_settled_since_submission_is_skipped(self) -> None:
        pending = self.stage("ancestry", "heritage", pos_subtype="concept_idea")
        state = self.prepare(pending)
        self.session.delete(pending)
        self.session.commit()

        outcome = self.stage_fns.apply(self.session, state, {"verdict": "unsure"}, self.ctx)

        self.assertEqual(outcome, Done("skipped", "pending row is gone"))

    def test_the_job_is_registered_for_the_batch_poller(self) -> None:
        self.assertIs(get_llm_job(JONVABALIS_JOB.name), JONVABALIS_JOB)


if __name__ == "__main__":
    unittest.main()
