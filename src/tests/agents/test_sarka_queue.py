"""Tests for Sarka's capability-named workqueue integration."""

from typing import Any
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.sarka.cli import enqueue_definition_work, enqueue_level_work, get_sarka_queue_stats
from storage.models.schema import Base, BarsukasTask
from workqueue.handlers.sarka import handle_generate_conversation, handle_generate_definition
from workqueue.registry import TASK_HANDLERS
from workqueue.task_queue import TaskStatus, TaskType


def test_enqueue_level_work_uses_canonical_task_and_dedup_names() -> None:
    """Conversation work is persisted without an agent-coupled task name."""
    agent: Any = Mock()
    agent.plan_conversations_for_level.return_value = [
        [{"lemma_text": "hello", "lemma_id": 1}, {"lemma_text": "world", "lemma_id": 2}]
    ]
    session = Mock()

    with (
        patch("agents.sarka.cli.get_active_task", return_value=None),
        patch("agents.sarka.cli.enqueue_task") as enqueue_mock,
    ):
        enqueue_mock.return_value.created = True
        result = enqueue_level_work(agent, session, level=3, num_conversations=1, num_sentences=8)

    assert result["enqueued"] == 1
    enqueue_kwargs = enqueue_mock.call_args.kwargs
    assert enqueue_kwargs["task_type"] == TaskType.CONVERSATIONS_GENERATE
    assert enqueue_kwargs["dedup_key"].startswith(f"{TaskType.CONVERSATIONS_GENERATE}:3:")
    session.commit.assert_called_once_with()


def test_enqueue_definition_work_uses_canonical_task_and_dedup_names() -> None:
    """Definition work is persisted without an agent-coupled task name."""
    agent: Any = Mock()
    agent.plan_word_definition_pairs.return_value = (
        [[{"lemma_text": "hot", "lemma_id": 3}, {"lemma_text": "cold", "lemma_id": 4}]],
        {},
    )
    session = Mock()

    with (
        patch("agents.sarka.cli.get_active_task", return_value=None),
        patch("agents.sarka.cli.enqueue_task") as enqueue_mock,
    ):
        enqueue_mock.return_value.created = True
        result = enqueue_definition_work(agent, session, level=2, num_pairs=1)

    assert result["enqueued"] == 1
    enqueue_kwargs = enqueue_mock.call_args.kwargs
    assert enqueue_kwargs["task_type"] == TaskType.CONVERSATIONS_DEFINITIONS
    assert enqueue_kwargs["dedup_key"].startswith(f"{TaskType.CONVERSATIONS_DEFINITIONS}:2:")
    session.commit.assert_called_once_with()


def test_registry_keeps_legacy_sarka_task_aliases() -> None:
    """Already-persisted Sarka tasks continue to dispatch after the rename."""
    assert TASK_HANDLERS[TaskType.CONVERSATIONS_GENERATE] is handle_generate_conversation
    assert TASK_HANDLERS["sarka_generate_conversation"] is handle_generate_conversation
    assert TASK_HANDLERS[TaskType.CONVERSATIONS_DEFINITIONS] is handle_generate_definition
    assert TASK_HANDLERS["sarka_generate_definition"] is handle_generate_definition


def test_queue_stats_include_canonical_and_legacy_conversation_tasks() -> None:
    """Queue statistics remain accurate while persisted legacy work drains."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        session.add_all(
            [
                BarsukasTask(
                    task_type=TaskType.CONVERSATIONS_GENERATE,
                    target_type="conversation",
                    status=TaskStatus.PENDING,
                ),
                BarsukasTask(
                    task_type=TaskType.CONVERSATIONS_GENERATE,
                    target_type="conversation",
                    status=TaskStatus.COMPLETED,
                ),
                BarsukasTask(
                    task_type="sarka_generate_conversation",
                    target_type="conversation",
                    status=TaskStatus.PENDING,
                ),
            ]
        )
        session.flush()

        stats = get_sarka_queue_stats(session)

        assert stats == {"pending": 2, "running": 0, "completed": 1, "failed": 0}
    finally:
        session.close()
        engine.dispose()


def test_enqueue_level_work_skips_active_legacy_dedup_key() -> None:
    """Canonical enqueueing does not duplicate equivalent persisted legacy work."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        session.add(
            BarsukasTask(
                task_type="sarka_generate_conversation",
                target_type="conversation",
                status=TaskStatus.PENDING,
                dedup_key="sarka_level3_3cb95cfb_0",
            )
        )
        session.commit()

        agent: Any = Mock()
        agent.plan_conversations_for_level.return_value = [
            [{"lemma_text": "hello", "lemma_id": 1}, {"lemma_text": "world", "lemma_id": 2}]
        ]

        result = enqueue_level_work(
            agent,
            session,
            level=3,
            num_conversations=1,
            num_sentences=8,
        )

        assert result["enqueued"] == 0
        assert session.query(BarsukasTask).count() == 1
    finally:
        session.close()
        engine.dispose()
