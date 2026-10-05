"""Tests for the request/response pieces shared by live OpenAI calls and batches.

The Batch API path must send exactly what ``OpenAIClient.generate_chat`` sends,
so these pin the shared builder against the live client, cover the batch-result
parser, the ``extra`` metadata round trip on ``BatchQueue`` rows, and the kill
switch on batch submission.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterator
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from clients.batch_queue import (
    BatchQueueManager,
    BatchRequestMetadata,
    create_batch_database_session,
    request_extra,
    update_request_extra,
)
from clients.lib import LLMCallsDisabledError
from clients.openai.batch_client import OpenAIBatchClient, batch_response_text
from clients.openai.client import (
    OpenAIClient,
    build_responses_request,
    parse_responses_output,
)
from clients.types import LLMCall, Schema, SchemaProperty

_SCHEMA = Schema(
    name="Gender",
    description="Pick a gender",
    properties={
        "gender": SchemaProperty("string", "The gender", enum=["masculine", "feminine"]),
        "confidence": SchemaProperty("number", "0-1", minimum=0.0, maximum=1.0),
    },
)


@pytest.fixture(autouse=True)
def _no_schema_size_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests are about request shape; the schema size guard has its own tests.

    Counting needs tiktoken's downloaded encoding, which some sandboxes cannot
    fetch, and the conftest would then skip every test here.
    """
    monkeypatch.setattr("clients.lib.count_schema_tokens", lambda schema_dict: 0)


def _message_body(text: str) -> Dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "thinking"}]},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.mark.parametrize("model", ["gpt-6-luna", "gpt-5.4-mini", "gpt-5-mini", "gpt-4o"])
def test_build_matches_what_generate_chat_sends(model: str) -> None:
    sent: Dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> Any:
        sent.update(kwargs)
        return _message_body('{"gender": "feminine", "confidence": 0.9}'), 12.0

    client = OpenAIClient(api_key="test-key")
    with patch.object(client, "_create_response", side_effect=fake_create):
        client.generate_chat(
            prompt="la table", model=model, json_schema=_SCHEMA, context="You are a linguist"
        )

    built = build_responses_request(
        model, "la table", context="You are a linguist", json_schema=_SCHEMA
    )
    assert built == sent


def test_llm_call_chat_kwargs_build_the_same_request() -> None:
    call = LLMCall(prompt="p", schema=_SCHEMA, context="c", max_tokens=300)
    kwargs = call.chat_kwargs()
    built = build_responses_request(
        "gpt-6-luna",
        kwargs["prompt"],
        context=kwargs["context"],
        json_schema=kwargs["json_schema"],
        max_tokens=kwargs["max_tokens"],
    )
    assert built["input"] == "p"
    assert built["instructions"] == "c"
    assert built["max_output_tokens"] == 300
    assert built["text"]["format"]["type"] == "json_schema"


def test_parse_responses_output_returns_text_and_reasoning() -> None:
    text, reasoning = parse_responses_output(_message_body("hello"))
    assert text == "hello"
    assert reasoning == "thinking"


def test_parse_responses_output_empty_body() -> None:
    assert parse_responses_output({}) == ("", None)


def test_batch_response_text_reads_body() -> None:
    assert batch_response_text({"status_code": 200, "body": _message_body("{}")}) == "{}"


def test_batch_response_text_refuses_incomplete() -> None:
    body = _message_body('{"gend')
    body["status"] = "incomplete"
    body["incomplete_details"] = {"reason": "max_output_tokens"}
    with pytest.raises(ValueError, match="incomplete"):
        batch_response_text({"body": body})


def test_batch_response_text_refuses_empty() -> None:
    with pytest.raises(ValueError, match="no output text"):
        batch_response_text({"body": {"output": []}})


@pytest.fixture
def batch_session(tmp_path: Path) -> Iterator[Session]:
    session = create_batch_database_session(str(tmp_path / "batch_tracking.sqlite"))
    try:
        yield session
    finally:
        session.close()


class _NoClient:
    """Stands in for OpenAIBatchClient where no request may be sent."""


def test_extra_round_trips_and_merges(batch_session: Session) -> None:
    manager = BatchQueueManager(batch_session, batch_client=_NoClient())  # type: ignore[arg-type]
    row = manager.queue_request(
        custom_id="job:run1:0:a",
        request_body={"model": "m"},
        metadata=BatchRequestMetadata(
            custom_id="job:run1:0:a",
            agent_name="job",
            operation_type="stage",
            extra={"run_id": "run1", "state": {"lemma_id": 3}},
        ),
    )
    assert request_extra(row) == {"run_id": "run1", "state": {"lemma_id": 3}}

    update_request_extra(row, applied=True)
    batch_session.commit()
    assert request_extra(row) == {"run_id": "run1", "state": {"lemma_id": 3}, "applied": True}
    # The fixed metadata fields are still there.
    metadata = BatchRequestMetadata.from_dict(json.loads(row.additional_metadata or "{}"))
    assert metadata.agent_name == "job"


def test_request_extra_is_empty_for_legacy_rows(batch_session: Session) -> None:
    manager = BatchQueueManager(batch_session, batch_client=_NoClient())  # type: ignore[arg-type]
    row = manager.queue_request(
        custom_id="voras_populate_1_abc",
        request_body={},
        metadata=BatchRequestMetadata(
            custom_id="voras_populate_1_abc", agent_name="voras", operation_type="x"
        ),
    )
    assert request_extra(row) == {}


def test_prefix_query_escapes_wildcards(batch_session: Session) -> None:
    manager = BatchQueueManager(batch_session, batch_client=_NoClient())  # type: ignore[arg-type]
    for custom_id in ("lape:run_1:0:a", "lape:run_1:0:b", "lape:runX1:0:c", "voras:run_1:0:d"):
        manager.queue_request(
            custom_id=custom_id,
            request_body={},
            metadata=BatchRequestMetadata(custom_id=custom_id, agent_name="x", operation_type="y"),
        )
    rows = manager.get_requests_by_custom_id_prefix("lape:run_1:")
    assert [row.custom_id for row in rows] == ["lape:run_1:0:a", "lape:run_1:0:b"]


@pytest.mark.parametrize("switch", ["GREENLAND_DISABLE_LLM", "GREENLAND_TEST_MODE"])
def test_batch_submission_honours_kill_switches(
    monkeypatch: pytest.MonkeyPatch, switch: str
) -> None:
    monkeypatch.setenv(switch, "1")
    with patch("clients.openai.batch_client.load_key", return_value="test-key"):
        client = OpenAIBatchClient()
    with patch("clients.openai.batch_client.requests.post") as post:
        with pytest.raises(LLMCallsDisabledError):
            client.upload_batch_file([{"custom_id": "a"}])
        with pytest.raises(LLMCallsDisabledError):
            client.create_batch("file-1")
        post.assert_not_called()
