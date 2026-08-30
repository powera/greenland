"""Tests for the tier system: bootstrap, runner, YLE importer, and reconcile."""

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
    WordToken,
)
from wordfreq.tiers.bootstrap import (
    BOOTSTRAP_TIER_DEFINITIONS,
    WORDFREQ_TIER_SPECS,
    bootstrap_tier_definitions,
    tier_specs_for_source,
)
from wordfreq.tiers.cambridge_yle import CambridgeYleImporter, _split_surface_forms
from wordfreq.tiers.runner import reconcile_external_annotations, run_import


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


# ---------- bootstrap ----------


def test_bootstrap_inserts_yle_and_cefr() -> None:
    session = _make_session()
    try:
        inserted = bootstrap_tier_definitions(session)
        expected = sum(len(specs) for specs in BOOTSTRAP_TIER_DEFINITIONS.values())
        assert inserted == expected
        yle = session.query(TierDefinition).filter(TierDefinition.source == "cambridge_yle").all()
        assert sorted((t.tier_name, t.ordinal) for t in yle) == [
            ("flyers", 3),
            ("movers", 2),
            ("starters", 1),
        ]
    finally:
        session.close()


def test_bootstrap_accepts_any_wordfreq_corpus_source() -> None:
    """A ``wordfreq_<corpus>`` source gets rank buckets without being listed."""
    session = _make_session()
    try:
        source = "wordfreq_wiki_physical_science"
        assert source not in BOOTSTRAP_TIER_DEFINITIONS
        inserted = bootstrap_tier_definitions(session, sources=[source])
        assert inserted == len(WORDFREQ_TIER_SPECS)
        rows = session.query(TierDefinition).filter(TierDefinition.source == source).all()
        assert {r.tier_name for r in rows} == {s.tier_name for s in WORDFREQ_TIER_SPECS}
    finally:
        session.close()


def test_tier_specs_for_source_rejects_unknown_sources() -> None:
    assert tier_specs_for_source("wordfreq_") is None
    assert tier_specs_for_source("not_a_source") is None
    assert tier_specs_for_source("cefr") == BOOTSTRAP_TIER_DEFINITIONS["cefr"]


def test_bootstrap_is_idempotent() -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        assert bootstrap_tier_definitions(session, sources=["cambridge_yle"]) == 0
    finally:
        session.close()


def test_bootstrap_constants_have_unique_ordinals_per_source() -> None:
    for source, specs in BOOTSTRAP_TIER_DEFINITIONS.items():
        ordinals = [s.ordinal for s in specs]
        assert len(ordinals) == len(set(ordinals)), f"duplicate ordinals in {source}"


# ---------- YLE importer ----------


def test_split_surface_forms() -> None:
    assert _split_surface_forms("animal") == ["animal"]
    assert _split_surface_forms("Ann/Anna") == ["Ann", "Anna"]
    assert _split_surface_forms(" Ann / Anna ") == ["Ann", "Anna"]
    assert _split_surface_forms("a/b/c") == ["a", "b", "c"]


def _write_yle_fixture(tmp_path: Path, entries: list[dict]) -> Path:
    fixture = tmp_path / "yle.json"
    fixture.write_text(json.dumps({"source": "test", "entries": entries}))
    return fixture


def test_yle_load_explodes_pos_and_slash(tmp_path: Path) -> None:
    fixture = _write_yle_fixture(
        tmp_path,
        [
            {"word": "Ann/Anna", "pos": ["n"], "level": "starters", "themes": ["Names"]},
            {"word": "run", "pos": ["n", "v"], "level": "movers", "themes": []},
        ],
    )
    entries = CambridgeYleImporter(file_path=str(fixture)).load_entries()
    # Ann + Anna + run(n) + run(v)
    assert len(entries) == 4
    surface_pos = {(e.word, e.pos_hint) for e in entries}
    assert surface_pos == {("Ann", "n"), ("Anna", "n"), ("run", "n"), ("run", "v")}


# ---------- runner: end-to-end ----------


def test_yle_unique_match_creates_annotation_link_and_tier(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        elephant = _add_lemma(session, "elephant", "N01_001", pos_type="noun")
        session.commit()

        fixture = _write_yle_fixture(
            tmp_path,
            [{"word": "elephant", "pos": ["n"], "level": "starters", "themes": ["Animals"]}],
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))

        assert report.total == 1
        assert report.annotations_inserted == 1
        assert report.lemma_links_inserted == 1
        assert report.lemma_tiers_inserted == 1
        assert report.unattached == 0

        annot = session.query(ExternalLexemeAnnotation).one()
        assert annot.tier_name == "starters"
        assert annot.word_token.token == "elephant"
        link = session.query(ExternalLexemeAnnotationLemma).one()
        assert link.lemma_id == elephant.id
        tier = session.query(LemmaTier).one()
        assert tier.lemma_id == elephant.id
        assert tier.tier_name == "starters"
    finally:
        session.close()


def test_yle_homograph_attaches_to_all_candidates(tmp_path: Path) -> None:
    """fish -> fish-animal AND fish-meat both get a link + LemmaTier row."""
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        f_animal = _add_lemma(session, "fish", "N02_001", pos_type="noun")
        f_meat = _add_lemma(session, "fish", "N02_002", pos_type="noun")
        session.commit()

        fixture = _write_yle_fixture(
            tmp_path, [{"word": "fish", "pos": ["n"], "level": "starters", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))

        assert report.annotations_inserted == 1
        assert report.lemma_links_inserted == 2
        assert report.lemma_tiers_inserted == 2

        link_lemma_ids = {
            row.lemma_id for row in session.query(ExternalLexemeAnnotationLemma).all()
        }
        assert link_lemma_ids == {f_animal.id, f_meat.id}
        tier_lemma_ids = {row.lemma_id for row in session.query(LemmaTier).all()}
        assert tier_lemma_ids == {f_animal.id, f_meat.id}
    finally:
        session.close()


def test_yle_unattached_annotation_still_recorded(tmp_path: Path) -> None:
    """A YLE entry with no matching lemma still creates an annotation row."""
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "Alice", "pos": ["n"], "level": "starters", "themes": ["Names"]}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))

        assert report.unattached == 1
        assert report.annotations_inserted == 1
        assert report.lemma_links_inserted == 0
        assert report.lemma_tiers_inserted == 0

        annot = session.query(ExternalLexemeAnnotation).one()
        assert annot.word_token.token == "Alice"
        assert session.query(ExternalLexemeAnnotationLemma).count() == 0
        assert session.query(LemmaTier).count() == 0
    finally:
        session.close()


def test_yle_pos_filter_still_excludes_wrong_pos(tmp_path: Path) -> None:
    """A YLE 'v' entry should not link a noun lemma even if lemma_text matches."""
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "saw", "N03_001", pos_type="noun")
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "saw", "pos": ["v"], "level": "flyers", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))
        assert report.unattached == 1
        assert report.annotations_inserted == 1
        assert report.lemma_links_inserted == 0
    finally:
        session.close()


def test_sense_hint_narrows_to_one(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        a = _add_lemma(session, "bank", "N04_001", pos_type="noun")
        a.disambiguation = "river"
        b = _add_lemma(session, "bank", "N04_002", pos_type="noun")
        b.disambiguation = "finance"
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path,
            [{"word": "bank", "pos": ["n"], "level": "movers", "sense": "river", "themes": []}],
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))
        assert report.lemma_links_inserted == 1
        link = session.query(ExternalLexemeAnnotationLemma).one()
        assert link.lemma_id == a.id
    finally:
        session.close()


def test_unknown_tier_name_skipped_no_annotation(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "x", "N05_001", pos_type="noun")
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "x", "pos": ["n"], "level": "MASTER_RANK", "themes": []}]
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(fixture)))
        assert "MASTER_RANK" in report.unknown_tier_names
        assert report.annotations_inserted == 0
        assert session.query(ExternalLexemeAnnotation).count() == 0
    finally:
        session.close()


def test_dry_run_does_not_persist(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "cat", "N06_001", pos_type="noun")
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "cat", "pos": ["n"], "level": "starters", "themes": []}]
        )
        run_import(session, CambridgeYleImporter(file_path=str(fixture)), dry_run=True)
        assert session.query(ExternalLexemeAnnotation).count() == 0
        assert session.query(LemmaTier).count() == 0
        assert session.query(ExternalLexemeAnnotationLemma).count() == 0
    finally:
        session.close()


def test_rerun_updates_annotation_in_place(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        _add_lemma(session, "cat", "N07_001", pos_type="noun")
        session.commit()

        f1 = tmp_path / "first.json"
        f1.write_text(
            json.dumps(
                {
                    "source": "t",
                    "entries": [{"word": "cat", "pos": ["n"], "level": "movers", "themes": []}],
                }
            )
        )
        run_import(session, CambridgeYleImporter(file_path=str(f1)))

        f2 = tmp_path / "second.json"
        f2.write_text(
            json.dumps(
                {
                    "source": "t",
                    "entries": [{"word": "cat", "pos": ["n"], "level": "starters", "themes": []}],
                }
            )
        )
        report = run_import(session, CambridgeYleImporter(file_path=str(f2)))
        assert report.annotations_updated == 1
        assert report.annotations_inserted == 0
        assert session.query(ExternalLexemeAnnotation).count() == 1
        assert session.query(ExternalLexemeAnnotation).one().tier_name == "starters"
        assert session.query(LemmaTier).one().tier_name == "starters"
    finally:
        session.close()


# ---------- reconcile ----------


def test_reconcile_attaches_lemmas_added_after_import(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "alphabet", "pos": ["n"], "level": "starters", "themes": []}]
        )
        importer = CambridgeYleImporter(file_path=str(fixture))
        run_import(session, importer)
        # No lemma yet — annotation exists, no links.
        assert session.query(ExternalLexemeAnnotation).count() == 1
        assert session.query(ExternalLexemeAnnotationLemma).count() == 0
        assert session.query(LemmaTier).count() == 0

        # Add the lemma later; reconcile should pick it up.
        _add_lemma(session, "alphabet", "N08_001", pos_type="noun")
        session.commit()
        report = reconcile_external_annotations(session, importer)
        assert report.lemma_links_inserted == 1
        assert report.lemma_tiers_inserted == 1
    finally:
        session.close()


# ---------- cascade behavior ----------


def test_cascade_delete_lemma_drops_links_only(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        cat = _add_lemma(session, "cat", "N09_001", pos_type="noun")
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "cat", "pos": ["n"], "level": "starters", "themes": []}]
        )
        run_import(session, CambridgeYleImporter(file_path=str(fixture)))
        assert session.query(ExternalLexemeAnnotationLemma).count() == 1

        session.delete(cat)
        session.commit()
        # Lemma cascade dropped the link and the LemmaTier row, but the
        # annotation itself survives.
        assert session.query(ExternalLexemeAnnotationLemma).count() == 0
        assert session.query(LemmaTier).count() == 0
        assert session.query(ExternalLexemeAnnotation).count() == 1
    finally:
        session.close()


def test_cascade_delete_annotation_drops_links_only(tmp_path: Path) -> None:
    session = _make_session()
    try:
        bootstrap_tier_definitions(session, sources=["cambridge_yle"])
        cat = _add_lemma(session, "cat", "N10_001", pos_type="noun")
        session.commit()
        fixture = _write_yle_fixture(
            tmp_path, [{"word": "cat", "pos": ["n"], "level": "starters", "themes": []}]
        )
        run_import(session, CambridgeYleImporter(file_path=str(fixture)))

        annot = session.query(ExternalLexemeAnnotation).one()
        session.delete(annot)
        session.commit()
        assert session.query(ExternalLexemeAnnotationLemma).count() == 0
        # The lemma and its LemmaTier row survive (LemmaTier is independent).
        assert session.query(Lemma).filter(Lemma.id == cat.id).count() == 1
        assert session.query(LemmaTier).count() == 1
    finally:
        session.close()
