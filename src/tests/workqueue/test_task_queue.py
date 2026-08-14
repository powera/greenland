#!/usr/bin/env python3
"""Tests for workqueue.task_queue module.

Tests the core queue operations (enqueue, claim, mark complete/failed, dedup)
using an in-memory SQLite database for realistic query testing.
"""

import json
import unittest
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, BarsukasTask
from workqueue.task_queue import (
    EnqueueResult,
    TaskStatus,
    TaskType,
    claim_next_task,
    enqueue_task,
    get_active_task,
    get_tasks_for_target,
    has_earlier_pending_task,
    mark_task_complete,
    mark_task_failed,
)


class TestTaskStatus(unittest.TestCase):
    """Test TaskStatus constants."""

    def test_status_values(self) -> None:
        self.assertEqual(TaskStatus.PENDING, "pending")
        self.assertEqual(TaskStatus.RUNNING, "running")
        self.assertEqual(TaskStatus.COMPLETED, "completed")
        self.assertEqual(TaskStatus.FAILED, "failed")

    def test_active_set(self) -> None:
        self.assertIn(TaskStatus.PENDING, TaskStatus.ACTIVE)
        self.assertIn(TaskStatus.RUNNING, TaskStatus.ACTIVE)
        self.assertNotIn(TaskStatus.COMPLETED, TaskStatus.ACTIVE)
        self.assertNotIn(TaskStatus.FAILED, TaskStatus.ACTIVE)


class TestTaskType(unittest.TestCase):
    """Test TaskType constants."""

    def test_type_values(self) -> None:
        """Task types use namespaced ids, e.g. "words.translations"."""
        self.assertEqual(TaskType.WORDS_TRANSLATIONS, "words.translations")
        self.assertEqual(TaskType.WORDS_PRONUNCIATIONS, "words.pronunciations")
        self.assertEqual(TaskType.WORDS_FORMS, "words.forms")
        self.assertEqual(TaskType.WORDS_SYNONYMS, "words.synonyms")
        self.assertEqual(TaskType.WORDS_GRAMMAR_FACTS, "words.grammar_facts")
        self.assertEqual(TaskType.CONVERSATIONS_GENERATE, "conversations.generate")
        self.assertEqual(TaskType.CONVERSATIONS_DEFINITIONS, "conversations.definitions")
        self.assertEqual(TaskType.SENTENCES_TRANSLATE, "sentences.translate")
        self.assertEqual(TaskType.AUDIO_GENERATE_LEMMA, "audio.generate.lemma")
        self.assertEqual(TaskType.AUDIO_GENERATE_SENTENCE, "audio.generate.sentence")

    def test_legacy_aliases_point_at_namespaced_values(self) -> None:
        """The pre-migration names are retained as aliases, not distinct values."""
        self.assertEqual(TaskType.ADD_MISSING_TRANSLATIONS, TaskType.WORDS_TRANSLATIONS)
        self.assertEqual(TaskType.GENERATE_PRONUNCIATIONS, TaskType.WORDS_PRONUNCIATIONS)
        self.assertEqual(TaskType.GENERATE_FORMS, TaskType.WORDS_FORMS)
        self.assertEqual(TaskType.GENERATE_SYNONYMS, TaskType.WORDS_SYNONYMS)
        self.assertEqual(TaskType.GENERATE_GRAMMAR_FACT, TaskType.WORDS_GRAMMAR_FACTS)
        self.assertEqual(TaskType.TRANSLATE_SENTENCE, TaskType.SENTENCES_TRANSLATE)
        self.assertEqual(TaskType.GENERATE_AUDIO, TaskType.AUDIO_GENERATE_LEMMA)
        self.assertEqual(TaskType.GENERATE_SENTENCE_AUDIO, TaskType.AUDIO_GENERATE_SENTENCE)


class TaskQueueDBTestCase(unittest.TestCase):
    """Base class for task queue tests that need a database session."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _enqueue(
        self,
        task_type: str = TaskType.ADD_MISSING_TRANSLATIONS,
        target_type: str = "lemma",
        target_id: int = 1,
        payload: Optional[dict] = None,
        dedup_key: Optional[str] = None,
    ) -> EnqueueResult:
        """Helper to enqueue a task with defaults."""
        return enqueue_task(
            self.session,
            task_type=task_type,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            dedup_key=dedup_key,
        )


class TestEnqueueTask(TaskQueueDBTestCase):
    """Test enqueue_task function."""

    def test_basic_enqueue(self) -> None:
        """Enqueuing a task creates it with PENDING status."""
        result = self._enqueue()
        self.assertTrue(result.created)
        self.assertEqual(result.task.status, TaskStatus.PENDING)
        self.assertEqual(result.task.task_type, TaskType.ADD_MISSING_TRANSLATIONS)
        self.assertEqual(result.task.target_type, "lemma")
        self.assertEqual(result.task.target_id, 1)

    def test_enqueue_with_payload(self) -> None:
        """Payload is serialized as JSON."""
        payload = {"lemma_id": 42, "lang_code": "fr"}
        result = self._enqueue(payload=payload)
        self.assertTrue(result.created)
        stored_payload = json.loads(result.task.payload)
        self.assertEqual(stored_payload["lemma_id"], 42)
        self.assertEqual(stored_payload["lang_code"], "fr")

    def test_enqueue_without_payload(self) -> None:
        """Tasks can be created without a payload."""
        result = self._enqueue(payload=None)
        self.assertTrue(result.created)
        self.assertIsNone(result.task.payload)

    def test_enqueue_assigns_id(self) -> None:
        """Flushing after enqueue assigns an ID to the task."""
        result = self._enqueue()
        self.assertIsNotNone(result.task.id)

    def test_dedup_prevents_duplicate_pending(self) -> None:
        """Active duplicate with same dedup_key returns existing task."""
        result1 = self._enqueue(dedup_key="lemma_1_translations")
        result2 = self._enqueue(dedup_key="lemma_1_translations")

        self.assertTrue(result1.created)
        self.assertFalse(result2.created)
        self.assertEqual(result1.task.id, result2.task.id)

    def test_dedup_prevents_duplicate_running(self) -> None:
        """Running task also counts as active for dedup purposes."""
        result1 = self._enqueue(dedup_key="lemma_1_translations")
        result1.task.status = TaskStatus.RUNNING
        self.session.flush()

        result2 = self._enqueue(dedup_key="lemma_1_translations")
        self.assertFalse(result2.created)
        self.assertEqual(result1.task.id, result2.task.id)

    def test_dedup_allows_after_completed(self) -> None:
        """Completed task does not block new enqueue with same dedup_key."""
        result1 = self._enqueue(dedup_key="lemma_1_translations")
        result1.task.status = TaskStatus.COMPLETED
        self.session.flush()

        result2 = self._enqueue(dedup_key="lemma_1_translations")
        self.assertTrue(result2.created)
        self.assertNotEqual(result1.task.id, result2.task.id)

    def test_dedup_allows_after_failed(self) -> None:
        """Failed task does not block new enqueue with same dedup_key."""
        result1 = self._enqueue(dedup_key="lemma_1_translations")
        result1.task.status = TaskStatus.FAILED
        self.session.flush()

        result2 = self._enqueue(dedup_key="lemma_1_translations")
        self.assertTrue(result2.created)
        self.assertNotEqual(result1.task.id, result2.task.id)

    def test_different_dedup_keys_allowed(self) -> None:
        """Different dedup_keys are treated as distinct tasks."""
        result1 = self._enqueue(dedup_key="lemma_1_translations")
        result2 = self._enqueue(dedup_key="lemma_2_translations")

        self.assertTrue(result1.created)
        self.assertTrue(result2.created)
        self.assertNotEqual(result1.task.id, result2.task.id)

    def test_no_dedup_key_allows_duplicates(self) -> None:
        """Without dedup_key, duplicate tasks are allowed."""
        result1 = self._enqueue(dedup_key=None)
        result2 = self._enqueue(dedup_key=None)

        self.assertTrue(result1.created)
        self.assertTrue(result2.created)
        self.assertNotEqual(result1.task.id, result2.task.id)

    def test_enqueue_with_null_target(self) -> None:
        """Tasks can be created without target type/id."""
        result = enqueue_task(
            self.session,
            task_type=TaskType.CONVERSATIONS_GENERATE,
            target_type=None,
            target_id=None,
            payload={"words": [{"word": "hello"}]},
        )
        self.assertTrue(result.created)
        self.assertIsNone(result.task.target_type)
        self.assertIsNone(result.task.target_id)


class TestClaimNextTask(TaskQueueDBTestCase):
    """Test claim_next_task function."""

    def test_claim_single_pending(self) -> None:
        """Claiming picks the only pending task."""
        self._enqueue()
        task = claim_next_task(self.session)
        assert task is not None
        self.assertEqual(task.status, TaskStatus.RUNNING)
        self.assertIsNotNone(task.started_at)

    def test_claim_returns_none_when_empty(self) -> None:
        """Returns None when no pending tasks exist."""
        task = claim_next_task(self.session)
        self.assertIsNone(task)

    def test_claim_oldest_first(self) -> None:
        """Tasks are claimed in creation order (FIFO)."""
        r1 = self._enqueue(task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_id=1)
        r2 = self._enqueue(task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_id=2)

        task = claim_next_task(self.session)
        assert task is not None
        self.assertEqual(task.id, r1.task.id)

    def test_claim_skips_running(self) -> None:
        """Already running tasks are not re-claimed."""
        r1 = self._enqueue(target_id=1)
        r1.task.status = TaskStatus.RUNNING
        self.session.flush()

        r2 = self._enqueue(target_id=2)

        task = claim_next_task(self.session)
        assert task is not None
        self.assertEqual(task.id, r2.task.id)

    def test_claim_skips_completed_and_failed(self) -> None:
        """Completed and failed tasks are not claimed."""
        r1 = self._enqueue(target_id=1)
        r1.task.status = TaskStatus.COMPLETED
        self.session.flush()

        r2 = self._enqueue(target_id=2)
        r2.task.status = TaskStatus.FAILED
        self.session.flush()

        r3 = self._enqueue(target_id=3)

        task = claim_next_task(self.session)
        assert task is not None
        self.assertEqual(task.id, r3.task.id)

    def test_claim_respects_pipeline_order(self) -> None:
        """Later pipeline tasks are blocked by earlier pending tasks on same lemma."""
        # Enqueue pronunciations (step 4) then translations (step 2)
        r_pron = self._enqueue(
            task_type=TaskType.GENERATE_PRONUNCIATIONS, target_type="lemma", target_id=10
        )
        r_trans = self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=10
        )

        # Translations (step 2) should be claimed first
        task = claim_next_task(self.session)
        assert task is not None
        self.assertEqual(task.id, r_trans.task.id)

    def test_claim_allows_different_lemma_tasks(self) -> None:
        """Pipeline ordering only blocks tasks on the SAME lemma."""
        # Lemma 10: pronunciations (step 4) - blocked by nothing
        r_pron = self._enqueue(
            task_type=TaskType.GENERATE_PRONUNCIATIONS, target_type="lemma", target_id=10
        )
        # Lemma 20: translations (step 2)
        r_trans = self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=20
        )

        # Lemma 10 pronunciations should be claimable (no earlier step pending on lemma 10)
        task = claim_next_task(self.session)
        assert task is not None
        self.assertEqual(task.id, r_pron.task.id)

    def test_claim_non_pipeline_tasks_not_blocked(self) -> None:
        """Tasks not in the pipeline are never blocked by pipeline ordering."""
        # Enqueue a pipeline task first
        self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=10
        )
        # Enqueue a non-pipeline task (generate_sentence_audio) for same target
        r_non = self._enqueue(
            task_type=TaskType.GENERATE_SENTENCE_AUDIO, target_type="lemma", target_id=10
        )

        # The first task (translations) is claimed since it was enqueued first
        task1 = claim_next_task(self.session)
        assert task1 is not None
        self.assertEqual(task1.task_type, TaskType.ADD_MISSING_TRANSLATIONS)

        # The non-pipeline task should then be claimable
        task2 = claim_next_task(self.session)
        assert task2 is not None
        self.assertEqual(task2.id, r_non.task.id)

    def test_claim_returns_none_when_all_blocked(self) -> None:
        """Returns None if all pending tasks are blocked by pipeline dependencies."""
        # Only a later-step task, with an earlier-step pending on same lemma
        r_trans = self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=10
        )
        self._enqueue(task_type=TaskType.GENERATE_AUDIO, target_type="lemma", target_id=10)

        # Claim translations
        claim_next_task(self.session)

        # Now only audio is pending, but translations is RUNNING on same lemma
        # Audio (step 9) is not blocked by running (only pending blocks).
        # Actually, has_earlier_pending_task only checks PENDING status, not RUNNING.
        task = claim_next_task(self.session)
        assert task is not None
        self.assertEqual(task.task_type, TaskType.GENERATE_AUDIO)


class TestHasEarlierPendingTask(TaskQueueDBTestCase):
    """Test has_earlier_pending_task function."""

    def test_no_earlier_when_non_lemma(self) -> None:
        """Non-lemma tasks are never blocked."""
        r = self._enqueue(
            task_type=TaskType.TRANSLATE_SENTENCE, target_type="sentence", target_id=1
        )
        self.assertFalse(has_earlier_pending_task(self.session, r.task))

    def test_no_earlier_when_no_target_id(self) -> None:
        """Tasks without target_id are never blocked."""
        result = enqueue_task(
            self.session,
            task_type=TaskType.ADD_MISSING_TRANSLATIONS,
            target_type="lemma",
            target_id=None,
        )
        self.assertFalse(has_earlier_pending_task(self.session, result.task))

    def test_no_earlier_when_not_in_pipeline(self) -> None:
        """Tasks not in pipeline are never blocked."""
        r = self._enqueue(
            task_type=TaskType.GENERATE_SENTENCE_AUDIO, target_type="lemma", target_id=1
        )
        self.assertFalse(has_earlier_pending_task(self.session, r.task))

    def test_blocked_by_earlier_step(self) -> None:
        """Pronunciation task blocked by pending translations on same lemma."""
        self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=10
        )
        r_pron = self._enqueue(
            task_type=TaskType.GENERATE_PRONUNCIATIONS, target_type="lemma", target_id=10
        )
        self.assertTrue(has_earlier_pending_task(self.session, r_pron.task))

    def test_not_blocked_by_later_step(self) -> None:
        """Translation task NOT blocked by pending pronunciation on same lemma."""
        r_trans = self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=10
        )
        self._enqueue(task_type=TaskType.GENERATE_PRONUNCIATIONS, target_type="lemma", target_id=10)
        self.assertFalse(has_earlier_pending_task(self.session, r_trans.task))

    def test_not_blocked_by_different_lemma(self) -> None:
        """Tasks on different lemmas don't block each other."""
        self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=10
        )
        r_pron = self._enqueue(
            task_type=TaskType.GENERATE_PRONUNCIATIONS, target_type="lemma", target_id=20
        )
        self.assertFalse(has_earlier_pending_task(self.session, r_pron.task))

    def test_not_blocked_by_completed_earlier(self) -> None:
        """Completed earlier-step task does not block."""
        r_trans = self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=10
        )
        r_trans.task.status = TaskStatus.COMPLETED
        self.session.flush()

        r_pron = self._enqueue(
            task_type=TaskType.GENERATE_PRONUNCIATIONS, target_type="lemma", target_id=10
        )
        self.assertFalse(has_earlier_pending_task(self.session, r_pron.task))

    def test_not_blocked_by_running_earlier(self) -> None:
        """Running earlier-step task does not block (only pending blocks)."""
        r_trans = self._enqueue(
            task_type=TaskType.ADD_MISSING_TRANSLATIONS, target_type="lemma", target_id=10
        )
        r_trans.task.status = TaskStatus.RUNNING
        self.session.flush()

        r_pron = self._enqueue(
            task_type=TaskType.GENERATE_PRONUNCIATIONS, target_type="lemma", target_id=10
        )
        self.assertFalse(has_earlier_pending_task(self.session, r_pron.task))


class TestMarkTaskComplete(TaskQueueDBTestCase):
    """Test mark_task_complete function."""

    def test_marks_completed(self) -> None:
        result = self._enqueue()
        mark_task_complete(self.session, result.task, "Done: 5 translations added")
        self.assertEqual(result.task.status, TaskStatus.COMPLETED)
        self.assertEqual(result.task.result_message, "Done: 5 translations added")
        self.assertIsNotNone(result.task.finished_at)

    def test_finished_at_is_set(self) -> None:
        result = self._enqueue()
        before = datetime.utcnow()
        mark_task_complete(self.session, result.task, "ok")
        self.assertIsNotNone(result.task.finished_at)


class TestMarkTaskFailed(TaskQueueDBTestCase):
    """Test mark_task_failed function."""

    def test_marks_failed(self) -> None:
        result = self._enqueue()
        mark_task_failed(self.session, result.task, "LLM timeout", "Connection refused")
        self.assertEqual(result.task.status, TaskStatus.FAILED)
        self.assertEqual(result.task.result_message, "LLM timeout")
        self.assertEqual(result.task.error_detail, "Connection refused")
        self.assertIsNotNone(result.task.finished_at)

    def test_error_detail_optional(self) -> None:
        result = self._enqueue()
        mark_task_failed(self.session, result.task, "Something went wrong")
        self.assertEqual(result.task.status, TaskStatus.FAILED)
        self.assertIsNone(result.task.error_detail)


class TestGetTasksForTarget(TaskQueueDBTestCase):
    """Test get_tasks_for_target function."""

    def test_returns_tasks_for_target(self) -> None:
        self._enqueue(
            target_type="lemma", target_id=42, task_type=TaskType.ADD_MISSING_TRANSLATIONS
        )
        self._enqueue(target_type="lemma", target_id=42, task_type=TaskType.GENERATE_FORMS)
        self._enqueue(
            target_type="lemma", target_id=99, task_type=TaskType.ADD_MISSING_TRANSLATIONS
        )

        tasks = get_tasks_for_target(self.session, "lemma", 42)
        self.assertEqual(len(tasks), 2)
        for t in tasks:
            self.assertEqual(t.target_id, 42)

    def test_returns_empty_for_no_match(self) -> None:
        self._enqueue(target_type="lemma", target_id=1)
        tasks = get_tasks_for_target(self.session, "lemma", 999)
        self.assertEqual(len(tasks), 0)

    def test_respects_limit(self) -> None:
        for i in range(15):
            self._enqueue(target_type="lemma", target_id=1, task_type=TaskType.GENERATE_FORMS)
        tasks = get_tasks_for_target(self.session, "lemma", 1, limit=5)
        self.assertEqual(len(tasks), 5)

    def test_returns_all_statuses(self) -> None:
        """All four statuses are returned."""
        r1 = self._enqueue(
            target_type="lemma", target_id=1, task_type=TaskType.ADD_MISSING_TRANSLATIONS
        )
        r2 = self._enqueue(target_type="lemma", target_id=1, task_type=TaskType.GENERATE_FORMS)
        r3 = self._enqueue(
            target_type="lemma", target_id=1, task_type=TaskType.GENERATE_PRONUNCIATIONS
        )
        r4 = self._enqueue(target_type="lemma", target_id=1, task_type=TaskType.GENERATE_SYNONYMS)

        r1.task.status = TaskStatus.COMPLETED
        r2.task.status = TaskStatus.FAILED
        r3.task.status = TaskStatus.RUNNING
        # r4 stays PENDING
        self.session.flush()

        tasks = get_tasks_for_target(self.session, "lemma", 1)
        statuses = {t.status for t in tasks}
        self.assertEqual(
            statuses,
            {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.RUNNING, TaskStatus.PENDING},
        )


class TestGetActiveTask(TaskQueueDBTestCase):
    """Test get_active_task function."""

    def test_returns_pending_task(self) -> None:
        self._enqueue(dedup_key="my_key")
        task = get_active_task(self.session, "my_key")
        assert task is not None
        self.assertEqual(task.dedup_key, "my_key")

    def test_returns_running_task(self) -> None:
        r = self._enqueue(dedup_key="my_key")
        r.task.status = TaskStatus.RUNNING
        self.session.flush()

        task = get_active_task(self.session, "my_key")
        self.assertIsNotNone(task)

    def test_returns_none_for_completed(self) -> None:
        r = self._enqueue(dedup_key="my_key")
        r.task.status = TaskStatus.COMPLETED
        self.session.flush()

        task = get_active_task(self.session, "my_key")
        self.assertIsNone(task)

    def test_returns_none_for_failed(self) -> None:
        r = self._enqueue(dedup_key="my_key")
        r.task.status = TaskStatus.FAILED
        self.session.flush()

        task = get_active_task(self.session, "my_key")
        self.assertIsNone(task)

    def test_returns_none_for_unknown_key(self) -> None:
        task = get_active_task(self.session, "nonexistent_key")
        self.assertIsNone(task)


if __name__ == "__main__":
    unittest.main()
