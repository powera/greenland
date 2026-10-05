"""Tests for PRONUNCIATIONS_JOB: papuga's pronunciations as a two-stage LLM job.

Stage 1 sends one call per (lemma, language) for its forms -- grouped when
there are several -- and stage 2, after the barrier, fills the translation's
pronunciation, usually from the base form stage 1 just stored.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.batch_queue import BatchQueueManager, create_batch_database_session
from clients.types import Response
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation
from wordfreq.tools.llm_validators import batch_generate_pronunciations
from workqueue.handlers.words.pronunciations import PRONUNCIATIONS_JOB, pronunciation_state
from workqueue.llm_batch import complete_rows, start_batch_run
from workqueue.registry import get_llm_job

_MODEL = "gpt-6-luna"


@pytest.fixture(autouse=True)
def _no_schema_size_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request shape only; counting schema tokens needs tiktoken's downloaded data."""
    monkeypatch.setattr("clients.lib.count_schema_tokens", lambda schema_dict: 0)


class _FakeBatchClient:
    def __init__(self) -> None:
        self.batches: Dict[str, List[Dict[str, Any]]] = {}
        self.results: Dict[str, List[Dict[str, Any]]] = {}
        self._uploads: Dict[str, List[Dict[str, Any]]] = {}

    def upload_batch_file(self, requests_data: List[Dict[str, Any]]) -> str:
        file_id = f"file-{len(self._uploads)}"
        self._uploads[file_id] = requests_data
        return file_id

    def create_batch(self, input_file_id: str, endpoint: str = "", **_: Any) -> Dict[str, Any]:
        batch_id = f"batch-{len(self.batches)}"
        self.batches[batch_id] = self._uploads[input_file_id]
        return {"id": batch_id}

    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        status = "completed" if batch_id in self.results else "in_progress"
        return {"id": batch_id, "status": status, "output_file_id": batch_id}

    def download_batch_results(self, output_file_id: str) -> List[Dict[str, Any]]:
        return self.results[output_file_id]

    def finish(self, batch_id: str, answer: Dict[str, Any]) -> None:
        self.results[batch_id] = [
            {
                "custom_id": line["custom_id"],
                "response": {
                    "status_code": 200,
                    "body": {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": json.dumps(answer)}],
                            }
                        ],
                    },
                },
            }
            for line in self.batches[batch_id]
        ]


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def batch_client() -> _FakeBatchClient:
    return _FakeBatchClient()


@pytest.fixture()
def manager(tmp_path: Path, batch_client: _FakeBatchClient) -> Iterator[BatchQueueManager]:
    batch_session = create_batch_database_session(str(tmp_path / "batch_tracking.sqlite"))
    yield BatchQueueManager(batch_session, batch_client=batch_client)  # type: ignore[arg-type]
    batch_session.close()


def _lemma(session: Session, text: str, pos_type: str) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=f"definition of {text}",
        pos_type=pos_type,
        guid=f"T02_{text}",
    )
    session.add(lemma)
    session.flush()
    return lemma


def _form(
    session: Session,
    lemma: Lemma,
    text: str,
    language_code: str,
    grammatical_form: str,
    is_base_form: bool,
    ipa: Optional[str] = None,
    phonetic: Optional[str] = None,
) -> DerivativeForm:
    form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=text,
        language_code=language_code,
        grammatical_form=grammatical_form,
        is_base_form=is_base_form,
        ipa_pronunciation=ipa,
        phonetic_pronunciation=phonetic,
    )
    session.add(form)
    session.flush()
    return form


def _translation(session: Session, lemma: Lemma, language_code: str, text: str) -> None:
    session.add(LemmaTranslation(lemma_id=lemma.id, language_code=language_code, translation=text))
    session.flush()


def _complete(
    manager: BatchQueueManager,
    batch_client: _FakeBatchClient,
    session: Session,
    batch_id: str,
    answer: Dict[str, Any],
) -> Dict[str, int]:
    batch_client.finish(batch_id, answer)
    manager.retrieve_batch_results(batch_id)
    rows = manager.get_completed_requests(batch_id=batch_id)
    return complete_rows(PRONUNCIATIONS_JOB, rows, session, batch_id, manager)


def _state(lemma: Lemma, language_code: str) -> Dict[str, Any]:
    return pronunciation_state(lemma.id, language_code, all_forms_pronunciation=True)


def test_job_is_registered() -> None:
    assert get_llm_job("papuga") is PRONUNCIATIONS_JOB


def test_several_forms_share_one_grouped_call_like_the_live_path(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "run", "verb")
    _form(session, lemma, "run", "en", "verb/en_present", True)
    _form(session, lemma, "ran", "en", "verb/en_past", False)
    session.commit()

    report = start_batch_run(session, manager, PRONUNCIATIONS_JOB, [_state(lemma, "en")], _MODEL)
    assert report.calls == 1
    body = batch_client.batches["batch-0"][0]["body"]

    sent: Dict[str, Any] = {}

    def record(**kwargs: Any) -> Response:
        sent.update(kwargs)
        return Response(response_text="", structured_data={}, usage=None)

    with patch("wordfreq.tools.llm_validators.UnifiedLLMClient") as client_class:
        client_class.return_value.generate_chat.side_effect = record
        batch_generate_pronunciations(
            lemma="run",
            definition="definition of run",
            pos_type="verb",
            forms=[
                {"form": "verb/en_present", "word": "run"},
                {"form": "verb/en_past", "word": "ran"},
            ],
            model=_MODEL,
            language_code="en",
        )
    assert body["input"] == sent["prompt"]
    assert body["instructions"] == sent["context"]

    result = _complete(
        manager,
        batch_client,
        session,
        "batch-0",
        {
            "verb_en_present_ipa": "/rʌn/",
            "verb_en_present_phonetic": "RUN",
            "verb_en_present_confidence": 0.9,
            "verb_en_past_ipa": "/ræn/",
            "verb_en_past_phonetic": "RAN",
            "verb_en_past_confidence": 0.3,
        },
    )
    assert result["updated"] == 1
    forms = {f.derivative_form_text: f for f in session.query(DerivativeForm).all()}
    assert forms["run"].ipa_pronunciation == "/rʌn/"
    # Below papuga's 0.5 floor: left for another run.
    assert forms["ran"].ipa_pronunciation is None
    assert len(batch_client.batches) == 1


def test_translation_is_copied_from_the_base_form_with_no_second_call(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "dog", "noun")
    _translation(session, lemma, "es", "perro")
    _form(session, lemma, "perro", "es", "noun/singular", True)
    session.commit()

    report = start_batch_run(session, manager, PRONUNCIATIONS_JOB, [_state(lemma, "es")], _MODEL)
    assert report.calls == 1
    _complete(
        manager,
        batch_client,
        session,
        "batch-0",
        {
            "needs_update": True,
            "suggested_ipa": "/ˈpero/",
            "suggested_phonetic": "PEH-roh",
            "issues": [],
            "confidence": 0.9,
        },
    )
    # Stage 2 found the base form filled and needed no batch of its own.
    assert len(batch_client.batches) == 1
    translation = session.query(LemmaTranslation).filter_by(lemma_id=lemma.id).one()
    assert (translation.ipa_pronunciation, translation.phonetic_pronunciation) == (
        "/ˈpero/",
        "PEH-roh",
    )


def test_translation_without_forms_is_asked_in_stage_two(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "cat", "noun")
    _translation(session, lemma, "es", "gato")
    session.commit()

    report = start_batch_run(session, manager, PRONUNCIATIONS_JOB, [_state(lemma, "es")], _MODEL)
    assert report.calls == 0
    assert report.resolved_without_llm == {"carried": 1}
    assert "gato" in batch_client.batches["batch-0"][0]["body"]["input"]

    result = _complete(
        manager,
        batch_client,
        session,
        "batch-0",
        {
            "needs_update": True,
            "suggested_ipa": "/ˈɡato/",
            "suggested_phonetic": "GAH-toh",
            "issues": [],
            "confidence": 0.9,
        },
    )
    assert result["updated"] == 1
    translation = session.query(LemmaTranslation).filter_by(lemma_id=lemma.id).one()
    assert translation.ipa_pronunciation == "/ˈɡato/"
    base = session.query(DerivativeForm).filter_by(lemma_id=lemma.id, is_base_form=True).one()
    assert base.derivative_form_text == "gato"


def test_stage_two_waits_for_every_stage_one_item(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    dog = _lemma(session, "dog", "noun")
    _translation(session, dog, "es", "perro")
    _form(session, dog, "perro", "es", "noun/singular", True)
    cat = _lemma(session, "cat", "noun")
    _translation(session, cat, "es", "gato")
    session.commit()

    start_batch_run(
        session, manager, PRONUNCIATIONS_JOB, [_state(dog, "es"), _state(cat, "es")], _MODEL
    )
    # Only dog's form went out; cat waits in stage 2 behind it.
    assert len(batch_client.batches) == 1
    _complete(
        manager,
        batch_client,
        session,
        "batch-0",
        {
            "needs_update": True,
            "suggested_ipa": "/ˈpero/",
            "suggested_phonetic": "PEH-roh",
            "issues": [],
            "confidence": 0.9,
        },
    )
    assert len(batch_client.batches) == 2
    assert "gato" in batch_client.batches["batch-1"][0]["body"]["input"]


def test_hand_entered_pronunciation_wins(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "sit", "verb")
    form = _form(session, lemma, "sit", "en", "verb/en_present", True)
    session.commit()
    start_batch_run(session, manager, PRONUNCIATIONS_JOB, [_state(lemma, "en")], _MODEL)

    form.ipa_pronunciation = "/sɪt/ (by hand)"
    form.phonetic_pronunciation = "SIT"
    session.commit()
    _complete(
        manager,
        batch_client,
        session,
        "batch-0",
        {
            "needs_update": True,
            "suggested_ipa": "/sæt/",
            "suggested_phonetic": "SAT",
            "issues": [],
            "confidence": 0.9,
            "alternative_pronunciations": [],
            "notes": "",
        },
    )
    refreshed = session.get(DerivativeForm, form.id)
    assert refreshed is not None
    assert refreshed.ipa_pronunciation == "/sɪt/ (by hand)"


def test_nothing_missing_is_skipped(session: Session, manager: BatchQueueManager) -> None:
    lemma = _lemma(session, "go", "verb")
    _form(session, lemma, "go", "en", "verb/en_present", True, ipa="/ɡoʊ/", phonetic="GOH")
    session.commit()
    report = start_batch_run(session, manager, PRONUNCIATIONS_JOB, [_state(lemma, "en")], _MODEL)
    assert report.resolved_without_llm == {"skipped": 1}
