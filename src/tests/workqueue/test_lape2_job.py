"""Lape2 requests round-trip through real batch tracking with a fake provider."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.lape2.job import LAPE2_JOB
from agents.lape2.planner import plan_request, stored_values
from agents.lape2.query import build_query
from clients.batch_queue import BatchQueueManager, create_batch_database_session
from storage.models import Base, Lemma
from storage.translation_helpers import set_translation
from workqueue.llm_batch import complete_rows, start_batch_run


class FakeBatchClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.data: dict[str, Any] = {}

    def upload_batch_file(self, requests_data: list[dict[str, Any]]) -> str:
        self.requests = requests_data
        return "fake-file"

    def create_batch(self, input_file_id: str, endpoint: str = "", **kwargs: Any) -> dict[str, str]:
        return {"id": "fake-batch"}

    def get_batch_status(self, batch_id: str) -> dict[str, str]:
        return {"id": batch_id, "status": "completed", "output_file_id": "fake-output"}

    def download_batch_results(self, output_file_id: str) -> list[dict[str, Any]]:
        return [
            {
                "custom_id": request["custom_id"],
                "response": {
                    "status_code": 200,
                    "body": {
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "content": [{"type": "output_text", "text": json.dumps(self.data)}],
                            }
                        ],
                    },
                },
            }
            for request in self.requests
        ]


@pytest.mark.parametrize("stale", [False, True])
def test_batch_uses_same_query_and_saved_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stale: bool
) -> None:
    monkeypatch.setattr("clients.lib.count_schema_tokens", lambda schema_dict: 0)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    batch_session = create_batch_database_session(str(tmp_path / "batch.sqlite"))
    provider = FakeBatchClient()
    manager = BatchQueueManager(batch_session, batch_client=provider)  # type: ignore[arg-type]
    try:
        with Session(engine) as session:
            word = Lemma(
                lemma_text="cat", guid="N08_999", pos_type="noun", definition_text="An animal"
            )
            session.add(word)
            session.flush()
            set_translation(session, word, "fr", "chat")
            session.commit()
            state = {
                "lemma_id": word.id,
                "languages": ["en", "fr"],
                "facts": ["countability"],
                "min_confidence": 0.7,
            }
            expected = build_query(
                plan_request(session, word, ["en", "fr"], facts=["countability"])
            )
            report = start_batch_run(session, manager, LAPE2_JOB, [state], "gpt-6-luna")
            assert report.calls == 1 and len(provider.requests) == 1
            body = provider.requests[0]["body"]
            assert body["input"] == expected.prompt
            assert body["instructions"] == expected.context
            assert set(body["text"]["format"]["schema"]["properties"]) == {
                "en__countability",
                "fr__countability",
            }
            # Different filters still deduplicate the same in-flight lemma.
            duplicate = start_batch_run(
                session,
                manager,
                LAPE2_JOB,
                [{**state, "languages": ["fr"]}],
                "gpt-6-luna",
                dry_run=True,
            )
            assert duplicate.skipped_in_flight == 1
            if stale:
                word.definition_text = "A different sense"
                session.commit()
            provider.data = {
                identifier: {
                    "value": "countable",
                    "confidence": 0.95,
                    "explanation": "For this sense",
                }
                for identifier in ("en__countability", "fr__countability")
            }
            manager.retrieve_batch_results("fake-batch")
            rows = manager.get_completed_requests(batch_id="fake-batch")
            result = complete_rows(LAPE2_JOB, rows, session, "fake-batch", manager)
            if stale:
                assert result["failed"] == 1
                assert not stored_values(session, word.id)
            else:
                assert result["updated"] == 1
                assert stored_values(session, word.id) == {
                    "en__countability": "countable",
                    "fr__countability": "countable",
                }
                # Redelivering a completed batch cannot add duplicate facts.
                complete_rows(LAPE2_JOB, rows, session, "fake-batch", manager)
                assert len(stored_values(session, word.id)) == 2
    finally:
        batch_session.close()
        engine.dispose()
