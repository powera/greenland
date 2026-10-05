"""Tests for SENTENCE_TRANSLATION_JOB: the sentence pipeline as a staged LLM job.

Stage 1 is Phase 1 (translate, persist); stage 2 is Phases 2+3 (candidate
lookup, combined decomposition), prepared after every sentence of the run has
its translations.  Both are built from the live path's own plan and requests.
"""

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.batch_queue import BatchQueueManager, create_batch_database_session
from sentences.candidate_lookup import CandidateLemma
from sentences.translate_and_decompose import build_phase1_prompt
from storage.models.schema import Base, Sentence, SentenceTranslation, SentenceWord
from workqueue.handlers.sentences.translation import (
    SENTENCE_TRANSLATION_JOB,
    sentence_translation_state,
)
from workqueue.llm_batch import complete_rows, start_batch_run
from workqueue.registry import get_llm_job

_MODEL = "gpt-6-luna"


@pytest.fixture(autouse=True)
def _no_schema_size_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Request shape only; counting schema tokens needs tiktoken's downloaded data."""
    monkeypatch.setattr("clients.lib.count_schema_tokens", lambda schema_dict: 0)


@pytest.fixture(autouse=True)
def _one_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2 needs a lemma to match; these tests are about the job, not the lookup."""
    candidate = CandidateLemma(
        guid="N01_001",
        lemma_text="dog",
        disambiguation="",
        pos="noun",
        definition="a canine",
        translations={"fr": "chien"},
    )
    monkeypatch.setattr(
        "sentences.translate_and_decompose.lookup_candidate_lemmas",
        lambda **kwargs: [candidate],
    )


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


def _sentence(session: Session, translations: Dict[str, str]) -> Sentence:
    sentence = Sentence(pattern_type="SVO", tense="present")
    session.add(sentence)
    session.flush()
    for language_code, text in translations.items():
        session.add(
            SentenceTranslation(
                sentence_id=sentence.id, language_code=language_code, translation_text=text
            )
        )
    session.commit()
    return sentence


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
    return complete_rows(SENTENCE_TRANSLATION_JOB, rows, session, batch_id, manager)


_PHASE1_ANSWER = {
    "fr": "Le chien dort.",
    "lt": "Šuo miega.",
    "zh": "狗在睡觉。",
    "es": "El perro duerme.",
    "hi": "कुत्ता सो रहा है।",
    "vi": "Con chó đang ngủ.",
    "ms": "Anjing sedang tidur.",
}


def _words(text: str) -> List[Dict[str, Any]]:
    return [
        {
            "position": index,
            "surface_form": token,
            "lemma_guid": "NONE",
            "part_of_speech": "x",
            "english_gloss": token,
        }
        for index, token in enumerate(text.rstrip(".").split())
    ]


def test_job_is_registered() -> None:
    assert get_llm_job("zvirblis") is SENTENCE_TRANSLATION_JOB


def test_two_stages_translate_then_decompose(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    sentence = _sentence(session, {"en": "The dog sleeps."})
    report = start_batch_run(
        session,
        manager,
        SENTENCE_TRANSLATION_JOB,
        [sentence_translation_state(sentence.id, ["fr"])],
        _MODEL,
    )
    assert report.calls == 1
    phase1_body = batch_client.batches["batch-0"][0]["body"]

    # The Phase-1 request is the live path's.
    built = build_phase1_prompt(
        sentence_text="The dog sleeps.",
        source_language="en",
        target_languages=["fr", "lt", "zh", "es", "hi", "vi", "ms"],
    )
    assert built is not None
    context, prompt, _full, _schema, _targets = built
    assert phase1_body["input"] == prompt
    assert phase1_body["instructions"] == context

    first = _complete(manager, batch_client, session, "batch-0", _PHASE1_ANSWER)
    assert first["carried"] == 1
    assert first["next_stage_calls"] == 1
    stored = {
        row.language_code: row.translation_text
        for row in session.query(SentenceTranslation).filter_by(sentence_id=sentence.id)
    }
    assert stored["fr"] == "Le chien dort."

    phase3_body = batch_client.batches["batch-1"][0]["body"]
    assert "Le chien dort." in phase3_body["input"]
    # No Phase-4 dependency fields are asked for.
    assert "ud_relation" not in json.dumps(phase3_body)

    second = _complete(
        manager,
        batch_client,
        session,
        "batch-1",
        {"words_fr": _words("Le chien dort."), "words_en": _words("The dog sleeps.")},
    )
    assert second["updated"] == 1
    words = session.query(SentenceWord).filter_by(sentence_id=sentence.id).all()
    assert {word.language_code for word in words} == {"fr", "en"}
    assert len(batch_client.batches) == 2


def test_translate_only_stops_after_phase_one(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    sentence = _sentence(session, {"en": "The dog sleeps.", "fr": "Le chien dort."})
    start_batch_run(
        session,
        manager,
        SENTENCE_TRANSLATION_JOB,
        [
            sentence_translation_state(
                sentence.id, ["fr", "lt"], decompose=False, skip_existing_translations=True
            )
        ],
        _MODEL,
    )
    phase1_body = batch_client.batches["batch-0"][0]["body"]
    # Already translated into French: not asked again.
    assert '"fr"' not in json.dumps(phase1_body["text"]["format"]["schema"]["properties"])
    result = _complete(manager, batch_client, session, "batch-0", _PHASE1_ANSWER)
    assert result["updated"] == 1
    assert len(batch_client.batches) == 1


def test_decompose_only_skips_phase_one(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    sentence = _sentence(session, {"en": "The dog sleeps.", **_PHASE1_ANSWER})
    report = start_batch_run(
        session,
        manager,
        SENTENCE_TRANSLATION_JOB,
        [
            sentence_translation_state(
                sentence.id, ["fr"], translate=False, decompose_languages=["fr"]
            )
        ],
        _MODEL,
    )
    assert report.calls == 0
    assert report.resolved_without_llm == {"carried": 1}
    body = batch_client.batches["batch-0"][0]["body"]
    assert "Le chien dort." in body["input"]


def test_phase_three_waits_for_every_phase_one(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    first = _sentence(session, {"en": "The dog sleeps."})
    second = _sentence(session, {"en": "The cat sleeps."})
    start_batch_run(
        session,
        manager,
        SENTENCE_TRANSLATION_JOB,
        [
            sentence_translation_state(first.id, ["fr"]),
            sentence_translation_state(second.id, ["fr"]),
        ],
        _MODEL,
    )
    assert len(batch_client.batches) == 1
    result = _complete(manager, batch_client, session, "batch-0", _PHASE1_ANSWER)
    assert result["next_stage_calls"] == 2
    assert len(batch_client.batches["batch-1"]) == 2


def test_failed_phase_one_does_not_decompose(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    sentence = _sentence(session, {"en": "The dog sleeps."})
    start_batch_run(
        session,
        manager,
        SENTENCE_TRANSLATION_JOB,
        [sentence_translation_state(sentence.id, ["fr"])],
        _MODEL,
    )
    result = _complete(manager, batch_client, session, "batch-0", {"fr": ""})
    assert result["failed"] == 1
    assert len(batch_client.batches) == 1


def test_missing_sentence_is_rejected(session: Session, manager: BatchQueueManager) -> None:
    report = start_batch_run(
        session,
        manager,
        SENTENCE_TRANSLATION_JOB,
        [sentence_translation_state(999, ["fr"])],
        _MODEL,
    )
    assert report.resolved_without_llm == {"rejected": 1}
