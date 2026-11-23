"""Ežys definition requests round-trip through real batch tracking with a fake provider."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.batch_queue import BatchQueueManager, create_batch_database_session
from storage.models import Base, Lemma
from storage.translation_helpers import get_definition, set_definition, set_translation
from words.definition_populate import build_definition_call
from workqueue.handlers.words.definitions import DEFINITIONS_JOB
from workqueue.llm_batch import complete_rows, start_batch_run
from workqueue.registry import get_llm_job


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


def test_job_is_registered_for_the_batch_poller() -> None:
    assert get_llm_job("ezys") is DEFINITIONS_JOB


@pytest.mark.parametrize("defined_meanwhile", [False, True])
def test_batch_sends_the_shared_call_and_stores_the_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defined_meanwhile: bool
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
                lemma_text="cat",
                guid="N08_998",
                pos_type="noun",
                definition_text="A small furry animal kept as a pet.",
            )
            session.add(word)
            session.flush()
            set_translation(session, word, "fr", "chat")
            set_translation(session, word, "lt", "katė")
            session.commit()
            state = {"lemma_id": word.id, "languages": ["fr", "lt"], "min_confidence": 0.7}

            expected = build_definition_call(session, word, ["fr", "lt"])
            report = start_batch_run(session, manager, DEFINITIONS_JOB, [state], "gpt-6-luna")
            assert report.calls == 1 and len(provider.requests) == 1
            body = provider.requests[0]["body"]
            assert body["input"] == expected.prompt
            assert body["instructions"] == expected.context
            assert set(body["text"]["format"]["schema"]["properties"]) == {"fr", "lt"}

            if defined_meanwhile:
                set_definition(session, word, "fr", "Défini à la main.")
                session.commit()
            provider.data = {
                "fr": {"definition": "Petit animal domestique qui miaule.", "confidence": 0.9},
                "lt": {"definition": "Naminis gyvūnas, kuris miaukia.", "confidence": 0.9},
            }
            manager.retrieve_batch_results("fake-batch")
            rows = manager.get_completed_requests(batch_id="fake-batch")
            result = complete_rows(DEFINITIONS_JOB, rows, session, "fake-batch", manager)

            assert result["updated"] == 1
            assert get_definition(session, word, "lt") == "Naminis gyvūnas, kuris miaukia."
            expected_fr = (
                "Défini à la main." if defined_meanwhile else "Petit animal domestique qui miaule."
            )
            assert get_definition(session, word, "fr") == expected_fr
    finally:
        batch_session.close()
        engine.dispose()
