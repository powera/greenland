"""Tests for the CEFR tier importer."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from storage.models.schema import (
    Base,
    ExternalLexemeAnnotation,
    ExternalLexemeAnnotationLemma,
    Lemma,
    LemmaTier,
    TierDefinition,
)
from wordfreq.tiers.bootstrap import bootstrap_tier_definitions
from wordfreq.tiers.cefr import CefrImporter, _accepted_lemma_pos_types
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


def _add_lemma(session: Session, text: str, guid: str, pos_type: str = "noun") -> Lemma:
    lemma = Lemma(lemma_text=text, definition_text=text, pos_type=pos_type, guid=guid)
    session.add(lemma)
    session.flush()
    return lemma


def _write_cefr_fixture(tmp_path: Path, entries: list[dict]) -> Path:
    fixture = tmp_path / "cefr.json"
    fixture.write_text(json.dumps({"source": "cefr", "entries": entries}))
    return fixture


def test_pos_mapping_collapses_verb_family() -> None:
    assert _accepted_lemma_pos_types("be-verb") == {"verb"}
    assert _accepted_lemma_pos_types("modal auxiliary") == {"verb"}
    assert _accepted_lemma_pos_types("vern") == {"verb"}
    assert _accepted_lemma_pos_types("noun") == {"noun"}
    assert _accepted_lemma_pos_types("determiner") == {"determiner", "article"}
    assert _accepted_lemma_pos_types("number") == {"numeral"}
    # infinitive-to and unknowns produce no filter
    assert _accepted_lemma_pos_types("infinitive-to") is None
    assert _accepted_lemma_pos_types("foo-bar") is None
    assert _accepted_lemma_pos_types(None) is None


def test_load_entries_one_per_row(tmp_path: Path) -> None:
    fixture = _write_cefr_fixture(
        tmp_path,
        [
            {"word": "abandon", "pos": "verb", "level": "B1"},
            {"word": "a", "pos": "determiner", "level": "A1"},
        ],
    )
    entries = CefrImporter(file_path=str(fixture)).load_entries()
    assert len(entries) == 2
    assert {(e.word, e.pos_hint, e.tier_name) for e in entries} == {
        ("abandon", "verb", "B1"),
        ("a", "determiner", "A1"),
    }


def test_cefr_unique_match_creates_links(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cefr"])
        verb = _add_lemma(session, "abandon", "V01", pos_type="verb")
        session.commit()

        fixture = _write_cefr_fixture(tmp_path, [{"word": "abandon", "pos": "verb", "level": "B1"}])
        report = run_import(session, CefrImporter(file_path=str(fixture)))

        assert report.total == 1
        assert report.annotations_inserted == 1
        assert report.lemma_links_inserted == 1
        assert report.lemma_tiers_inserted == 1

        link = session.query(ExternalLexemeAnnotationLemma).one()
        assert link.lemma_id == verb.id
        tier = session.query(LemmaTier).one()
        assert tier.tier_name == "B1"
        assert tier.source == "cefr"
    finally:
        session.close()


def test_cefr_pos_filter_excludes_wrong_pos(tmp_path: Path) -> None:
    """A CEFR 'verb' entry should not link a noun lemma with the same text."""
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cefr"])
        _add_lemma(session, "saw", "N01", pos_type="noun")
        session.commit()
        fixture = _write_cefr_fixture(tmp_path, [{"word": "saw", "pos": "verb", "level": "A2"}])
        report = run_import(session, CefrImporter(file_path=str(fixture)))
        assert report.unattached == 1
        assert report.lemma_links_inserted == 0
    finally:
        session.close()


def test_cefr_modal_auxiliary_matches_verb_lemma(tmp_path: Path) -> None:
    """'modal auxiliary' should fold into 'verb' so a verb lemma matches."""
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cefr"])
        can = _add_lemma(session, "can", "V02", pos_type="verb")
        session.commit()
        fixture = _write_cefr_fixture(
            tmp_path, [{"word": "can", "pos": "modal auxiliary", "level": "A1"}]
        )
        report = run_import(session, CefrImporter(file_path=str(fixture)))
        assert report.lemma_links_inserted == 1
        link = session.query(ExternalLexemeAnnotationLemma).one()
        assert link.lemma_id == can.id
    finally:
        session.close()


def test_bootstrap_inserts_cefr_tiers() -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cefr"])
        rows = session.query(TierDefinition).filter(TierDefinition.source == "cefr").all()
        assert sorted((t.tier_name, t.ordinal) for t in rows) == [
            ("A1", 1),
            ("A2", 2),
            ("B1", 3),
            ("B2", 4),
            ("C1", 5),
            ("C2", 6),
        ]
    finally:
        session.close()
