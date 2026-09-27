"""Tests for the OpenAI Batch lemma-translation populate path."""

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
from storage.models.schema import Base, Lemma
from storage.translation_helpers import get_translation, lang_code_to_llm_field, set_translation
from words.translation_batch import (
    AGENT_NAME,
    OPERATION_TYPE,
    PopulatePlan,
    PopulateRequest,
    apply_populate_results,
    build_request_body,
    chunk_by_lemma,
    find_in_flight_lemma_ids,
    plan_populate_requests,
    submit_populate_batches,
)
from wordfreq.translation.translations import build_translation_prompt

_MODEL = "gpt-6-luna"


class _FakeBatchClient:
    """Stands in for OpenAIBatchClient: records uploads, returns fixed ids."""

    def __init__(self, fail_on_create: bool = False) -> None:
        self.uploads: List[List[Dict[str, Any]]] = []
        self.fail_on_create = fail_on_create

    def upload_batch_file(self, requests: List[Dict[str, Any]]) -> str:
        self.uploads.append(requests)
        return f"file_{len(self.uploads)}"

    def create_batch(
        self, file_id: str, endpoint: str, metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        if self.fail_on_create:
            raise RuntimeError("upstream unavailable")
        return {"id": f"batch_{file_id}"}


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


def test_plan_asks_each_lemma_only_for_its_missing_languages(session: Session) -> None:
    partial = _add_lemma(session, "dog", {"lt": "šuo", "hi": "कुत्ता"})
    _add_lemma(session, "cat", {"lt": "katė", "hi": "बिल्ली", "vi": "mèo", "ms": "kucing"})

    plan = plan_populate_requests(session, session.query(Lemma).all(), ["hi", "vi", "ms"], _MODEL)

    assert plan.lemmas_complete == 1
    assert [(r.lemma_id, r.languages) for r in plan.requests] == [(partial.id, ["vi", "ms"])]
    assert plan.missing_by_language() == {"vi": 1, "ms": 1}


def test_plan_splits_more_than_ten_languages_and_skips_in_flight(session: Session) -> None:
    languages = ["de", "it", "nl", "pt", "sv", "ja", "ko", "sw", "hi", "vi", "ms"]
    lemma = _add_lemma(session, "dog", {"lt": "šuo"})
    busy = _add_lemma(session, "cat", {"lt": "katė"})

    plan = plan_populate_requests(
        session, [lemma, busy], languages, _MODEL, in_flight_lemma_ids={busy.id}
    )

    assert plan.lemmas_skipped_in_flight == 1
    assert [len(r.languages) for r in plan.requests] == [10, 1]
    assert {r.lemma_id for r in plan.requests} == {lemma.id}


def test_request_body_mirrors_the_live_responses_call() -> None:
    prompt = build_translation_prompt("dog", ("lt", "šuo"), "a canine", "noun", languages=["hi"])
    assert prompt is not None

    body = build_request_body(prompt, _MODEL)

    assert body["model"] == _MODEL
    assert body["instructions"] == prompt.context
    assert body["input"] == prompt.prompt
    assert body["reasoning"] == {"effort": "none"}
    assert body["text"]["format"]["strict"] is True
    assert _field("hi") in body["text"]["format"]["schema"]["properties"]


def test_chunks_hold_whole_lemmas() -> None:
    requests = [
        PopulateRequest(lemma_id=1, languages=["hi"], body={}),
        PopulateRequest(lemma_id=1, languages=["vi"], body={}),
        PopulateRequest(lemma_id=2, languages=["hi"], body={}),
        PopulateRequest(lemma_id=3, languages=["hi"], body={}),
    ]

    chunks = chunk_by_lemma(requests, lemmas_per_batch=2)

    assert [[r.lemma_id for r in chunk] for chunk in chunks] == [[1, 1, 2], [3]]


def test_submit_sends_one_batch_per_chunk(batch_session: Session) -> None:
    client = _FakeBatchClient()
    manager = BatchQueueManager(batch_session, batch_client=client)  # type: ignore[arg-type]
    plan = PopulatePlan(
        requests=[
            PopulateRequest(lemma_id=lemma_id, languages=["hi"], body={"model": _MODEL})
            for lemma_id in (1, 2, 3)
        ]
    )

    submitted = submit_populate_batches(manager, plan, lemmas_per_batch=2)

    assert [(b.batch_id, b.lemma_count) for b in submitted] == [
        ("batch_file_1", 2),
        ("batch_file_2", 1),
    ]
    assert [len(upload) for upload in client.uploads] == [2, 1]
    assert find_in_flight_lemma_ids(batch_session) == {1, 2, 3}


def test_failed_submission_cancels_its_rows(batch_session: Session) -> None:
    manager = BatchQueueManager(
        batch_session, batch_client=_FakeBatchClient(fail_on_create=True)  # type: ignore[arg-type]
    )
    plan = PopulatePlan(requests=[PopulateRequest(lemma_id=1, languages=["hi"], body={})])

    with pytest.raises(RuntimeError):
        submit_populate_batches(manager, plan)

    statuses = {row.status for row in batch_session.query(BatchQueue).all()}
    assert statuses == {BatchRequestStatus.CANCELLED.value}
    assert find_in_flight_lemma_ids(batch_session) == set()


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
