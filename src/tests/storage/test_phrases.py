"""Tests for the phrases system.

Covers ``crud/phrase`` (GUID allocation, add, translation upsert), the
prefix-based ``guid_router`` (lemma / phrase / sentence classification and
resolution), and the phrase data migration that lifts ``pos_type="phrase"``
lemmas into the dedicated ``phrases`` table.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.phrase import (
    add_phrase,
    get_phrase_by_guid,
    next_phrase_guid,
    set_phrase_translation,
)
from storage.guid_router import guid_kind, resolve_guid
from storage.models.schema import (
    Base,
    Lemma,
    LemmaTranslation,
    Phrase,
    PhraseTranslation,
    Sentence,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PHRASE_MIGRATION_PATH = PROJECT_ROOT / "migrations" / "20260718_move_phrases_to_phrase_table.py"


def _load_phrase_migration() -> ModuleType:
    module_name = "migration_20260718_move_phrases_to_phrase_table"
    spec = importlib.util.spec_from_file_location(module_name, PHRASE_MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


# ---------------------------------------------------------------------------
# GUID allocation
# ---------------------------------------------------------------------------


def test_next_phrase_guid_starts_at_one(session: Session) -> None:
    assert next_phrase_guid(session, "greetings") == "F01_001"
    assert next_phrase_guid(session, "traveler") == "F02_001"


def test_next_phrase_guid_increments_per_subtype(session: Session) -> None:
    add_phrase(session, "greetings", "Hello")
    add_phrase(session, "greetings", "Goodbye")
    assert next_phrase_guid(session, "greetings") == "F01_003"
    # A different subtype has an independent counter.
    assert next_phrase_guid(session, "traveler") == "F02_001"


def test_next_phrase_guid_rejects_unknown_subtype(session: Session) -> None:
    with pytest.raises(ValueError):
        next_phrase_guid(session, "not_a_subtype")


# ---------------------------------------------------------------------------
# add_phrase / translations
# ---------------------------------------------------------------------------


def test_add_phrase_autogenerates_guid_and_is_fetchable(session: Session) -> None:
    phrase = add_phrase(
        session,
        phrase_subtype="greetings",
        label="See you later",
        definition="Lithuanian: Iki pasimatymo",
        difficulty_level=1,
    )
    assert phrase.guid == "F01_001"
    fetched = get_phrase_by_guid(session, "F01_001")
    assert fetched is not None
    assert fetched.label == "See you later"


def test_set_phrase_translation_inserts_then_updates(session: Session) -> None:
    phrase = add_phrase(session, "greetings", "Hello")
    set_phrase_translation(session, phrase, "lt", "labas")
    set_phrase_translation(session, phrase, "lt", "sveiki", translation_status="conventional")

    rows = (
        session.query(PhraseTranslation)
        .filter(PhraseTranslation.phrase_id == phrase.id, PhraseTranslation.language_code == "lt")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].translation == "sveiki"
    assert rows[0].translation_status == "conventional"


# ---------------------------------------------------------------------------
# guid_router
# ---------------------------------------------------------------------------


def test_guid_kind_classifies_by_prefix() -> None:
    assert guid_kind("S_00001") == "sentence"
    assert guid_kind("F01_003") == "phrase"
    assert guid_kind("F02_010") == "phrase"
    assert guid_kind("N02_001") == "lemma"
    assert guid_kind("V01_003") == "lemma"


def test_resolve_guid_dispatches_to_right_table(session: Session) -> None:
    lemma = Lemma(lemma_text="dog", definition_text="animal", pos_type="noun", guid="N02_001")
    sentence = Sentence(guid="S_00001")
    session.add_all([lemma, sentence])
    session.flush()
    phrase = add_phrase(session, "greetings", "Hello")

    assert resolve_guid(session, "N02_001") == ("lemma", lemma)
    assert resolve_guid(session, "S_00001") == ("sentence", sentence)
    assert resolve_guid(session, phrase.guid) == ("phrase", phrase)

    # Missing rows still report their kind, with a None object.
    kind, obj = resolve_guid(session, "F02_999")
    assert kind == "phrase" and obj is None


# ---------------------------------------------------------------------------
# Data migration
# ---------------------------------------------------------------------------


def test_migration_moves_phrase_lemmas(tmp_path: Path) -> None:
    migration = _load_phrase_migration()

    db_path = str(tmp_path / "old_style.sqlite")
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    with Session(engine) as setup:
        lemma = Lemma(
            lemma_text="See you later",
            definition_text="Lithuanian: Iki",
            pos_type="phrase",
            pos_subtype="greetings",
            guid="F01_003",
            difficulty_level=1,
            verified=True,
        )
        setup.add(lemma)
        setup.flush()
        setup.add(
            LemmaTranslation(lemma_id=lemma.id, language_code="en", translation="See you later")
        )
        setup.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="lt",
                translation="iki pasimatymo",
                translation_status="conventional",
            )
        )
        # A normal lemma that must survive untouched.
        setup.add(
            Lemma(lemma_text="dog", definition_text="animal", pos_type="noun", guid="N02_001")
        )
        setup.commit()

    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)
    assert migration.migrate(config, dry_run=False) == 1
    # Idempotent re-run.
    assert migration.migrate(config, dry_run=False) == 0

    with Session(engine) as check:
        assert check.query(Lemma).filter(Lemma.pos_type == "phrase").count() == 0
        assert check.query(Lemma).filter(Lemma.pos_type == "noun").count() == 1
        phrase = check.query(Phrase).filter(Phrase.guid == "F01_003").one()
        assert phrase.label == "See you later"
        assert phrase.phrase_subtype == "greetings"
        assert phrase.verified is True
        translations = {
            t.language_code: t.translation
            for t in check.query(PhraseTranslation).filter(PhraseTranslation.phrase_id == phrase.id)
        }
        assert translations == {"en": "See you later", "lt": "iki pasimatymo"}
        # No duplication on the second run.
        assert check.query(Phrase).count() == 1
