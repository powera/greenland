"""Tests for voras's populate as a staged batch job, and the legacy batch applier.

New runs go through TRANSLATIONS_JOB (workqueue.llm_batch); rows submitted
before that are applied by words.translation_batch.apply_populate_results.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.batch_queue import (
    BatchQueue,
    BatchQueueManager,
    BatchRequestMetadata,
    BatchRequestStatus,
    create_batch_database_session,
)
from clients.openai.client import build_responses_request
from storage.crud.uncertain_llm_result import get_uncertain_llm_result, record_uncertain_llm_result
from storage.models.schema import Base, Lemma
from storage.models.uncertain_llm_result import REASON_LOW_CONFIDENCE, TOPIC_TRANSLATION
from storage.translation_helpers import get_translation, lang_code_to_llm_field, set_translation
from words.translation_batch import (
    AGENT_NAME,
    OPERATION_TYPE,
    apply_populate_results,
    find_in_flight_lemma_ids,
)
from wordfreq.translation.translations import build_translation_prompt
from workqueue.handlers.words.translations import TRANSLATIONS_JOB, translation_populate_states
from workqueue.llm_batch import complete_rows, start_batch_run
from workqueue.registry import get_llm_job

_MODEL = "gpt-6-luna"


class _FakeBatchClient:
    """Stands in for OpenAIBatchClient: records uploads and serves set results."""

    def __init__(self, fail_on_create: bool = False) -> None:
        self.uploads: List[List[Dict[str, Any]]] = []
        self.fail_on_create = fail_on_create
        self.results: Dict[str, List[Dict[str, Any]]] = {}

    def upload_batch_file(self, requests: List[Dict[str, Any]]) -> str:
        self.uploads.append(requests)
        return f"file_{len(self.uploads)}"

    def create_batch(
        self, file_id: str, endpoint: str, metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        if self.fail_on_create:
            raise RuntimeError("upstream unavailable")
        return {"id": f"batch_{file_id}"}

    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        status = "completed" if batch_id in self.results else "in_progress"
        return {"id": batch_id, "status": status, "output_file_id": batch_id}

    def download_batch_results(self, output_file_id: str) -> List[Dict[str, Any]]:
        return self.results[output_file_id]

    def finish(self, batch_id: str, upload_index: int, structured: Dict[str, Any]) -> None:
        self.results[batch_id] = [
            {
                "custom_id": line["custom_id"],
                "response": json.loads(_responses_envelope(structured)),
            }
            for line in self.uploads[upload_index]
        ]


@pytest.fixture(autouse=True)
def _no_schema_size_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request shape only; counting schema tokens needs tiktoken's downloaded data."""
    monkeypatch.setattr("clients.lib.count_schema_tokens", lambda schema_dict: 0)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def batch_session(tmp_path: Path) -> Iterator[Session]:
    db_session = create_batch_database_session(str(tmp_path / "batch_tracking.sqlite"))
    yield db_session
    db_session.close()


def _add_lemma(session: Session, text: str, translations: Dict[str, str]) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=f"definition of {text}",
        pos_type="noun",
        guid=f"N00_{text}",
    )
    session.add(lemma)
    session.flush()
    for language_code, value in translations.items():
        set_translation(session, lemma, language_code, value)
    session.commit()
    return lemma


def _responses_envelope(structured: Dict[str, Any], status: str = "completed") -> str:
    """A stored batch result, as BatchQueueManager.retrieve_batch_results saves it."""
    return json.dumps(
        {
            "status_code": 200,
            "body": {
                "status": status,
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(structured)}],
                    },
                ],
            },
        }
    )


def _completed_row(
    lemma_id: int, structured: Dict[str, Any], status: str = "completed"
) -> BatchQueue:
    return BatchQueue(
        custom_id=f"voras_populate_{lemma_id}_test",
        request_body=json.dumps({"model": _MODEL}),
        endpoint="/v1/responses",
        status=BatchRequestStatus.COMPLETED.value,
        agent_name=AGENT_NAME,
        operation_type=OPERATION_TYPE,
        entity_id=lemma_id,
        entity_type="lemma",
        response_body=_responses_envelope(structured, status=status),
    )


def _field(language_code: str) -> str:
    field_name = lang_code_to_llm_field(language_code)
    assert field_name is not None
    return field_name


def test_job_is_registered() -> None:
    assert get_llm_job("voras") is TRANSLATIONS_JOB


def test_states_ask_each_lemma_only_for_its_missing_languages(session: Session) -> None:
    partial = _add_lemma(session, "dog", {"lt": "šuo", "hi": "कुत्ता"})
    _add_lemma(session, "cat", {"lt": "katė", "hi": "बिल्ली", "vi": "mèo", "ms": "kucing"})

    states, complete = translation_populate_states(
        session, session.query(Lemma).all(), ["hi", "vi", "ms"]
    )

    assert complete == 1
    assert states == [{"lemma_id": partial.id, "languages": ["vi", "ms"], "retry_uncertain": False}]


def test_states_skip_uncertain_languages_unless_retried(session: Session) -> None:
    lemma = _add_lemma(session, "skewer", {"lt": "iešmas"})
    record_uncertain_llm_result(
        session, TOPIC_TRANSLATION, "vi", REASON_LOW_CONFIDENCE, lemma_id=lemma.id
    )

    skipped, _complete = translation_populate_states(session, [lemma], ["hi", "vi"])
    retried, _complete = translation_populate_states(
        session, [lemma], ["hi", "vi"], retry_uncertain=True
    )

    assert [state["languages"] for state in skipped] == [["hi"]]
    assert [state["languages"] for state in retried] == [["hi", "vi"]]


def test_lemma_with_only_uncertain_gaps_is_not_asked(
    session: Session, batch_session: Session
) -> None:
    lemma = _add_lemma(session, "skewer", {"lt": "iešmas"})
    record_uncertain_llm_result(
        session, TOPIC_TRANSLATION, "hi", REASON_LOW_CONFIDENCE, lemma_id=lemma.id
    )
    manager = BatchQueueManager(batch_session, batch_client=_FakeBatchClient())  # type: ignore[arg-type]

    # A state planned before the row was recorded is skipped when prepared.
    report = start_batch_run(
        session, manager, TRANSLATIONS_JOB, [{"lemma_id": lemma.id, "languages": ["hi"]}], _MODEL
    )

    assert report.calls == 0
    assert report.resolved_without_llm == {"skipped": 1}


def test_set_translation_clears_the_uncertain_row(session: Session) -> None:
    lemma = _add_lemma(session, "skewer", {"lt": "iešmas"})
    record_uncertain_llm_result(
        session, TOPIC_TRANSLATION, "hi", REASON_LOW_CONFIDENCE, lemma_id=lemma.id
    )

    set_translation(session, lemma, "hi", "सीख")

    assert get_uncertain_llm_result(session, TOPIC_TRANSLATION, "hi", lemma_id=lemma.id) is None


def test_states_split_more_than_ten_languages(session: Session) -> None:
    languages = ["de", "it", "nl", "pt", "sv", "ja", "ko", "sw", "hi", "vi", "ms"]
    lemma = _add_lemma(session, "dog", {"lt": "šuo"})

    states, _complete = translation_populate_states(session, [lemma], languages)

    assert [len(state["languages"]) for state in states] == [10, 1]


def test_batch_request_is_the_live_request(session: Session, batch_session: Session) -> None:
    lemma = _add_lemma(session, "dog", {"lt": "šuo"})
    client = _FakeBatchClient()
    manager = BatchQueueManager(batch_session, batch_client=client)  # type: ignore[arg-type]
    states, _complete = translation_populate_states(session, [lemma], ["hi"])

    start_batch_run(session, manager, TRANSLATIONS_JOB, states, _MODEL)

    prompt = build_translation_prompt(
        "dog", ("lt", "šuo"), "definition of dog", "noun", languages=["hi"]
    )
    assert prompt is not None
    assert client.uploads[0][0]["body"] == build_responses_request(
        _MODEL, prompt.prompt, context=prompt.context, json_schema=prompt.schema
    )


def test_batch_writes_missing_languages_and_keeps_hand_edits(
    session: Session, batch_session: Session
) -> None:
    lemma = _add_lemma(session, "dog", {"lt": "šuo"})
    client = _FakeBatchClient()
    manager = BatchQueueManager(batch_session, batch_client=client)  # type: ignore[arg-type]
    states, _complete = translation_populate_states(session, [lemma], ["hi", "vi"])
    report = start_batch_run(session, manager, TRANSLATIONS_JOB, states, _MODEL)
    assert report.calls == 1

    # A hand edit that landed while the batch was running.
    set_translation(session, lemma, "vi", "con chó")
    session.commit()

    batch_id = report.batch_ids[0]
    client.finish(
        batch_id,
        0,
        {_field("hi"): {"translation": "कुत्ता"}, _field("vi"): {"translation": " chó "}},
    )
    manager.retrieve_batch_results(batch_id)
    result = complete_rows(
        TRANSLATIONS_JOB, manager.get_completed_requests(batch_id=batch_id), session, batch_id
    )

    assert result["updated"] == 1
    assert get_translation(session, lemma, "hi") == "कुत्ता"
    assert get_translation(session, lemma, "vi") == "con chó"


def test_lemma_without_reference_is_rejected(session: Session, batch_session: Session) -> None:
    lemma = Lemma(lemma_text="", definition_text="", pos_type="noun", guid="N00_blank")
    session.add(lemma)
    session.commit()
    manager = BatchQueueManager(batch_session, batch_client=_FakeBatchClient())  # type: ignore[arg-type]

    report = start_batch_run(
        session, manager, TRANSLATIONS_JOB, [{"lemma_id": lemma.id, "languages": ["hi"]}], _MODEL
    )

    assert report.calls == 0
    assert report.resolved_without_llm == {"rejected": 1}


def test_failed_submission_cancels_its_rows(session: Session, batch_session: Session) -> None:
    lemma = _add_lemma(session, "dog", {"lt": "šuo"})
    manager = BatchQueueManager(
        batch_session, batch_client=_FakeBatchClient(fail_on_create=True)  # type: ignore[arg-type]
    )
    states, _complete = translation_populate_states(session, [lemma], ["hi"])

    with pytest.raises(RuntimeError):
        start_batch_run(session, manager, TRANSLATIONS_JOB, states, _MODEL)

    statuses = {row.status for row in batch_session.query(BatchQueue).all()}
    assert statuses == {BatchRequestStatus.CANCELLED.value}


def test_legacy_in_flight_lemmas_are_found(batch_session: Session) -> None:
    manager = BatchQueueManager(batch_session, batch_client=_FakeBatchClient())  # type: ignore[arg-type]
    manager.queue_request(
        custom_id="voras_populate_7_x",
        request_body={},
        metadata=BatchRequestMetadata(
            custom_id="voras_populate_7_x",
            agent_name=AGENT_NAME,
            operation_type=OPERATION_TYPE,
            entity_id=7,
        ),
    )

    assert find_in_flight_lemma_ids(batch_session) == {7}


def test_in_flight_ignores_other_agents(batch_session: Session) -> None:
    manager = BatchQueueManager(batch_session, batch_client=_FakeBatchClient())  # type: ignore[arg-type]
    manager.queue_request(
        custom_id="other",
        request_body={},
        metadata=BatchRequestMetadata(
            custom_id="other", agent_name="barsukas_translate", operation_type="x", entity_id=9
        ),
    )

    assert find_in_flight_lemma_ids(batch_session) == set()


def test_apply_writes_missing_languages_and_keeps_existing(session: Session) -> None:
    lemma = _add_lemma(session, "dog", {"lt": "šuo"})
    row = _completed_row(
        lemma.id,
        {_field("hi"): {"translation": "कुत्ता"}, _field("vi"): {"translation": " chó "}},
    )
    # A hand edit that landed while the batch was running.
    set_translation(session, lemma, "vi", "con chó")
    session.commit()

    results = apply_populate_results([row], session, "batch_1")

    assert results == {"processed": 1, "updated": 1, "translations": 1, "failed": 0}
    assert get_translation(session, lemma, "hi") == "कुत्ता"
    assert get_translation(session, lemma, "vi") == "con chó"


def test_apply_counts_incomplete_and_unknown_lemmas_as_failed(session: Session) -> None:
    lemma = _add_lemma(session, "dog", {"lt": "šuo"})
    truncated = _completed_row(lemma.id, {}, status="incomplete")
    orphan = _completed_row(999, {_field("hi"): {"translation": "कुत्ता"}})

    results = apply_populate_results([truncated, orphan], session, "batch_1")

    assert results["failed"] == 2
    assert results["updated"] == 0
    assert get_translation(session, lemma, "hi") is None


def test_populate_schema_rates_each_language() -> None:
    prompt = build_translation_prompt("dog", ("lt", "šuo"), "a canine", "noun", languages=["hi"])

    assert prompt is not None
    rated = prompt.schema.properties[_field("hi")]
    assert set(rated.properties or {}) == {"translation", "confidence"}


def test_batch_gates_each_language_on_its_own_confidence(
    session: Session, batch_session: Session
) -> None:
    lemma = _add_lemma(session, "skewer", {"lt": "iešmas"})
    client = _FakeBatchClient()
    manager = BatchQueueManager(batch_session, batch_client=client)  # type: ignore[arg-type]
    states, _complete = translation_populate_states(session, [lemma], ["hi", "vi", "ms"])
    report = start_batch_run(session, manager, TRANSLATIONS_JOB, states, _MODEL)

    batch_id = report.batch_ids[0]
    client.finish(
        batch_id,
        0,
        {
            _field("hi"): {"translation": "सीख", "confidence": 0.95},
            _field("vi"): {"translation": "xiên", "confidence": 0.4},
            # Sent before the schema asked for a confidence: stored as it is.
            _field("ms"): {"translation": "cucuk"},
        },
    )
    manager.retrieve_batch_results(batch_id)
    complete_rows(
        TRANSLATIONS_JOB, manager.get_completed_requests(batch_id=batch_id), session, batch_id
    )

    assert get_translation(session, lemma, "hi") == "सीख"
    assert get_translation(session, lemma, "vi") is None
    assert get_translation(session, lemma, "ms") == "cucuk"
    row = get_uncertain_llm_result(session, TOPIC_TRANSLATION, "vi", lemma_id=lemma.id)
    assert row is not None
    assert row.note == f"{_MODEL} leaned xiên (0.40)"
