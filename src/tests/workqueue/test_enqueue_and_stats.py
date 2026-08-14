#!/usr/bin/env python3
"""Tests for the generic batch-enqueue helper and queue statistics.

These are the mechanics the agent CLIs share: turning a list of task requests
into queue rows (honoring dedup keys and dry runs), and counting what is in the
queue per task type.
"""

import unittest
from typing import List, Tuple

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from storage.models.schema import BarsukasTask, Base
from workqueue.stats import get_task_type_counts, has_queued_work
from workqueue.task_queue import TaskRequest, TaskStatus, TaskType, enqueue_tasks


def _session() -> Tuple[Engine, Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def _requests(*lemma_ids: int) -> List[TaskRequest]:
    return [
        TaskRequest(
            task_type=TaskType.WORDS_TRANSLATIONS,
            target_type="lemma",
            target_id=lemma_id,
            payload={"lemma_id": lemma_id},
            dedup_key=f"{TaskType.WORDS_TRANSLATIONS}:{lemma_id}",
            legacy_dedup_key=f"voras_populate_{lemma_id}",
        )
        for lemma_id in lemma_ids
    ]


class TestEnqueueTasks(unittest.TestCase):
    def setUp(self) -> None:
        self.engine, self.session = _session()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_enqueues_each_request_once(self) -> None:
        summary = enqueue_tasks(self.session, _requests(1, 2))

        self.assertEqual(summary["enqueued"], 2)
        self.assertEqual(summary["skipped"], 0)
        self.assertFalse(summary["dry_run"])
        self.assertEqual(self.session.query(BarsukasTask).count(), 2)

    def test_repeat_enqueue_is_skipped_not_duplicated(self) -> None:
        enqueue_tasks(self.session, _requests(1))
        summary = enqueue_tasks(self.session, _requests(1))

        self.assertEqual(summary["enqueued"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(self.session.query(BarsukasTask).count(), 1)

    def test_active_legacy_dedup_key_suppresses_the_request(self) -> None:
        self.session.add(
            BarsukasTask(
                task_type=TaskType.WORDS_TRANSLATIONS,
                target_type="lemma",
                target_id=7,
                dedup_key="voras_populate_7",
                status=TaskStatus.PENDING,
            )
        )
        self.session.commit()

        summary = enqueue_tasks(self.session, _requests(7))

        self.assertEqual(summary["enqueued"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(self.session.query(BarsukasTask).count(), 1)

    def test_dry_run_counts_without_writing(self) -> None:
        summary = enqueue_tasks(self.session, _requests(1, 2, 3), dry_run=True)

        self.assertEqual(summary["enqueued"], 3)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(self.session.query(BarsukasTask).count(), 0)


class TestTaskTypeCounts(unittest.TestCase):
    def setUp(self) -> None:
        self.engine, self.session = _session()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def _add(self, task_type: str, status: str) -> None:
        self.session.add(
            BarsukasTask(task_type=task_type, target_type="lemma", target_id=1, status=status)
        )

    def test_counts_are_grouped_by_type_and_status(self) -> None:
        self._add(TaskType.WORDS_TRANSLATIONS, TaskStatus.PENDING)
        self._add(TaskType.WORDS_TRANSLATIONS, TaskStatus.PENDING)
        self._add(TaskType.WORDS_TRANSLATIONS, TaskStatus.FAILED)
        self._add(TaskType.WORDS_SYNONYMS, TaskStatus.COMPLETED)
        self.session.commit()

        stats = get_task_type_counts(
            self.session, [TaskType.WORDS_TRANSLATIONS, TaskType.WORDS_SYNONYMS]
        )

        self.assertEqual(stats[TaskType.WORDS_TRANSLATIONS]["pending"], 2)
        self.assertEqual(stats[TaskType.WORDS_TRANSLATIONS]["failed"], 1)
        self.assertEqual(stats[TaskType.WORDS_TRANSLATIONS]["running"], 0)
        self.assertEqual(stats[TaskType.WORDS_SYNONYMS]["completed"], 1)

    def test_requested_types_without_rows_report_zeros(self) -> None:
        stats = get_task_type_counts(self.session, [TaskType.WORDS_FORMS])

        self.assertEqual(
            stats[TaskType.WORDS_FORMS],
            {"pending": 0, "running": 0, "completed": 0, "failed": 0},
        )
        self.assertFalse(has_queued_work(stats[TaskType.WORDS_FORMS]))

    def test_other_task_types_are_not_counted(self) -> None:
        self._add(TaskType.WORDS_SYNONYMS, TaskStatus.PENDING)
        self.session.commit()

        stats = get_task_type_counts(self.session, [TaskType.WORDS_TRANSLATIONS])

        self.assertEqual(list(stats), [TaskType.WORDS_TRANSLATIONS])
        self.assertFalse(has_queued_work(stats[TaskType.WORDS_TRANSLATIONS]))


if __name__ == "__main__":
    unittest.main()
