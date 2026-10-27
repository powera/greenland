"""Real persistence with fake synthesis: share assets, retain semantic slots."""

from pathlib import Path
from typing import Any, Dict, Iterator
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from agents.vieversys import VieversysAgent
from audiotools.lemma_audio import (
    LemmaAudioTarget,
    alias_recording,
    generate_lemma_audio_targets,
    lemma_audio_targets,
    reusable_recording,
)
from clients.audio.gpt_voices import GptVoice
from clients.audio.types import AudioGenerationResult, Voice
from exports.wireword.gendered_forms import build_gendered_forms
from storage.backend.config import DataSourceConfig
from storage.crud.variant_form import add_variant_form
from storage.models.schema import AudioQualityReview, Base, DerivativeForm, Lemma, LemmaTranslation
from storage.translation_helpers import set_translation
from storage.variant_audio import gender_audio_slot


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def actor(session: Session, language: str = "en") -> Lemma:
    lemma = Lemma(
        guid="N36_047",
        lemma_text="actor",
        definition_text="A performer.",
        pos_type="noun",
        pos_subtype="occupation",
    )
    session.add(lemma)
    session.flush()
    if language != "en":
        session.add(
            LemmaTranslation(lemma_id=lemma.id, language_code=language, translation="actor")
        )
    for key, text in (("male", "actor"), ("female", "actress")):
        add_variant_form(
            session,
            lemma,
            text,
            language,
            key,
            f"noun/{language}_singular",
            variant_kind="gender",
            is_base_form=True,
            link_word_token=False,
        )
    session.commit()
    return lemma


def generated(text: str) -> AudioGenerationResult:
    return AudioGenerationResult(
        audio_data=text.encode(),
        text=text,
        voice=Voice.ALLOY,
        language_code="en",
        model="fake",
        duration_ms=100,
    )


@pytest.mark.parametrize("engine", ["openai", "google"])
def test_batch_generates_two_assets_reuses_and_force_still_deduplicates(
    session: Session,
    tmp_path: Path,
    engine: str,
) -> None:
    lemma = actor(session)
    agent = VieversysAgent(
        DataSourceConfig(),
        output_dir=str(tmp_path),
        upload_s3=False,
        tts_engine=engine,
        skip_existing=True,
    )
    with (
        patch.object(agent, "get_session", return_value=session),
        patch(
            "agents.vieversys.generate_audio", side_effect=lambda **kw: generated(kw["text"])
        ) as tts,
        patch.object(
            agent, "_call_cloud_tts", side_effect=lambda text, *_: generated(text)
        ) as cloud,
    ):
        kwargs = (
            {"voices": [GptVoice.GPT_ES_M1]}
            if engine == "openai"
            else {"cloud_voice_names": ["test"]}
        )
        result = agent.generate_batch("en", [lemma], **kwargs)
        assert result["success_count"] == 1
        synthesis = tts if engine == "openai" else cloud
        assert synthesis.call_count == 2
        rows = session.query(AudioQualityReview).all()
        assert len(rows) == 3
        by_slot = {row.grammatical_form: row for row in rows}
        assert by_slot[None].manifest_md5 == by_slot[gender_audio_slot("male")].manifest_md5
        assert by_slot[None].manifest_md5 != by_slot[gender_audio_slot("female")].manifest_md5
        agent.generate_batch("en", [lemma], **kwargs)
        assert synthesis.call_count == 2
        agent.skip_existing = False
        agent.generate_batch("en", [lemma], **kwargs)
        assert synthesis.call_count == 4
        assert session.query(AudioQualityReview).count() == 3


def test_default_edit_preserves_variant_asset_and_variant_edit_preserves_default(
    session: Session,
) -> None:
    lemma = actor(session, "es")
    default = AudioQualityReview(
        guid=lemma.guid,
        lemma_id=lemma.id,
        language_code="es",
        voice_name="test",
        expected_text="actor",
        filename="a.mp3",
        manifest_md5="a",
        status="approved",
        s3_prod_url="https://example/a.mp3",
    )
    session.add(default)
    session.flush()
    male = alias_recording(session, default, gender_audio_slot("male"))
    set_translation(session, lemma, "es", "intérprete")
    assert default.status == "needs_replacement"
    assert male.status == "approved"
    add_variant_form(
        session,
        lemma,
        "artista",
        "es",
        "male",
        "noun/es_singular",
        variant_kind="gender",
        is_base_form=True,
        link_word_token=False,
    )
    assert male.status == "needs_replacement"


@pytest.mark.parametrize(
    "language,voice,status,expected",
    [
        ("en-gb", "test", "approved", False),
        ("en", "other", "approved", False),
        ("en", "test", "needs_replacement", False),
        ("en", "test", "approved", True),
    ],
)
def test_reuse_never_crosses_accent_voice_or_bad_verdict(
    session: Session,
    tmp_path: Path,
    language: str,
    voice: str,
    status: str,
    expected: bool,
) -> None:
    lemma = actor(session)
    session.add(
        AudioQualityReview(
            guid=lemma.guid,
            lemma_id=lemma.id,
            language_code=language,
            voice_name=voice,
            expected_text="actor",
            filename="a.mp3",
            manifest_md5="a",
            status=status,
            s3_prod_url="https://example/a.mp3",
        )
    )
    session.flush()
    found = reusable_recording(
        session, lemma, "en", "test", LemmaAudioTarget(gender_audio_slot("male"), "actor"), tmp_path
    )
    assert (found is not None) is expected


def test_dialect_planning_and_inflections_are_explicit(session: Session) -> None:
    lemma = actor(session, "es-419")
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            language_code="es-419",
            grammatical_form="noun/es_plural",
            derivative_form_text="actors",
        )
    )
    add_variant_form(
        session,
        lemma,
        "actresses",
        "es-419",
        "female",
        "noun/es_plural",
        variant_kind="gender",
        link_word_token=False,
    )
    assert {target.text for target in lemma_audio_targets(session, lemma, "es-mx")} == {
        "actor",
        "actress",
    }
    assert {
        target.text for target in lemma_audio_targets(session, lemma, "es-mx", include_forms=True)
    } == {"actor", "actress", "actors", "actresses"}
    assert len(lemma_audio_targets(session, lemma, "es-mx", include_variants=False)) == 1
    assert not lemma_audio_targets(session, lemma, "es")


def test_export_shares_per_voice_without_changing_grammar() -> None:
    word: Dict[str, Any] = {
        "guid": "N36_047",
        "base_target": "actor",
        "base_english": "actor",
        "audio": {"test": "a"},
        "grammar_metadata": {"grammatical_gender": "common"},
    }
    variants = {
        "en": [
            {
                "key": key,
                "grammatical_gender": gender,
                "forms": [
                    {"text": text, "grammatical_form": "noun/en_singular", "is_base_form": True}
                ],
            }
            for key, text, gender in (
                ("male", "actor", "masculine"),
                ("female", "actress", "feminine"),
            )
        ]
    }
    forms = build_gendered_forms(
        word,
        variants,
        "en",
        "en",
        {
            (word["guid"], None): {"test": "a"},
            (word["guid"], gender_audio_slot("female")): {"test": "b"},
        },
    )
    assert [form["audio"]["test"] for form in forms] == ["a", "a", "b"]
    assert forms[1]["grammatical_forms"][0]["audio"] == {"test": "a"}
    assert [form["grammar_metadata"]["grammatical_gender"] for form in forms] == [
        "common",
        "masculine",
        "feminine",
    ]


def test_review_and_production_acceptance_follow_the_shared_asset(session: Session) -> None:
    from unittest.mock import Mock
    from audiotools.review_records import propagate_asset_review
    from clients.audio.audio_acceptance import accept_audio_for_production

    lemma = actor(session)
    base = AudioQualityReview(
        guid=lemma.guid,
        lemma_id=lemma.id,
        language_code="en",
        voice_name="test",
        expected_text="actor",
        filename="a.mp3",
        manifest_md5="a",
        status="pending_review",
        s3_staging_url="https://example/staging/a.mp3",
        staging_agent="vieversys",
    )
    session.add(base)
    session.flush()
    male = alias_recording(session, base, gender_audio_slot("male"))
    base.status = "approved"
    propagate_asset_review(session, base)
    assert male.status == "approved"
    uploader = Mock()
    uploader.move_to_production.return_value = (True, "https://example/prod/a.mp3")
    success, _ = accept_audio_for_production(session, base.id, s3_uploader=uploader)
    assert success
    assert male.s3_prod_url == base.s3_prod_url
    base.status = "needs_replacement"
    base.quality_issues = '["pronunciation_error"]'
    propagate_asset_review(session, base)
    assert male.status == "needs_replacement"
    male.quality_issues = '["translation_mismatch"]'
    base.status = "approved"
    base.quality_issues = None
    propagate_asset_review(session, base)
    assert male.status == "needs_replacement"


def test_review_validation_reads_the_variant_not_the_default(session: Session) -> None:
    from barsukas.helpers.audio_helpers import validate_audio_translation

    lemma = actor(session, "es-419")
    assert lemma.guid is not None
    valid = validate_audio_translation(
        session, lemma.guid, "actress", "es-mx", gender_audio_slot("female")
    )
    assert valid["valid"]
    assert valid["current_translation"] == "actress"
    invalid = validate_audio_translation(
        session, lemma.guid, "actor", "es-mx", gender_audio_slot("female")
    )
    assert invalid["mismatch"]


def test_local_generation_shares_and_reuses_recordings(session: Session, tmp_path: Path) -> None:
    from agents.strazdas import StrazdasAgent
    from audioshoe.espeak import EspeakVoice

    lemma = actor(session)
    agent = StrazdasAgent(DataSourceConfig(), output_dir=str(tmp_path))
    with (
        patch.object(agent, "get_session", return_value=session),
        patch.object(
            agent,
            "_generate_audio_with_backend",
            side_effect=lambda voice, text, ipa: generated(text),
        ) as synthesis,
    ):
        result = agent.generate_batch("en", [lemma], voices=[EspeakVoice.CLAIRE])
        assert result["success_count"] == 1
        assert synthesis.call_count == 2
        agent.generate_batch("en", [lemma], voices=[EspeakVoice.CLAIRE])
        assert synthesis.call_count == 2
        agent.generate_batch("en", [lemma], voices=[EspeakVoice.CLAIRE], skip_existing=False)
        assert synthesis.call_count == 4
        assert session.query(AudioQualityReview).count() == 3


def test_regenerating_one_slot_preserves_another_slots_local_asset(
    session: Session, tmp_path: Path
) -> None:
    lemma = actor(session)
    agent = VieversysAgent(DataSourceConfig(), output_dir=str(tmp_path), upload_s3=False)
    with (
        patch.object(agent, "get_session", return_value=session),
        patch("agents.vieversys.generate_audio", side_effect=lambda **kw: generated(kw["text"])),
    ):
        agent.generate_batch("en", [lemma], voices=[GptVoice.GPT_ES_M1])
    male = (
        session.query(AudioQualityReview)
        .filter_by(grammatical_form=gender_audio_slot("male"))
        .one()
    )
    path = tmp_path / "en" / male.voice_name / male.filename
    old_asset = path.read_bytes()
    with patch("agents.vieversys.generate_audio", return_value=generated("new audio bytes")):
        agent.generate_audio_for_lemma(session, lemma, "en", [GptVoice.GPT_ES_M1])
    assert path.read_bytes() == old_asset
    base = session.query(AudioQualityReview).filter_by(grammatical_form=None).one()
    assert base.manifest_md5 != male.manifest_md5
    assert base.filename != male.filename
