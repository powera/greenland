"""Tests for red-link discovery (which concept topics to create next)."""

from typing import Iterator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from concepts import discovery
from concepts.discovery import RankedTopic, rank_wanted_topics
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.concept import cache_wikidata_title, create_concept, create_sub_concept
from storage.models.concept import Base, ConceptWikidataIndex


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture()
def config(monkeypatch: pytest.MonkeyPatch, session: Session) -> DataSourceConfig:
    """A config whose sessions are always the test's in-memory session."""
    monkeypatch.setattr(discovery, "create_backend_session", lambda _config: session)
    # The session is shared with the test, so closing it must not end it.
    monkeypatch.setattr(session, "close", lambda: None)
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=":memory:")


def _titles(topics: List[RankedTopic]) -> List[str]:
    return [topic.title for topic in topics]


def test_red_links_without_a_concept_are_wanted(session: Session, config: DataSourceConfig) -> None:
    create_concept(session, "Art Deco", body="Related to [[Bauhaus]] and [[Streamline Moderne]].")
    session.commit()

    ranked = rank_wanted_topics(config, limit=10)

    assert sorted(_titles(ranked.wanted)) == ["Bauhaus", "Streamline Moderne"]
    assert ranked.suppressed == []


def test_targets_that_already_exist_are_not_wanted(
    session: Session, config: DataSourceConfig
) -> None:
    create_concept(session, "Art Deco", body="Related to [[Bauhaus]].")
    create_concept(session, "Bauhaus", body="A German art school.")
    session.commit()

    ranked = rank_wanted_topics(config, limit=10)

    assert ranked.wanted == []


def test_sub_concept_slugs_are_not_wanted(session: Session, config: DataSourceConfig) -> None:
    create_concept(session, "Rivers", body="Such as the [[Danube]].")
    create_sub_concept(session, "Danube", category="geography_river")
    session.commit()

    ranked = rank_wanted_topics(config, limit=10)

    assert ranked.wanted == []
    assert ranked.suppressed == []


def test_rejected_qids_are_suppressed_with_a_reason(
    session: Session, config: DataSourceConfig
) -> None:
    create_concept(session, "Art Deco", body="Related to [[Bauhaus]].")
    cache_wikidata_title(session, "Q1", "Bauhaus")
    session.query(ConceptWikidataIndex).filter_by(qid="Q1").one().rejected = True
    session.commit()

    ranked = rank_wanted_topics(config, limit=10)

    assert ranked.wanted == []
    assert _titles(ranked.suppressed) == ["Bauhaus"]
    assert ranked.suppressed[0].suppressed_reason == "rejected"


def test_qid_form_targets_are_skipped(session: Session, config: DataSourceConfig) -> None:
    create_concept(session, "Art Deco", body="See [[Q12345]] and [[Bauhaus]].")
    session.commit()

    ranked = rank_wanted_topics(config, limit=10)

    assert _titles(ranked.wanted) == ["Bauhaus"]


def test_limit_caps_the_wanted_list(session: Session, config: DataSourceConfig) -> None:
    create_concept(session, "Index", body="[[One]] [[Two]] [[Three]] [[Four]]")
    session.commit()

    ranked = rank_wanted_topics(config, limit=2)

    assert len(ranked.wanted) == 2


def test_more_cited_topics_rank_higher(session: Session, config: DataSourceConfig) -> None:
    create_concept(session, "First", body="[[Popular]] and [[Obscure]].")
    create_concept(session, "Second", body="[[Popular]] again.")
    create_concept(session, "Third", body="[[Popular]] once more.")
    session.commit()

    ranked = rank_wanted_topics(config, limit=10)

    assert _titles(ranked.wanted)[0] == "Popular"
    assert ranked.wanted[0].inbound > ranked.wanted[1].inbound
