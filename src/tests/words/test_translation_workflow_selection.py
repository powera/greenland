"""Tests for translation lemma selection and queueing."""

import json
from typing import Iterator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import BarsukasTask, Base, Lemma
from storage.translation_helpers import MAX_LLM_LANGUAGES_PER_OPERATION
from words.translation_workflow import (
    count_curated_lemmas,
    enqueue_translation_population,
    enqueue_translation_regeneration,
    resolve_generation_languages,
    select_curated_lemmas,
)
from workqueue.task_queue import TaskStatus, TaskType


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _add_lemmas(session: Session, count: int, *, curated: bool = True) -> List[Lemma]:
    lemmas = [
        Lemma(
            lemma_text=f"word{index}",
            definition_text=f"definition of word{index}",
            pos_type="noun",
            guid=f"N00_{index:03d}" if curated else None,
        )
        for index in range(count)
    ]
    session.add_all(lemmas)
    session.commit()
    return lemmas


def test_selection_covers_curated_lemmas_only(session: Session) -> None:
    _add_lemmas(session, 2)
    _add_lemmas(session, 3, curated=False)

    selected = select_curated_lemmas(session)

    assert [lemma.guid for lemma in selected] == ["N00_000", "N00_001"]
    assert count_curated_lemmas(session) == 2


def test_selection_and_count_agree_under_a_limit(session: Session) -> None:
    _add_lemmas(session, 5)

    assert len(select_curated_lemmas(session, limit=3)) == 3
    assert count_curated_lemmas(session, limit=3) == 3


def test_population_tasks_carry_the_requested_languages(session: Session) -> None:
    lemma = _add_lemmas(session, 1)[0]

    summary = enqueue_translation_population(session, [lemma], ["fr", "es"])

    assert summary["enqueued"] == 1
    task = session.query(BarsukasTask).one()
    assert task.task_type == TaskType.WORDS_TRANSLATIONS
    assert task.dedup_key == f"{TaskType.WORDS_TRANSLATIONS}:{lemma.id}:es:fr"
    assert task.payload is not None
    payload = json.loads(task.payload)
    assert payload["languages"] == ["fr", "es"]
    assert payload["source_component"] == "agents.voras"


def test_regeneration_tasks_use_the_regenerate_task_type(session: Session) -> None:
    lemma = _add_lemmas(session, 1)[0]

    summary = enqueue_translation_regeneration(session, [lemma])

    assert summary["enqueued"] == 1
    task = session.query(BarsukasTask).one()
    assert task.task_type == TaskType.WORDS_TRANSLATIONS_REGENERATE
    assert task.dedup_key == f"{TaskType.WORDS_TRANSLATIONS_REGENERATE}:{lemma.id}"


def test_an_active_regeneration_task_is_not_queued_twice(session: Session) -> None:
    lemma = _add_lemmas(session, 1)[0]
    enqueue_translation_regeneration(session, [lemma])

    summary = enqueue_translation_regeneration(session, [lemma])

    assert summary["skipped"] == 1
    assert session.query(BarsukasTask).count() == 1


def test_a_legacy_regeneration_task_also_suppresses_the_request(session: Session) -> None:
    lemma = _add_lemmas(session, 1)[0]
    session.add(
        BarsukasTask(
            task_type=TaskType.WORDS_TRANSLATIONS_REGENERATE,
            target_type="lemma",
            target_id=lemma.id,
            dedup_key=f"voras_regenerate_{lemma.id}",
            status=TaskStatus.PENDING,
        )
    )
    session.commit()

    summary = enqueue_translation_regeneration(session, [lemma])

    assert summary["enqueued"] == 0
    assert session.query(BarsukasTask).count() == 1


def test_dry_run_queues_nothing(session: Session) -> None:
    lemmas = _add_lemmas(session, 2)

    summary = enqueue_translation_population(session, lemmas, ["fr"], dry_run=True)

    assert summary == {"enqueued": 2, "skipped": 0, "dry_run": True}
    assert session.query(BarsukasTask).count() == 0


def test_empty_language_request_falls_back_to_the_generation_defaults() -> None:
    from storage.translation_helpers import get_default_generation_languages

    defaults = resolve_generation_languages(get_default_generation_languages())

    assert resolve_generation_languages(None) == defaults
    assert resolve_generation_languages([]) == defaults
    assert resolve_generation_languages(["all"]) == defaults
    assert resolve_generation_languages(["fr"]) == ["fr"]


def test_the_whole_default_set_survives_resolution() -> None:
    """Generation batches its own requests, so nothing may be dropped here.

    The per-call LLM limit used to truncate the default set, silently dropping
    everything past the tenth entry -- which is exactly where the dialects and
    the experimental languages sit.
    """
    from storage.translation_helpers import get_default_generation_languages

    defaults = get_default_generation_languages()

    assert len(defaults) > MAX_LLM_LANGUAGES_PER_OPERATION
    assert resolve_generation_languages(None) == defaults
    for language_code in ("zh-tw", "es-419", "pt-br"):
        assert language_code in resolve_generation_languages(None)


def test_dialect_codes_are_accepted_however_they_are_spelled() -> None:
    """``--languages pt-BR`` from a shell must reach storage as ``pt-br``."""
    assert resolve_generation_languages(["es-419", "pt-BR", "zh_TW"]) == [
        "es-419",
        "pt-br",
        "zh-tw",
    ]
    # es-US and es-419 name the same variety, so the request de-duplicates.
    assert resolve_generation_languages(["es-419", "es-US"]) == ["es-419"]
    # The parent language stays distinct from its dialect.
    assert resolve_generation_languages(["es", "es-419"]) == ["es", "es-419"]
