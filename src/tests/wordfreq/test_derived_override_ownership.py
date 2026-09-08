"""Derived override tools must not claim manually maintained rows."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.models.schema import Base, Lemma, LemmaDifficultyOverride
from wordfreq.tools.country_override_manager import CountryOverrideManager, _is_country_override
from wordfreq.tools.family_relation_override_manager import (
    FamilyRelationOverrideManager,
    _is_family_override,
)


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session


def _override(notes: str) -> LemmaDifficultyOverride:
    return LemmaDifficultyOverride(
        lemma_id=1,
        language_code="lt",
        difficulty_level=-1,
        notes=notes,
    )


def test_country_tool_recognizes_only_its_provenance() -> None:
    assert _is_country_override(_override("Country word priority: country word for Lithuania"))
    assert not _is_country_override(_override("Reviewed manually"))


def test_family_tool_recognizes_only_its_provenance() -> None:
    assert _is_family_override(_override("Family relation: no natural distinction"))
    assert not _is_family_override(_override("Reviewed manually"))


@pytest.mark.parametrize(
    ("lemma_text", "pos_subtype", "manager_type", "language_code"),
    [
        ("Lithuania", "region", CountryOverrideManager, "lt"),
        ("brother", "family_relation", FamilyRelationOverrideManager, "zh"),
    ],
)
def test_preview_preserves_manual_override(
    session: Session,
    lemma_text: str,
    pos_subtype: str,
    manager_type: type[CountryOverrideManager] | type[FamilyRelationOverrideManager],
    language_code: str,
) -> None:
    lemma = Lemma(
        guid=f"N_{lemma_text}",
        lemma_text=lemma_text,
        definition_text="test definition",
        pos_type="noun",
        pos_subtype=pos_subtype,
        difficulty_level=30,
    )
    session.add(lemma)
    session.flush()
    manual_override = LemmaDifficultyOverride(
        lemma_id=lemma.id,
        language_code=language_code,
        difficulty_level=27,
        notes="Reviewed manually",
    )
    session.add(manual_override)
    session.flush()

    summary = manager_type(session).preview_changes(language_code, include_unchanged=True)

    assert summary.changes == []
