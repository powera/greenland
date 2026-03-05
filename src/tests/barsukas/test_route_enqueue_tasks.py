"""Focused route tests for enqueue-only Barsukas endpoints."""

from types import SimpleNamespace
from typing import Any, cast

from flask.testing import FlaskClient
from pytest import MonkeyPatch

from barsukas.app import BarsukasFlask
from storage.models.schema import Sentence, SentenceTranslation
from workqueue.task_queue import EnqueueResult, TaskType


def _seed_sentence_for_enqueue_tests(app: BarsukasFlask) -> int:
    """Insert a sentence with translations used by sentence/audio route tests."""
    session = app.db_session_factory()
    sentence = Sentence(
        guid="S_00001",
        pattern_type="SVO",
        tense="present",
        minimum_level=1,
        verified=False,
        rejected=False,
    )
    session.add(sentence)
    session.flush()

    session.add_all(
        [
            SentenceTranslation(
                sentence_id=sentence.id,
                language_code="en",
                translation_text="I eat.",
            ),
            SentenceTranslation(
                sentence_id=sentence.id,
                language_code="fr",
                translation_text="Je mange.",
            ),
        ]
    )
    sentence_id = int(sentence.id)
    session.commit()
    session.close()
    return sentence_id


def test_agents_generate_grammar_fact_enqueues_expected_task(
    client: FlaskClient,
    monkeypatch: MonkeyPatch,
) -> None:
    """POST /agents/generate-grammar-fact enqueues a grammar-fact task."""
    enqueue_mock_calls: list[dict[str, object]] = []

    def _fake_enqueue_task(db_session, **kwargs: object) -> EnqueueResult:  # type: ignore[no-untyped-def]
        del db_session
        enqueue_mock_calls.append(kwargs)
        return EnqueueResult(task=cast(Any, SimpleNamespace(id=111)), created=True)

    monkeypatch.setattr("workqueue.task_queue.enqueue_task", _fake_enqueue_task)
    monkeypatch.setattr("barsukas.routes.agents.enqueue_task", _fake_enqueue_task)
    monkeypatch.setattr("workqueue.handlers.lape.SUPPORTED_FACT_TYPES", {"measure_words"})
    monkeypatch.setattr(
        "workqueue.handlers.lape.validate_grammar_fact_request",
        lambda lemma, fact_type, language_code, db: (True, None, None),
    )
    monkeypatch.setattr("storage.crud.grammar_fact.get_grammar_fact_value", lambda *args: None)

    response = client.post(
        "/agents/generate-grammar-fact/1",
        data={"fact_type": "measure_words", "language_code": "zh"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert len(enqueue_mock_calls) == 1
    kwargs = enqueue_mock_calls[0]
    assert kwargs["task_type"] == TaskType.WORDS_GRAMMAR_FACTS
    assert kwargs["target_type"] == "lemma"
    assert kwargs["target_id"] == 1
    assert kwargs["dedup_key"] == f"{TaskType.WORDS_GRAMMAR_FACTS}:1:measure_words:zh"


def test_audio_generate_single_duplicate_submit_shows_warning_and_keeps_dedup_shape(
    client: FlaskClient,
    monkeypatch: MonkeyPatch,
) -> None:
    """POST /audio/generate-single duplicate enqueue shows user warning."""
    enqueue_mock_calls: list[dict[str, object]] = []

    def _fake_enqueue_task(db_session, **kwargs: object) -> EnqueueResult:  # type: ignore[no-untyped-def]
        del db_session
        enqueue_mock_calls.append(kwargs)
        return EnqueueResult(task=cast(Any, SimpleNamespace(id=222)), created=False)

    monkeypatch.setattr("workqueue.task_queue.enqueue_task", _fake_enqueue_task)

    response = client.post(
        "/audio/generate-single/V01_001",
        data={"language": "fr", "voices": "ash", "tts_engine": "openai"},
        follow_redirects=True,
    )

    html = response.data.decode()
    assert response.status_code == 200
    assert "Audio generation already in progress for this lemma/language." in html
    assert len(enqueue_mock_calls) == 1
    kwargs = enqueue_mock_calls[0]
    assert kwargs["task_type"] == TaskType.AUDIO_GENERATE_LEMMA
    assert kwargs["target_type"] == "lemma"
    assert kwargs["target_id"] == 1
    assert kwargs["dedup_key"] == f"{TaskType.AUDIO_GENERATE_LEMMA}:1:fr:openai"


def test_sentences_translate_duplicate_submit_shows_info_message(
    app: BarsukasFlask,
    client: FlaskClient,
    monkeypatch: MonkeyPatch,
) -> None:
    """POST /sentences/<id>/translate duplicate enqueue shows informative flash."""
    sentence_id = _seed_sentence_for_enqueue_tests(app)
    enqueue_mock_calls: list[dict[str, object]] = []

    def _fake_enqueue_task(db_session, **kwargs: object) -> EnqueueResult:  # type: ignore[no-untyped-def]
        del db_session
        enqueue_mock_calls.append(kwargs)
        return EnqueueResult(task=cast(Any, SimpleNamespace(id=333)), created=False)

    monkeypatch.setattr("workqueue.task_queue.enqueue_task", _fake_enqueue_task)
    monkeypatch.setattr("barsukas.routes.sentences.enqueue_task", _fake_enqueue_task)

    response = client.post(
        f"/sentences/{sentence_id}/translate",
        data={"languages": ["fr", "es"]},
        follow_redirects=True,
    )

    html = response.data.decode()
    assert response.status_code == 200
    assert (
        "A translation task for these languages is already in progress for this sentence." in html
    )
    assert len(enqueue_mock_calls) == 1
    kwargs = enqueue_mock_calls[0]
    assert kwargs["task_type"] == TaskType.SENTENCES_TRANSLATE
    assert kwargs["target_type"] == "sentence"
    assert kwargs["target_id"] == sentence_id
    assert kwargs["dedup_key"] == f"{TaskType.SENTENCES_TRANSLATE}:{sentence_id}:es:fr"
