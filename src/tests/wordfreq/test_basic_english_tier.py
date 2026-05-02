"""Tests for the Basic English tier importer."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from storage.models.schema import (
    Base,
    ExternalLexemeAnnotationLemma,
    Lemma,
    LemmaTier,
    TierDefinition,
)
from wordfreq.tiers.basic_english import BasicEnglishImporter
from wordfreq.tiers.bootstrap import bootstrap_tier_definitions
from wordfreq.tiers.runner import run_import


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_lemma(
    session: Session,
    text: str,
    guid: str,
    pos_type: str = "noun",
    disambiguation: str | None = None,
) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=text,
        pos_type=pos_type,
        guid=guid,
        disambiguation=disambiguation,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _write_be_fixture(tmp_path: Path, entries: list[dict]) -> Path:
    fixture = tmp_path / "basic_english.json"
    fixture.write_text(json.dumps({"source": "basic_english", "entries": entries}))
    return fixture


def test_bootstrap_inserts_basic_english_tiers() -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["basic_english"])
        rows = session.query(TierDefinition).filter(TierDefinition.source == "basic_english").all()
        assert sorted((t.tier_name, t.ordinal) for t in rows) == [
            ("basic", 1),
            ("extended", 2),
        ]
    finally:
        session.close()


def test_basic_unique_match_creates_links(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["basic_english"])
        animal = _add_lemma(session, "animal", "N01")
        session.commit()
        fixture = _write_be_fixture(tmp_path, [{"word": "animal", "level": "basic"}])
        report = run_import(session, BasicEnglishImporter(file_path=str(fixture)))
        assert report.lemma_links_inserted == 1
        tier = session.query(LemmaTier).one()
        assert tier.lemma_id == animal.id
        assert tier.tier_name == "basic"
    finally:
        session.close()


def test_extended_level_attaches_correctly(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["basic_english"])
        _add_lemma(session, "backbone", "N02")
        session.commit()
        fixture = _write_be_fixture(tmp_path, [{"word": "backbone", "level": "extended"}])
        report = run_import(session, BasicEnglishImporter(file_path=str(fixture)))
        assert report.lemma_tiers_inserted == 1
        assert session.query(LemmaTier).one().tier_name == "extended"
    finally:
        session.close()


def test_no_pos_means_all_pos_match(tmp_path: Path) -> None:
    """Basic English carries no POS info, so every lemma_text match is kept."""
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["basic_english"])
        as_n = _add_lemma(session, "act", "N03", pos_type="noun")
        as_v = _add_lemma(session, "act", "V03", pos_type="verb")
        session.commit()
        fixture = _write_be_fixture(tmp_path, [{"word": "act", "level": "basic"}])
        report = run_import(session, BasicEnglishImporter(file_path=str(fixture)))
        assert report.lemma_links_inserted == 2
        link_ids = {row.lemma_id for row in session.query(ExternalLexemeAnnotationLemma).all()}
        assert link_ids == {as_n.id, as_v.id}
    finally:
        session.close()


def test_disambiguation_narrows_to_one(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["basic_english"])
        material = _add_lemma(session, "cork", "N04", disambiguation="cork (material)")
        _add_lemma(session, "cork", "N05", disambiguation="bottle stopper")
        session.commit()
        fixture = _write_be_fixture(
            tmp_path, [{"word": "cork", "disambiguation": "cork (material)", "level": "basic"}]
        )
        report = run_import(session, BasicEnglishImporter(file_path=str(fixture)))
        assert report.lemma_links_inserted == 1
        link = session.query(ExternalLexemeAnnotationLemma).one()
        assert link.lemma_id == material.id
    finally:
        session.close()
