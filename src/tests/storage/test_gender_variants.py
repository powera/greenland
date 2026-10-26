"""Gender counterparts preserve identity and grammar across storage boundaries."""

import json
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.crud.variant_form import add_variant_form
from storage.migrate import export_sqlite_to_jsonl, import_jsonl_to_sqlite
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, Lemma, LemmaTranslation
from storage.models.variant_form import (
    ACCEPTED_ANSWER_VARIANT_KINDS,
    VARIANT_KIND_GENDER,
    VariantForm,
)
from storage.release.variant import records_to_paradigms, variants_by_language


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


def test_gender_upsert_keeps_default_and_gender_variants_distinct(session: Session) -> None:
    lemma = Lemma(
        guid="N35_076",
        lemma_text="cousin",
        definition_text="A cousin.",
        pos_type="noun",
        pos_subtype="family_relation",
    )
    session.add(lemma)
    session.flush()
    for gender, text in (("male", "primo"), ("female", "prima")):
        add_variant_form(
            session,
            lemma,
            text,
            "es",
            gender,
            "noun/es_singular",
            variant_kind=VARIANT_KIND_GENDER,
            is_base_form=True,
            grammatical_gender="masculine" if gender == "male" else "feminine",
            link_word_token=False,
            source="test/gender-variants",
        )
    updated = add_variant_form(
        session,
        lemma,
        "prima",
        "es",
        "female",
        "noun/es_singular",
        variant_kind=VARIANT_KIND_GENDER,
        is_base_form=True,
        grammatical_gender="common",
        link_word_token=False,
        source="test/gender-variants",
    )
    assert updated.grammatical_gender == "common"
    assert session.query(VariantForm).count() == 2
    logs = session.query(OperationLog).filter_by(operation_type="variant_update").all()
    assert len(logs) == 1
    assert "grammatical_gender" in logs[0].fact
    assert VARIANT_KIND_GENDER not in ACCEPTED_ANSWER_VARIANT_KINDS
    with pytest.raises(ValueError, match="male/female"):
        add_variant_form(
            session,
            lemma,
            "primo",
            "es",
            "unspecified",
            "noun/es_singular",
            variant_kind=VARIANT_KIND_GENDER,
            link_word_token=False,
        )


def test_release_groups_grammatical_gender_without_inferring_it() -> None:
    rows = [
        VariantForm(
            language_code="es",
            variant_kind="gender",
            variant_key="female",
            grammatical_form="noun/es_singular",
            variant_form_text="prima",
            is_base_form=True,
            grammatical_gender="masculine",
        )
    ]
    record = variants_by_language(rows)["es"][0]
    assert record["grammatical_gender"] == "masculine"
    assert "grammatical_gender" not in record["forms"][0]
    restored = records_to_paradigms([record])
    assert restored[("gender", "female")][0]["grammatical_gender"] == "masculine"


@pytest.mark.parametrize("backend", ["sqlite", "jsonl"])
def test_gender_variant_release_roundtrip(tmp_path: Path, backend: str) -> None:
    source = tmp_path / "source.sqlite"
    engine = create_engine(f"sqlite:///{source}")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        lemma = Lemma(
            guid="N35_076",
            lemma_text="cousin",
            definition_text="A cousin.",
            pos_type="noun",
            pos_subtype="family_relation",
            difficulty_level=18,
        )
        database_session.add(lemma)
        database_session.flush()
        database_session.add(
            LemmaTranslation(lemma_id=lemma.id, language_code="es", translation="primo")
        )
        for slot, text in (("singular", "prima"), ("plural", "primas")):
            add_variant_form(
                database_session,
                lemma,
                text,
                "es",
                "female",
                f"noun/es_{slot}",
                variant_kind="gender",
                is_base_form=slot == "singular",
                grammatical_gender="feminine",
                link_word_token=False,
            )
        database_session.commit()
    engine.dispose()
    release = tmp_path / "release"
    export_sqlite_to_jsonl(str(source), str(release))
    line = json.loads((release / "lemmas/nouns/family_relation/es.jsonl").read_text().strip())
    assert line["variants"][0]["grammatical_gender"] == "feminine"
    if backend == "sqlite":
        destination = tmp_path / "imported.sqlite"
        import_jsonl_to_sqlite(str(release), str(destination), force=True)
        config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=str(destination))
    else:
        config = DataSourceConfig(backend_type=BackendType.JSONL, jsonl_data_dir=str(release))
    with create_session(config) as imported:
        forms = imported.query(VariantForm).filter_by(variant_kind="gender").all()
        assert {(form.variant_form_text, form.grammatical_gender) for form in forms} == {
            ("prima", "feminine"),
            ("primas", "feminine"),
        }
