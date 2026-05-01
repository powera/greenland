"""Tests for the tier system: bootstrap, runner, and Cambridge YLE importer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.imports import PendingImport
from storage.models.schema import Base, Lemma, LemmaTier, TierDefinition
from wordfreq.tiers.base import ResolveResult, ResolveStatus, TierEntry
from wordfreq.tiers.bootstrap import (
    BOOTSTRAP_TIER_DEFINITIONS,
    bootstrap_tier_definitions,
)
from wordfreq.tiers.cambridge_yle import CambridgeYleImporter
from wordfreq.tiers.runner import run_import


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_lemma(session: Session, text: str, guid: str, pos_type: str = "noun") -> Lemma:
    lemma = Lemma(lemma_text=text, definition_text=text, pos_type=pos_type, guid=guid)
    session.add(lemma)
    session.flush()
    return lemma


# ---------- bootstrap ----------


def test_bootstrap_inserts_yle_and_cefr() -> None:
    session = _make_session()
    try:
        inserted = bootstrap_tier_definitions(session)
        # 3 YLE + 6 CEFR
        assert inserted == 3 + 6
        yle = session.query(TierDefinition).filter(TierDefinition.source == "cambridge_yle").all()
        assert sorted((t.tier_name, t.ordinal) for t in yle) == [
            ("flyers", 3),
            ("movers", 2),
            ("starters", 1),
        ]
        cefr_names = sorted(
            t.tier_name
            for t in session.query(TierDefinition).filter(TierDefinition.source == "cefr").all()
        )
        assert cefr_names == ["A1", "A2", "B1", "B2", "C1", "C2"]
    finally:
        session.close()


def test_bootstrap_is_idempotent() -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        second = bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        assert second == 0
    finally:
        session.close()


def test_bootstrap_constants_have_unique_ordinals_per_source() -> None:
    for source, specs in BOOTSTRAP_TIER_DEFINITIONS.items():
        ordinals = [s.ordinal for s in specs]
        assert len(ordinals) == len(set(ordinals)), f"duplicate ordinals in {source}"


# ---------- YLE importer ----------


def _write_yle_fixture(tmp_path: Path, entries: list[dict]) -> Path:
    payload = {"source": "test", "entries": entries}
    fixture = tmp_path / "yle.json"
    fixture.write_text(json.dumps(payload))
    return fixture


def test_yle_load_entries_explodes_pos_list(tmp_path: Path) -> None:
    fixture = _write_yle_fixture(
        tmp_path,
        [
            {"word": "run", "pos": ["n", "v"], "level": "movers", "themes": [], "sense": None},
        ],
    )
    importer = CambridgeYleImporter(file_path=str(fixture))
    entries = importer.load_entries()
    assert len(entries) == 2
    assert {e.pos_hint for e in entries} == {"n", "v"}
    assert all(e.tier_name == "movers" for e in entries)


def test_yle_resolve_unique_match(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "elephant", "N01_001", pos_type="noun")
        session.commit()

        fixture = _write_yle_fixture(
            tmp_path,
            [{"word": "elephant", "pos": ["n"], "level": "starters", "themes": ["Animals"]}],
        )
        importer = CambridgeYleImporter(file_path=str(fixture))
        report = run_import(session, importer)

        assert report.total == 1
        assert report.matched == 1
        assert report.upserts_inserted == 1
        tier = session.query(LemmaTier).one()
        assert tier.tier_name == "starters"
        assert json.loads(tier.themes or "[]") == ["Animals"]
    finally:
        session.close()


def test_yle_resolve_ambiguous_queues_for_review(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "bank", "N02_001", pos_type="noun")
        _add_lemma(session, "bank", "N02_002", pos_type="noun")
        session.commit()

        fixture = _write_yle_fixture(
            tmp_path, [{"word": "bank", "pos": ["n"], "level": "movers", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))

        assert report.matched == 0
        assert report.ambiguous == 1
        assert report.queued_for_review == 1
        pending = session.query(PendingImport).all()
        assert len(pending) == 1
        assert pending[0].english_word == "bank"
        assert pending[0].source == "tier:cambridge_yle"
    finally:
        session.close()


def test_yle_resolve_pos_filter_filters_out_wrong_pos(tmp_path: Path) -> None:
    """A YLE 'v' entry should not match a noun lemma even if lemma_text matches."""
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "saw", "N03_001", pos_type="noun")
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "saw", "pos": ["v"], "level": "flyers", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))
        assert report.matched == 0
        assert report.unmatched == 1
        assert report.queued_for_review == 1
    finally:
        session.close()


def test_yle_resolve_unmatched_when_no_lemma(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "ghostword", "pos": ["n"], "level": "starters", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))
        assert report.unmatched == 1
        assert report.queued_for_review == 1
    finally:
        session.close()


def test_yle_unknown_tier_name_is_unmatched(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "x", "N04_001", pos_type="noun")
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "x", "pos": ["n"], "level": "MASTER_RANK", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))
        assert report.unmatched == 1
        assert "MASTER_RANK" in report.unknown_tier_names
    finally:
        session.close()


def test_run_import_dry_run_does_not_persist(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "cat", "N05_001", pos_type="noun")
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "cat", "pos": ["n"], "level": "starters", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)), dry_run=True)
        assert report.matched == 1
        # Nothing committed
        assert session.query(LemmaTier).count() == 0
    finally:
        session.close()


def test_run_import_updates_existing_lemma_tier(tmp_path: Path) -> None:
    """Re-importing should update tier_name in place rather than insert a duplicate."""
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        cat = _add_lemma(session, "cat", "N06_001", pos_type="noun")
        session.add(LemmaTier(lemma_id=cat.id, source="cambridge_yle", tier_name="movers"))
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "cat", "pos": ["n"], "level": "starters", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))
        assert report.matched == 1
        assert report.upserts_updated == 1
        assert report.upserts_inserted == 0
        rows = session.query(LemmaTier).filter(LemmaTier.lemma_id == cat.id).all()
        assert len(rows) == 1
        assert rows[0].tier_name == "starters"
    finally:
        session.close()


# ---------- ResolveResult constructors ----------


def test_resolve_result_constructors() -> None:
    m = ResolveResult.matched(7)
    assert m.status is ResolveStatus.MATCHED and m.lemma_ids == (7,)
    a = ResolveResult.ambiguous([1, 2], reason="dup")
    assert a.status is ResolveStatus.AMBIGUOUS and a.lemma_ids == (1, 2)
    u = ResolveResult.unmatched("missing")
    assert u.status is ResolveStatus.UNMATCHED and u.reason == "missing"
