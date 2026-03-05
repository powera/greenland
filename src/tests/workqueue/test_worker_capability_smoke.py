#!/usr/bin/env python3
"""Smoke tests for capability-first task dispatch in the worker."""

import json
from typing import Dict
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Base, BarsukasTask
from workqueue.task_queue import TaskStatus
from workqueue.worker import process_task


def test_process_task_dispatches_capability_matrix() -> None:
    """process_task dispatches capability task types to the expected handlers."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        task_rows = [
            (
                "words.grammar_facts",
                {"lemma_id": 101, "language_code": "lt"},
                "grammar facts ok",
            ),
            (
                "sentences.translate",
                {"sentence_id": 202, "target_language": "fr"},
                "sentence translation ok",
            ),
            (
                "audio.generate.sentence",
                {"sentence_id": 303, "voice": "deterministic"},
                "sentence audio ok",
            ),
        ]

        created_tasks: Dict[str, BarsukasTask] = {}
        for task_type, payload_data, _ in task_rows:
            task = BarsukasTask(
                task_type=task_type,
                target_type="smoke",
                target_id=1,
                status=TaskStatus.PENDING,
                payload=json.dumps(payload_data),
            )
            session.add(task)
            session.flush()
            created_tasks[task_type] = task

        grammar_handler = Mock(return_value="grammar facts ok")
        sentence_handler = Mock(return_value="sentence translation ok")
        audio_handler = Mock(return_value="sentence audio ok")

        with patch.dict(
            "workqueue.registry.TASK_HANDLERS",
            {
                "words.grammar_facts": grammar_handler,
                "sentences.translate": sentence_handler,
                "audio.generate.sentence": audio_handler,
            },
            clear=False,
        ):
            for task_type, expected_payload, expected_message in task_rows:
                task_to_process = created_tasks[task_type]
                result = process_task(task_to_process, session)
                assert result == expected_message

        grammar_handler.assert_called_once_with(session, {"lemma_id": 101, "language_code": "lt"})
        sentence_handler.assert_called_once_with(
            session, {"sentence_id": 202, "target_language": "fr"}
        )
        audio_handler.assert_called_once_with(
            session, {"sentence_id": 303, "voice": "deterministic"}
        )
    finally:
        session.close()
        engine.dispose()
