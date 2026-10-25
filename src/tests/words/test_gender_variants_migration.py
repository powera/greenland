"""The reviewed migration merges only cousins and preserves references/assets."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.grammar_fact import GrammarFact
from storage.models.guid_tombstone import GuidTombstone
from storage.models.lemma_fact import LemmaFact
from storage.models.operation_log import OperationLog
from storage.models.schema import (
    AudioQualityReview,
    Base,
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
    Sentence,
    SentenceWord,
)
from storage.models.variant_form import VariantForm
from storage.variant_audio import gender_audio_slot
from wordfreq.data.family_relations_sections import COUSIN_SECTION
from words.difficulty.family_relation_priorities import get_excluded_terms_for_language
from words.gender_variants import COUSIN_GUID, merge_cousin


def _migration() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "migrations/20261024_gender_variants.py"
    spec = importlib.util.spec_from_file_location("gender_variants_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _populate(session: Session) -> None:
    for guid, word, subtype in (
        (COUSIN_GUID, "cousin", "family_relation"),
        ("N35_047", "cousin", "family_relation"),
        ("N35_048", "cousin", "family_relation"),
        ("N36_047", "actor", "occupation"),
        ("N33_005", "German", "nationality"),
        ("N35_062", "aunt", "family_relation"),
    ):
        lemma = Lemma(
            guid=guid,
            lemma_text=word,
            definition_text=f"A {word}.",
            pos_type="noun",
            pos_subtype=subtype,
            difficulty_level=18,
        )
        session.add(lemma)
        session.flush()
        text = "prima" if guid == "N35_048" else "primo"
        session.add(LemmaTranslation(lemma_id=lemma.id, language_code="es", translation=text))
        session.add(
            GrammarFact(
                lemma_id=lemma.id,
                language_code="es",
                fact_type="grammatical_gender",
                fact_value="feminine" if guid == "N35_048" else "masculine",
            )
        )
        if guid in {COUSIN_GUID, "N35_047", "N35_048"}:
            session.add(
                LemmaFact(lemma_id=lemma.id, fact_type="concreteness", fact_value="physical")
            )
        if guid in {"N35_047", "N35_048"}:
            session.add(
                DerivativeForm(
                    lemma_id=lemma.id,
                    language_code="es",
                    grammatical_form="noun/es_plural",
                    derivative_form_text=text + "s",
                )
            )
            session.add(
                AudioQualityReview(
                    guid=guid,
                    lemma_id=lemma.id,
                    language_code="es",
                    voice_name="test",
                    filename=f"{guid}.mp3",
                    expected_text=text,
                    manifest_md5=guid,
                    status="approved",
                )
            )
        if guid == COUSIN_GUID:
            session.add(
                LemmaDifficultyOverride(lemma_id=lemma.id, language_code="es", difficulty_level=-1)
            )
    session.commit()


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        _populate(database_session)
        yield database_session
    engine.dispose()


def test_merge_preserves_audio_sentences_forms_and_tombstones(session: Session) -> None:
    female = session.query(Lemma).filter_by(guid="N35_048").one()
    sentence = Sentence(pattern_type="test")
    session.add(sentence)
    session.flush()
    session.add(
        SentenceWord(
            sentence_id=sentence.id,
            lemma_id=female.id,
            language_code="es",
            position=0,
            part_of_speech="noun",
            target_language_text="prima",
        )
    )
    session.commit()
    _migration().apply_changes(session)
    session.commit()
    cousin = session.query(Lemma).filter_by(guid=COUSIN_GUID).one()
    assert session.query(Lemma).filter(Lemma.guid.in_(["N35_047", "N35_048"])).count() == 0
    assert session.query(Lemma).filter_by(guid="N35_062").one().lemma_text == "aunt"
    assert session.query(SentenceWord).one().lemma_id == cousin.id
    assert session.query(SentenceWord).one().target_language_text == "prima"
    assert session.query(LemmaDifficultyOverride).filter_by(lemma_id=cousin.id).count() == 0
    assert {
        (row.variant_key, row.variant_form_text)
        for row in session.query(VariantForm).filter_by(lemma_id=cousin.id)
    } == {("male", "primo"), ("male", "primos"), ("female", "prima"), ("female", "primas")}
    assert {row.grammatical_form for row in session.query(AudioQualityReview)} == {
        gender_audio_slot("male"),
        gender_audio_slot("female"),
    }
    assert {row.manifest_md5 for row in session.query(AudioQualityReview)} == {"N35_047", "N35_048"}
    assert {row.replacement_guid for row in session.query(GuidTombstone)} == {COUSIN_GUID}
    assert session.query(LemmaFact).filter_by(lemma_id=cousin.id).count() == 1
    count = session.query(OperationLog).count()
    _migration().apply_changes(session)
    session.commit()
    assert session.query(OperationLog).count() == count


def test_unknown_merge_is_rejected(session: Session) -> None:
    with pytest.raises(ValueError, match="explicitly selected"):
        merge_cousin(session, "N35_062", "female")


def test_known_male_cousin_classification_error_keeps_physical_concept(session: Session) -> None:
    source = session.query(Lemma).filter_by(guid="N35_047").one()
    session.query(LemmaFact).filter_by(lemma_id=source.id).one().fact_value = "abstract"
    session.commit()
    assert merge_cousin(session, "N35_047", "male")
    target = session.query(Lemma).filter_by(guid=COUSIN_GUID).one()
    assert session.query(LemmaFact).filter_by(lemma_id=target.id).one().fact_value == "physical"
    log = session.query(OperationLog).filter_by(operation_type="lemma_merge").one()
    assert "abstract" in log.fact


def test_conflicting_fact_rolls_back_merge(session: Session) -> None:
    source = session.query(Lemma).filter_by(guid="N35_048").one()
    session.add(LemmaFact(lemma_id=source.id, fact_type="individuation", fact_value="collection"))
    target = session.query(Lemma).filter_by(guid=COUSIN_GUID).one()
    session.add(LemmaFact(lemma_id=target.id, fact_type="individuation", fact_value="individual"))
    session.commit()
    with pytest.raises(ValueError, match="conflicting concept fact"):
        with session.begin():
            merge_cousin(session, "N35_048", "female")
    assert session.query(Lemma).filter_by(guid="N35_048").count() == 1
    assert session.query(VariantForm).count() == 0
    assert session.query(GuidTombstone).count() == 0


def test_preview_is_read_only(tmp_path: Path) -> None:
    database = tmp_path / "preview.sqlite"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    with Session(engine) as fixture:
        _populate(fixture)
    engine.dispose()
    before = database.read_bytes()
    plan = _migration().preview(
        DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=str(database))
    )
    assert plan["mode"] == "read-only preview"
    assert plan["merge_into"] == COUSIN_GUID
    assert database.read_bytes() == before


def test_curriculum_keeps_one_cousin_without_recreating_gender_lemmas() -> None:
    assert [variant.guid for variant in COUSIN_SECTION.variants] == [COUSIN_GUID]
    for language in ("en", "es", "es-419", "fr", "de", "lt", "zh"):
        assert "cousin" not in get_excluded_terms_for_language(language)
