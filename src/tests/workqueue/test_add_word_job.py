"""Tests for the staged add_word job (workqueue.handlers.words.add_word).

The job runs inline here against a fake chat client, which is enough to cover
what the batch path adds on top of add_word: the senses stage, the fan-out of
one subtype call per selected sense, and the joined write.  The batch plumbing
itself (fan-out rows, the join, the barrier) is covered in test_llm_batch.
"""

import re
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from clients.types import Response, Schema
from storage.models import Base, Lemma
from workqueue.handlers.words.add_word import ADD_WORD_JOB, add_word_state
from workqueue.llm_batch import Done, run_inline

pytestmark = pytest.mark.usefixtures("require_lemma_write_scope")

_MODEL = "test-model"


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    import storage.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'add_word_job.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    db_session = sessionmaker(bind=db_engine)()
    yield db_session
    db_session.close()


def _sense(definition: str, pos: str, prominence: str = "very_common") -> Dict[str, Any]:
    return {
        "definition": definition,
        "pos": pos,
        "sense_prominence": prominence,
        "lithuanian_translation": "vertimas",
        "spanish_translation": "traducción",
        "spanish_latam_translation": "traducción",
        "french_translation": "traduction",
        "chinese_translation": "翻译",
    }


class FakeChat:
    """Answers the senses call with canned senses and each subtype call by definition."""

    def __init__(self, senses: List[Dict[str, Any]], subtypes: Dict[str, Optional[str]]) -> None:
        self.senses = senses
        self.subtypes = subtypes
        self.subtype_prompts: List[str] = []
        self.senses_calls = 0

    def generate_chat(
        self,
        prompt: str,
        model: Optional[str] = None,
        json_schema: Optional[Schema] = None,
        **_: Any,
    ) -> Response:
        assert json_schema is not None
        if json_schema.name == "WordDefinitions":
            self.senses_calls += 1
            return Response(
                response_text="", structured_data={"definitions": self.senses}, usage=None
            )
        self.subtype_prompts.append(prompt)
        match = re.search(r"Definition: (.*)", prompt)
        assert match, prompt
        subtype = self.subtypes.get(match.group(1).strip())
        data = {"pos_subtype": subtype} if subtype else {}
        return Response(response_text="", structured_data=data, usage=None)


def test_job_adds_each_sense_with_its_own_subtype_call(session: Session) -> None:
    chat = FakeChat(
        [
            _sense("A bird with webbed feet", "noun"),
            _sense("To lower the head quickly", "verb"),
        ],
        {
            "A bird with webbed feet": "animal",
            "To lower the head quickly": "physical_action",
        },
    )
    results = run_inline(
        session,
        ADD_WORD_JOB,
        [add_word_state("duck", source="test", difficulty_level=1399)],
        chat,  # type: ignore[arg-type]
        _MODEL,
    )

    assert results[0].status == "written", results[0]
    assert chat.senses_calls == 1
    # One subtype call per sense, each showing only its own definition.
    assert len(chat.subtype_prompts) == 2
    assert all(prompt.count("Definition:") == 1 for prompt in chat.subtype_prompts)
    lemmas = {
        (lemma.pos_type, lemma.pos_subtype, lemma.difficulty_level)
        for lemma in session.query(Lemma).filter_by(lemma_text="duck")
    }
    assert lemmas == {("noun", "animal", 1399), ("verb", "physical_action", 1399)}


def test_job_skips_a_word_already_present_without_a_call(session: Session) -> None:
    chat = FakeChat(
        [_sense("A bird with webbed feet", "noun")], {"A bird with webbed feet": "animal"}
    )
    run_inline(session, ADD_WORD_JOB, [add_word_state("duck", source="test")], chat, _MODEL)  # type: ignore[arg-type]
    calls_after_first = chat.senses_calls

    results = run_inline(session, ADD_WORD_JOB, [add_word_state("duck", source="test")], chat, _MODEL)  # type: ignore[arg-type]
    assert results == [Done("skipped", "already_exists")]
    assert chat.senses_calls == calls_after_first


def test_job_writes_nothing_when_a_subtype_call_fails(session: Session) -> None:
    chat = FakeChat(
        [
            _sense("A bird with webbed feet", "noun"),
            _sense("To lower the head quickly", "verb"),
        ],
        {"A bird with webbed feet": "animal", "To lower the head quickly": None},
    )
    results = run_inline(session, ADD_WORD_JOB, [add_word_state("duck", source="test")], chat, _MODEL)  # type: ignore[arg-type]

    assert results[0].status == "failed"
    assert "subtype call failed" in results[0].detail
    assert session.query(Lemma).filter_by(lemma_text="duck").count() == 0
