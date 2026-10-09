"""Tests for FORMS_JOB: vilkas's form generation as a staged LLM job.

The job runs the live generators with a DeferringClient, so these check that a
mechanical paradigm still answers without a call, that the LLM fallback of
every registered (language, pos) surfaces as the call the live path would make,
and that batch completion stores forms through the same writer as the live path.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.batch_queue import BatchQueueManager, create_batch_database_session
from clients.deferring_client import DeferLLMCall, DeferringClient
from clients.types import LLMCall, Response
from langtools.form_registry import FORM_SPECS
from langtools.form_tasks import generate_forms, get_on_demand_pos_types
from langtools.llm_forms_base import forms_answer_confidence, forms_answer_notes, query_forms
from storage.crud.uncertain_llm_result import get_uncertain_llm_result
from storage.database import QueryLog
from storage.models.schema import Base, DerivativeForm, Lemma
from storage.models.uncertain_llm_result import TOPIC_FORMS
from storage.translation_helpers import set_translation
from workqueue.handlers.words.forms import FORMS_JOB, forms_state
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


class _RecordingClient:
    """A live-client stand-in that records the call and returns *answer*."""

    def __init__(self, answer: Dict[str, Any]) -> None:
        self.default_model = _MODEL
        self.answer = answer
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(self, prompt: str, model: Optional[str] = None, **kwargs: Any) -> Response:
        self.calls.append({"prompt": prompt, **kwargs})
        return Response(response_text="", structured_data=self.answer, usage=None)


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


_counter = iter(range(10_000))


def _lemma(session: Session, text: str, pos_type: str, translations: Dict[str, str]) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=f"definition of {text}",
        pos_type=pos_type,
        guid=f"T01_{next(_counter):04d}",
    )
    session.add(lemma)
    session.flush()
    for language_code, value in translations.items():
        set_translation(session, lemma, language_code, value)
    session.commit()
    return lemma


def _forms(session: Session, lemma: Lemma, language_code: str) -> Dict[str, str]:
    rows = (
        session.query(DerivativeForm)
        .filter_by(lemma_id=lemma.id, language_code=language_code)
        .all()
    )
    return {row.grammatical_form: row.derivative_form_text for row in rows}


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
    return complete_rows(FORMS_JOB, rows, session, batch_id, manager)


def test_job_is_registered() -> None:
    assert get_llm_job("vilkas") is FORMS_JOB


def test_mechanical_forms_need_no_call(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "house", "noun", {"lt": "namas"})
    report = start_batch_run(
        session, manager, FORMS_JOB, [forms_state(lemma.id, "lt", "noun")], _MODEL
    )
    assert report.calls == 0
    assert report.resolved_without_llm == {"written": 1}
    assert batch_client.batches == {}
    stored = _forms(session, lemma, "lt")
    assert "namai" in stored.values()
    assert "namų" in stored.values()


def test_llm_noun_batch_matches_live_call_and_stores_forms(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "house", "noun", {"de": "Haus"})
    report = start_batch_run(
        session, manager, FORMS_JOB, [forms_state(lemma.id, "de", "noun")], _MODEL
    )
    assert report.calls == 1
    body = batch_client.batches["batch-0"][0]["body"]

    spec = FORM_SPECS[("de", "noun")]
    answer_forms = {field: f"{field}-form" for field in spec.form_fields}
    live = _RecordingClient({"forms": answer_forms, "confidence": 0.9, "notes": ""})
    query_forms(spec, live, lemma.id, lambda: session)  # type: ignore[arg-type]
    assert body["input"] == live.calls[0]["prompt"]
    assert body["instructions"] == live.calls[0]["context"]

    result = _complete(
        manager,
        batch_client,
        session,
        "batch-0",
        {"forms": answer_forms, "confidence": 0.9, "notes": ""},
    )
    assert result["updated"] == 1
    stored = _forms(session, lemma, "de")
    assert len(stored) == len({spec.form_mapping[f].value for f in spec.form_fields})
    logged = session.query(QueryLog).filter_by(query_type=spec.query_type).all()
    assert any("OpenAI batch" in (row.prompt or "") for row in logged)


def test_llm_verb_batch_matches_live_call(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "to sing", "verb", {"de": "singen"})
    start_batch_run(session, manager, FORMS_JOB, [forms_state(lemma.id, "de", "verb")], _MODEL)
    body = batch_client.batches["batch-0"][0]["body"]

    live = _RecordingClient({"forms": {}, "confidence": 0.9, "notes": ""})
    query_forms(FORM_SPECS[("de", "verb")], live, lemma.id, lambda: session)  # type: ignore[arg-type]
    assert body["input"] == live.calls[0]["prompt"]
    assert body["instructions"] == live.calls[0]["context"]


def test_complete_forms_are_skipped(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "house", "noun", {"lt": "namas"})
    start_batch_run(session, manager, FORMS_JOB, [forms_state(lemma.id, "lt", "noun")], _MODEL)
    report = start_batch_run(
        session, manager, FORMS_JOB, [forms_state(lemma.id, "lt", "noun")], _MODEL
    )
    assert report.resolved_without_llm == {"skipped": 1}


def test_hand_entered_form_survives_batch(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "house", "noun", {"de": "Haus"})
    start_batch_run(session, manager, FORMS_JOB, [forms_state(lemma.id, "de", "noun")], _MODEL)
    spec = FORM_SPECS[("de", "noun")]
    first_field = spec.form_fields[0]
    grammatical_form = spec.form_mapping[first_field].value
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="Haus (by hand)",
            language_code="de",
            grammatical_form=grammatical_form,
            is_base_form=False,
            verified=True,
        )
    )
    session.commit()

    answer_forms = {field: f"{field}-form" for field in spec.form_fields}
    _complete(manager, batch_client, session, "batch-0", {"forms": answer_forms, "confidence": 0.9})
    assert _forms(session, lemma, "de")[grammatical_form] == "Haus (by hand)"
    assert len(_forms(session, lemma, "de")) > 1


def test_low_confidence_forms_are_recorded_and_skipped_unless_retried(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "house", "noun", {"de": "Haus"})
    start_batch_run(session, manager, FORMS_JOB, [forms_state(lemma.id, "de", "noun")], _MODEL)
    spec = FORM_SPECS[("de", "noun")]
    answer_forms = {field: f"{field}-form" for field in spec.form_fields}

    result = _complete(
        manager,
        batch_client,
        session,
        "batch-0",
        {"forms": answer_forms, "confidence": 0.5, "notes": "unsure of the plural"},
    )

    assert result["updated"] == 0
    assert _forms(session, lemma, "de") == {}
    row = get_uncertain_llm_result(session, TOPIC_FORMS, "de", lemma_id=lemma.id)
    assert row is not None
    assert row.note is not None
    assert row.note.startswith(f"{_MODEL} leaned ")
    assert row.note.endswith("(0.50): unsure of the plural")

    skipped = start_batch_run(
        session, manager, FORMS_JOB, [forms_state(lemma.id, "de", "noun")], _MODEL
    )
    retried = start_batch_run(
        session,
        manager,
        FORMS_JOB,
        [forms_state(lemma.id, "de", "noun", retry_uncertain=True)],
        _MODEL,
    )
    assert skipped.resolved_without_llm == {"skipped": 1}
    assert retried.calls == 1


def test_live_query_carries_the_confidence(session: Session) -> None:
    lemma = _lemma(session, "house", "noun", {"de": "Haus"})
    spec = FORM_SPECS[("de", "noun")]
    live = _RecordingClient(
        {"forms": {spec.form_fields[0]: "Haus"}, "confidence": 0.4, "notes": "rare word"}
    )

    answer = query_forms(spec, live, lemma.id, lambda: session)  # type: ignore[arg-type]

    forms, success = answer
    assert (forms, success) == ({spec.form_fields[0]: "Haus"}, True)
    assert forms_answer_confidence(answer) == 0.4
    assert forms_answer_notes(answer) == "rare word"
    assert forms_answer_confidence(({}, False)) is None


def test_dry_run_prepares_nothing(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "house", "noun", {"lt": "namas", "de": "Haus"})
    report = start_batch_run(
        session,
        manager,
        FORMS_JOB,
        [forms_state(lemma.id, "lt", "noun"), forms_state(lemma.id, "de", "noun")],
        _MODEL,
        dry_run=True,
    )
    assert report.unprepared == 2
    assert _forms(session, lemma, "lt") == {}
    assert session.query(QueryLog).count() == 0


def test_wrong_pos_and_missing_translation_are_rejected(
    session: Session, manager: BatchQueueManager
) -> None:
    verb = _lemma(session, "to sing", "verb", {"de": "singen"})
    noun = _lemma(session, "tree", "noun", {})
    report = start_batch_run(
        session,
        manager,
        FORMS_JOB,
        [forms_state(verb.id, "de", "noun"), forms_state(noun.id, "de", "noun")],
        _MODEL,
    )
    assert report.calls == 0
    assert report.resolved_without_llm == {"rejected": 2}


# What vilkas offers (and so what --batch can be asked for).
_ON_DEMAND = sorted(
    (language_code, pos_type)
    for language_code, pos_types in get_on_demand_pos_types().items()
    for pos_type in pos_types
)


@pytest.mark.parametrize("language_code,pos_type", _ON_DEMAND)
def test_every_generator_defers_or_answers(
    session: Session, language_code: str, pos_type: str
) -> None:
    """No generator may swallow the deferral and report a plain failure."""
    spec = FORM_SPECS[(language_code, pos_type)]
    translations = {} if spec.is_source_language else {language_code: "testword"}
    lemma = _lemma(session, "testword", pos_type, translations)
    try:
        forms, success = generate_forms(
            language_code, pos_type, DeferringClient(_MODEL), lemma.id, lambda: session
        )
    except DeferLLMCall as deferred:
        assert isinstance(deferred.call, LLMCall)
        assert deferred.call.prompt
        return
    assert success and forms, f"{language_code} {pos_type} neither deferred nor answered"
