"""Tests for the Wikidata Q-id concept pipeline."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from concepts.pipeline import create_concept_from_qid
from concepts.persist import create_concept_from_seed
from concepts.validate import validate_qid, validate_seed
from storage.crud.concept import create_concept, get_wikidata_index
from storage.models.concept import Base
from storage.wikidata import WikidataConceptSeed


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _seed(qid: str = "Q42", title: str = "Douglas Adams") -> WikidataConceptSeed:
    return WikidataConceptSeed(
        qid=qid,
        title=title,
        summary="English author and humorist",
        sources=[{"title": "Wikipedia", "url": "https://example.test/adams"}],
    )


def test_pipeline_runs_query_generation_validation_and_persistence(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    queried: list[tuple[str, bool]] = []
    generated: list[tuple[str, str]] = []

    def query(qid: str, *, include_regional_wikis: bool = False) -> WikidataConceptSeed:
        queried.append((qid, include_regional_wikis))
        return _seed(qid)

    def generate(title: str, summary: str, sources: list[dict[str, object]]) -> str:
        generated.append((title, summary))
        assert sources[0]["title"] == "Wikipedia"
        return "A generated body about [[The Hitchhiker's Guide to the Galaxy]]."

    monkeypatch.setattr("concepts.pipeline.query_wikidata_seed", query)

    result = create_concept_from_qid(
        session,
        "q42",
        body_generator=generate,
        source_model="test-model",
        include_regional_wikis=True,
    )

    assert result.status == "created"
    assert result.concept is not None
    assert result.concept.body is not None
    assert result.concept.body.startswith("A generated body")
    assert result.concept.source_model == "test-model"
    assert queried == [("Q42", True)]
    assert generated == [("Douglas Adams", "English author and humorist")]
    index_row = get_wikidata_index(session, "Q42")
    assert index_row is not None and index_row.concept == result.concept


def test_pipeline_persists_seed_when_generation_fails(
    monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    monkeypatch.setattr(
        "concepts.pipeline.query_wikidata_seed",
        lambda qid, *, include_regional_wikis=False: _seed(qid),
    )

    def fail_generation(title: str, summary: str, sources: list[dict[str, object]]) -> str:
        raise RuntimeError("offline")

    result = create_concept_from_qid(
        session,
        "Q42",
        body_generator=fail_generation,
        source_model="unused-model",
    )

    assert result.status == "created"
    assert result.concept is not None
    assert result.concept.body == ""
    assert result.concept.source_model is None
    assert result.detail == "saved without body: offline"


def test_validation_rejects_existing_qid_before_seed_query(session: Session) -> None:
    first_result = create_concept_from_seed(session, _seed(), body="Stored body")
    assert first_result.status == "created"

    validation = validate_qid(session, "q42")

    assert validation.status == "exists"
    assert validation.concept == first_result.concept


def test_validation_rejects_duplicate_seed_title(session: Session) -> None:
    assert create_concept(session, title="Douglas Adams") is not None

    validation = validate_seed(session, _seed("Q99"))

    assert validation.status == "exists"
    assert "already exists" in validation.detail
