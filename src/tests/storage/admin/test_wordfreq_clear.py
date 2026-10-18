"""Tests for the wordfreq clears: the soft rank reset keeps token ids, the hard clear
leaves nothing pointing at a deleted token."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest
from sqlalchemy import create_engine

# Import the full model registry so every table is created.
import storage.models  # noqa: F401
from storage.admin.service import DatabaseAdminService
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.crud.name_entity import create_name
from storage.models.name_entity import NameDerivativeForm
from storage.models.schema import (
    Base,
    DerivativeForm,
    ExternalLexemeAnnotation,
    ExternalLexemeAnnotationLemma,
    Lemma,
    WordToken,
)
from storage.token_forms import TOKEN_FORM_SOURCES


@pytest.fixture
def config(tmp_path: Path) -> DataSourceConfig:
    database_path = tmp_path / "wordfreq.sqlite"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return DataSourceConfig(sqlite_path=str(database_path))


def _populate(config: DataSourceConfig) -> Dict[str, int]:
    """One lemma form, one name form, a corpus annotation and a tier annotation."""
    session = create_session(config)
    try:
        cat = WordToken(token="cat", language_code="en", frequency_rank=10)
        john = WordToken(token="John", language_code="en", frequency_rank=20)
        session.add_all([cat, john])
        session.flush()

        lemma = Lemma(lemma_text="cat", definition_text="cat", pos_type="noun", guid="N01_001")
        session.add(lemma)
        session.flush()
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="cat",
                word_token_id=cat.id,
                language_code="en",
                grammatical_form="noun/en_singular",
                is_base_form=True,
            )
        )
        create_name(session, name_text="John", kind="given_name")

        corpus_row = ExternalLexemeAnnotation(
            word_token_id=cat.id, source="wordfreq_test", tier_name="common", ordinal_rank=1
        )
        tier_row = ExternalLexemeAnnotation(word_token_id=cat.id, source="cefr", tier_name="A1")
        session.add_all([corpus_row, tier_row])
        session.flush()
        session.add_all(
            [
                ExternalLexemeAnnotationLemma(annotation_id=corpus_row.id, lemma_id=lemma.id),
                ExternalLexemeAnnotationLemma(annotation_id=tier_row.id, lemma_id=lemma.id),
            ]
        )
        session.commit()
        return {"cat": cat.id, "John": john.id}
    finally:
        session.close()


def test_reset_wordfreq_ranks_keeps_token_ids_and_links(config: DataSourceConfig) -> None:
    token_ids = _populate(config)

    result = DatabaseAdminService(config).reset_wordfreq_ranks()
    assert result["annotations"] == 1

    session = create_session(config)
    try:
        assert {t.token: t.id for t in session.query(WordToken).all()} == token_ids
        assert all(t.frequency_rank is None for t in session.query(WordToken).all())
        assert session.query(DerivativeForm).one().word_token_id == token_ids["cat"]
        name_links = {
            form.derivative_form_text: form.word_token_id
            for form in session.query(NameDerivativeForm).all()
        }
        assert name_links["John"] == token_ids["John"]
        assert [row.source for row in session.query(ExternalLexemeAnnotation).all()] == ["cefr"]
        assert session.query(ExternalLexemeAnnotationLemma).count() == 1
    finally:
        session.close()


def test_hard_clear_leaves_no_reference_to_a_deleted_token(config: DataSourceConfig) -> None:
    _populate(config)

    result = DatabaseAdminService(config).clear_wordfreq_data()
    assert result["tiers_need_reimport"] is True

    session = create_session(config)
    try:
        assert session.query(WordToken).count() == 0
        for source in TOKEN_FORM_SOURCES:
            linked = session.query(source.model).filter(source.model.word_token_id.isnot(None))
            assert linked.count() == 0, source.table_name
        assert session.query(ExternalLexemeAnnotation).count() == 0
        assert session.query(ExternalLexemeAnnotationLemma).count() == 0
        # The forms themselves are dictionary data and survive.
        assert session.query(DerivativeForm).count() == 1
        assert session.query(NameDerivativeForm).count() == 2
    finally:
        session.close()


def test_dry_runs_change_nothing(config: DataSourceConfig) -> None:
    _populate(config)
    service = DatabaseAdminService(config)

    service.reset_wordfreq_ranks(dry_run=True)
    service.clear_wordfreq_data(dry_run=True)

    session = create_session(config)
    try:
        assert session.query(WordToken).filter(WordToken.frequency_rank.isnot(None)).count() == 2
        assert session.query(ExternalLexemeAnnotation).count() == 2
    finally:
        session.close()
