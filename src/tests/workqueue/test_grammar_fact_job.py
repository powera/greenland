"""Tests for GRAMMAR_FACT_JOB: lape's grammar facts as a staged LLM job.

Runs the job through workqueue.llm_batch against a real (in-memory) main
database and a fake OpenAI batch client, so the storage path -- the shared
save_generated_fact writer -- is exercised the way batch completion runs it.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from clients.batch_queue import BatchQueueManager, create_batch_database_session
from clients.types import LLMCall, Response
from storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import Base, Lemma
from storage.translation_helpers import set_translation
from words.grammar_fact_tasks import FACT_TASKS
from words.grammar_fact_tasks.grammatical_gender import prepare_grammatical_gender
from workqueue.handlers.words.grammar_facts import (
    GRAMMAR_FACT_JOB,
    grammar_fact_state,
)
from workqueue.llm_batch import (
    Done,
    StageContext,
    complete_rows,
    run_inline,
    start_batch_run,
)
from workqueue.registry import get_llm_job

_MODEL = "gpt-6-luna"
_CTX = StageContext(model=_MODEL, via="batch")


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

    def finish(self, batch_id: str, answer: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
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
                                "content": [
                                    {"type": "output_text", "text": json.dumps(answer(line))}
                                ],
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


def _lemma(session: Session, text: str, pos_type: str, translations: Dict[str, str]) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=f"definition of {text}",
        pos_type=pos_type,
        guid=f"T00_{text.replace(' ', '_')}",
    )
    session.add(lemma)
    session.flush()
    for language_code, value in translations.items():
        set_translation(session, lemma, language_code, value)
    session.commit()
    return lemma


def _complete(
    manager: BatchQueueManager,
    batch_client: _FakeBatchClient,
    session: Session,
    batch_id: str,
    answer: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, int]:
    batch_client.finish(batch_id, answer)
    manager.retrieve_batch_results(batch_id)
    rows = manager.get_completed_requests(batch_id=batch_id)
    return complete_rows(GRAMMAR_FACT_JOB, rows, session, batch_id, manager)


def _gender(value: str, confidence: float = 0.9) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    return lambda line: {"gender": value, "explanation": "because", "confidence": confidence}


def test_job_is_registered() -> None:
    assert get_llm_job("lape") is GRAMMAR_FACT_JOB
    assert get_llm_job("voras") is None


def test_batch_writes_the_fact(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "book", "noun", {"de": "Buch"})
    report = start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "de", "grammatical_gender")],
        _MODEL,
    )
    assert report.calls == 1
    body = batch_client.batches["batch-0"][0]["body"]
    assert "Buch" in body["input"]

    result = _complete(manager, batch_client, session, "batch-0", _gender("neuter"))
    assert result["updated"] == 1
    fact = session.query(GrammarFact).one()
    assert (fact.fact_value, fact.notes, fact.verified) == ("neuter", "because", False)


def test_batch_body_is_the_live_prompt(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "book", "noun", {"de": "Buch"})
    start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "de", "grammatical_gender")],
        _MODEL,
    )
    live = prepare_grammatical_gender(session, lemma, "Buch", "de")
    assert isinstance(live, LLMCall)
    body = batch_client.batches["batch-0"][0]["body"]
    assert body["input"] == live.prompt
    assert body["instructions"] == live.context


def test_low_confidence_is_not_stored(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "book", "noun", {"de": "Buch"})
    start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "de", "grammatical_gender", min_confidence=0.8)],
        _MODEL,
    )
    result = _complete(manager, batch_client, session, "batch-0", _gender("neuter", 0.75))
    assert result["skipped"] == 1
    assert session.query(GrammarFact).count() == 0


def test_hand_edit_made_while_batch_ran_wins(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "book", "noun", {"de": "Buch"})
    start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "de", "grammatical_gender")],
        _MODEL,
    )
    add_grammar_fact(session, lemma.id, "de", "grammatical_gender", "neuter", verified=True)

    result = _complete(manager, batch_client, session, "batch-0", _gender("masculine"))
    assert result["skipped"] == 1
    assert get_grammar_fact_value(session, lemma.id, "de", "grammatical_gender") == "neuter"


def test_existing_fact_is_not_sent(session: Session, manager: BatchQueueManager) -> None:
    lemma = _lemma(session, "book", "noun", {"de": "Buch"})
    add_grammar_fact(session, lemma.id, "de", "grammatical_gender", "neuter")
    report = start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "de", "grammatical_gender")],
        _MODEL,
    )
    assert report.calls == 0
    assert report.resolved_without_llm == {"skipped": 1}


def test_wrong_pos_and_missing_translation_are_rejected_without_a_call(
    session: Session, manager: BatchQueueManager
) -> None:
    verb = _lemma(session, "to run", "verb", {"de": "laufen"})
    noun = _lemma(session, "house", "noun", {})
    report = start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [
            grammar_fact_state(verb.id, "de", "grammatical_gender"),
            grammar_fact_state(noun.id, "de", "grammatical_gender"),
        ],
        _MODEL,
    )
    assert report.calls == 0
    assert report.resolved_without_llm == {"rejected": 2}


def test_spanish_dialect_copy_needs_no_call(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "house", "noun", {"es": "casa", "es-419": "casa"})
    add_grammar_fact(session, lemma.id, "es", "grammatical_gender", "feminine")
    report = start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "es-419", "grammatical_gender")],
        _MODEL,
    )
    assert report.calls == 0
    assert report.resolved_without_llm == {"written": 1}
    assert batch_client.batches == {}
    fact = session.query(GrammarFact).filter_by(lemma_id=lemma.id, language_code="es-419").one()
    assert fact.fact_value == "feminine"
    assert "Copied from es" in (fact.notes or "")


def test_french_auxiliary_rule_needs_no_call(session: Session, manager: BatchQueueManager) -> None:
    lemma = _lemma(session, "to speak", "verb", {"fr": "parler"})
    report = start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "fr", "auxiliary_verb")],
        _MODEL,
    )
    assert report.calls == 0
    assert get_grammar_fact_value(session, lemma.id, "fr", "auxiliary_verb") == "avoir"


def test_dry_run_counts_rule_answers_without_writing(
    session: Session, manager: BatchQueueManager
) -> None:
    lemma = _lemma(session, "to speak", "verb", {"fr": "parler"})
    report = start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "fr", "auxiliary_verb")],
        _MODEL,
        dry_run=True,
    )
    assert report.resolved_without_llm == {"answered": 1}
    assert session.query(GrammarFact).count() == 0


def test_rule_disagreement_is_flagged_in_batch_notes(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient
) -> None:
    lemma = _lemma(session, "nation", "noun", {"fr": "nation"})
    start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "fr", "grammatical_gender")],
        _MODEL,
    )
    _complete(manager, batch_client, session, "batch-0", _gender("masculine"))
    fact = session.query(GrammarFact).one()
    assert fact.fact_value == "masculine"
    assert (fact.notes or "").startswith("CHECK: ending rule predicts")


class _FakeChatClient:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(self, prompt: str, model: Optional[str] = None, **kwargs: Any) -> Response:
        self.calls.append({"prompt": prompt, "model": model, **kwargs})
        return Response(response_text="", structured_data=self.data, usage=None)


def test_inline_single_word(session: Session) -> None:
    lemma = _lemma(session, "book", "noun", {"de": "Buch"})
    client = _FakeChatClient({"gender": "neuter", "explanation": "", "confidence": 0.95})
    results = run_inline(
        session,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, "de", "grammatical_gender")],
        client,  # type: ignore[arg-type]
        _MODEL,
    )
    assert results == [Done("written", "neuter")]
    assert client.calls[0]["model"] == _MODEL
    assert get_grammar_fact_value(session, lemma.id, "de", "grammatical_gender") == "neuter"


# One eligible example per fact type: (pos, language, translation).
_EXAMPLES = {
    "animacy": ("noun", "en", "dog"),
    "auxiliary_verb": ("verb", "de", "gehen"),
    "countability": ("noun", "en", "water"),
    "declension_class": ("noun", "lt", "namas"),
    "fanciful_collective": ("noun", "en", "crow"),
    "grammatical_gender": ("noun", "fr", "maison"),
    "measure_words": ("noun", "zh", "书"),
    "verb_reflexivity": ("verb", "fr", "laver"),
    "verb_transitivity": ("verb", "en", "eat"),
}


def test_every_batchable_fact_type_has_an_example() -> None:
    assert set(_EXAMPLES) == set(FACT_TASKS)


@pytest.mark.parametrize("fact_type", sorted(_EXAMPLES))
def test_every_fact_type_prepares_a_call(
    session: Session, manager: BatchQueueManager, batch_client: _FakeBatchClient, fact_type: str
) -> None:
    pos_type, language_code, translation = _EXAMPLES[fact_type]
    translations = {} if language_code == "en" else {language_code: translation}
    lemma = _lemma(
        session, translation if language_code == "en" else "thing", pos_type, translations
    )
    report = start_batch_run(
        session,
        manager,
        GRAMMAR_FACT_JOB,
        [grammar_fact_state(lemma.id, language_code, fact_type)],
        _MODEL,
    )
    assert report.calls == 1, report.resolved_without_llm
    body = batch_client.batches["batch-0"][0]["body"]
    assert body["text"]["format"]["type"] == "json_schema"
    assert lemma.lemma_text in body["input"]
