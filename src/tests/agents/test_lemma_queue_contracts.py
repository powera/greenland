"""Contracts shared by lemma work finders and word capability tasks."""

from __future__ import annotations

import json
from typing import Any, cast

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from agents.lape.cli import enqueue_grammar_fact_work
from agents.sernas.cli import enqueue_sernas_work
from agents.vilkas.cli import enqueue_vilkas_work
from words.translation_workflow import enqueue_translation_population
from storage.models.schema import BarsukasTask, Base, Lemma
from workqueue.task_queue import TaskStatus, TaskType


def _session_with_noun() -> tuple[Engine, Session, Lemma]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    lemma = Lemma(
        lemma_text="dog",
        definition_text="a domesticated canine",
        pos_type="noun",
        guid="N00_012",
    )
    session.add(lemma)
    session.commit()
    return engine, session, lemma


def test_lemma_finders_enqueue_canonical_keys_and_payloads() -> None:
    engine, session, lemma = _session_with_noun()
    try:
        enqueue_translation_population(session, [lemma], ["fr", "es"])
        enqueue_vilkas_work(session, [lemma], "en-noun-forms")
        enqueue_sernas_work(session, [lemma], ["en"])
        enqueue_grammar_fact_work(
            cast(Any, None),
            session,
            [lemma],
            {"fr": ["grammatical_gender"]},
        )

        tasks = session.query(BarsukasTask).order_by(BarsukasTask.id).all()
        assert [task.task_type for task in tasks] == [
            TaskType.WORDS_TRANSLATIONS,
            TaskType.WORDS_FORMS,
            TaskType.WORDS_SYNONYMS,
            TaskType.WORDS_GRAMMAR_FACTS,
        ]
        assert all(task.dedup_key and task.dedup_key.startswith(task.task_type) for task in tasks)
        assert all(
            animal_name not in (task.dedup_key or "")
            for task in tasks
            for animal_name in ("voras", "vilkas", "sernas", "lape")
        )

        payloads = [json.loads(task.payload or "{}") for task in tasks]
        assert payloads[0]["languages"] == ["fr", "es"]
        assert payloads[1]["language_code"] == "en"
        assert payloads[2]["language_code"] == "en"
        assert payloads[3]["language_code"] == "fr"
        assert all(payload["lemma_id"] == lemma.id for payload in payloads)
        assert all("lang_code" not in payload for payload in payloads)
        assert all("lemma_guid" not in payload for payload in payloads)
    finally:
        session.close()
        engine.dispose()


def test_lemma_finders_recognize_active_legacy_dedup_keys() -> None:
    engine, session, lemma = _session_with_noun()
    try:
        session.add_all(
            [
                BarsukasTask(
                    task_type=TaskType.WORDS_TRANSLATIONS,
                    target_type="lemma",
                    target_id=lemma.id,
                    dedup_key=f"voras_populate_{lemma.id}",
                    status=TaskStatus.PENDING,
                ),
                BarsukasTask(
                    task_type=TaskType.WORDS_FORMS,
                    target_type="lemma",
                    target_id=lemma.id,
                    dedup_key=f"vilkas_en_noun_{lemma.id}",
                    status=TaskStatus.PENDING,
                ),
                BarsukasTask(
                    task_type=TaskType.WORDS_SYNONYMS,
                    target_type="lemma",
                    target_id=lemma.id,
                    dedup_key=f"sernas_{lemma.id}_en_all",
                    status=TaskStatus.PENDING,
                ),
                BarsukasTask(
                    task_type=TaskType.WORDS_GRAMMAR_FACTS,
                    target_type="lemma",
                    target_id=lemma.id,
                    dedup_key=f"lape_grammatical_gender_{lemma.id}_fr",
                    status=TaskStatus.PENDING,
                ),
            ]
        )
        session.commit()

        assert enqueue_translation_population(session, [lemma], ["fr"])["enqueued"] == 0
        assert enqueue_vilkas_work(session, [lemma], "en-noun-forms")["enqueued"] == 0
        assert enqueue_sernas_work(session, [lemma], ["en"])["enqueued"] == 0
        assert (
            enqueue_grammar_fact_work(
                cast(Any, None),
                session,
                [lemma],
                {"fr": ["grammatical_gender"]},
            )["enqueued"]
            == 0
        )
        assert session.query(BarsukasTask).count() == 4
    finally:
        session.close()
        engine.dispose()
