#!/usr/bin/env python3
"""Tests for workqueue.worker module.

Tests the background worker task processing logic using mocks for
database sessions and handler functions.
"""

import json
import unittest
from typing import Optional
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from wordfreq.storage.models.schema import Base, BarsukasTask
from workqueue.task_queue import TaskStatus, TaskType
from workqueue.worker import process_task


class TestProcessTask(unittest.TestCase):
    """Test process_task dispatches to the correct handler."""

    def _make_task(self, task_type: str, payload: Optional[dict] = None) -> BarsukasTask:
        """Create a minimal BarsukasTask-like object."""
        task = BarsukasTask(
            task_type=task_type,
            status=TaskStatus.RUNNING,
            payload=json.dumps(payload or {}),
        )
        return task

    @patch("workqueue.worker.TASK_HANDLERS")
    def test_dispatches_to_registered_handler(self, mock_handlers: MagicMock) -> None:
        """process_task calls the registered handler with session and payload."""
        mock_handler = MagicMock(return_value="Added 3 translations")
        mock_handlers.get.return_value = mock_handler

        task = self._make_task("add_missing_translations", {"lemma_id": 42})
        session = MagicMock()

        result = process_task(task, session)

        mock_handlers.get.assert_called_once_with("add_missing_translations")
        mock_handler.assert_called_once_with(session, {"lemma_id": 42})
        self.assertEqual(result, "Added 3 translations")

    @patch("workqueue.worker.TASK_HANDLERS")
    def test_raises_for_unknown_task_type(self, mock_handlers: MagicMock) -> None:
        """process_task raises ValueError for unregistered task types."""
        mock_handlers.get.return_value = None
        task = self._make_task("unknown_task_type")
        session = MagicMock()

        with self.assertRaises(ValueError) as ctx:
            process_task(task, session)
        self.assertIn("No handler registered", str(ctx.exception))
        self.assertIn("unknown_task_type", str(ctx.exception))

    @patch("workqueue.worker.TASK_HANDLERS")
    def test_empty_payload_becomes_empty_dict(self, mock_handlers: MagicMock) -> None:
        """A task with null payload is deserialized as empty dict."""
        mock_handler = MagicMock(return_value="ok")
        mock_handlers.get.return_value = mock_handler

        task = BarsukasTask(
            task_type="generate_forms",
            status=TaskStatus.RUNNING,
            payload=None,
        )
        session = MagicMock()

        process_task(task, session)
        mock_handler.assert_called_once_with(session, {})

    @patch("workqueue.worker.TASK_HANDLERS")
    def test_handler_exception_propagates(self, mock_handlers: MagicMock) -> None:
        """Exceptions from handlers propagate to caller."""
        mock_handler = MagicMock(side_effect=RuntimeError("LLM timeout"))
        mock_handlers.get.return_value = mock_handler

        task = self._make_task("generate_audio", {"lemma_id": 1})
        session = MagicMock()

        with self.assertRaises(RuntimeError) as ctx:
            process_task(task, session)
        self.assertIn("LLM timeout", str(ctx.exception))


class TestProcessTaskWithDB(unittest.TestCase):
    """Integration-style tests for process_task using an in-memory database."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    @patch("workqueue.worker.TASK_HANDLERS")
    def test_process_task_with_real_db_task(self, mock_handlers: MagicMock) -> None:
        """process_task works with a real BarsukasTask from the database."""
        mock_handler = MagicMock(return_value="Generated 2 forms")
        mock_handlers.get.return_value = mock_handler

        task = BarsukasTask(
            task_type=TaskType.GENERATE_FORMS,
            target_type="lemma",
            target_id=5,
            status=TaskStatus.RUNNING,
            payload=json.dumps({"lemma_id": 5, "lang_code": "lt"}),
        )
        self.session.add(task)
        self.session.flush()

        result = process_task(task, self.session)
        self.assertEqual(result, "Generated 2 forms")
        mock_handler.assert_called_once_with(self.session, {"lemma_id": 5, "lang_code": "lt"})


if __name__ == "__main__":
    unittest.main()
