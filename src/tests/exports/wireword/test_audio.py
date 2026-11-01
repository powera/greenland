"""WireWord never chooses a competing take by database row order."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from exports.wireword.audio import build_audio_index
from exports.wireword.export_wireword import WirewordExporter
from storage.models.schema import AudioQualityReview, Base, Lemma


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        db_session.add(
            Lemma(
                guid="N30_078",
                lemma_text="airport",
                definition_text="air travel facility",
                pos_type="noun",
                pos_subtype="place_name",
            )
        )
        db_session.flush()
        yield db_session
    engine.dispose()


def audio(
    session: Session,
    guid: str,
    md5: str,
    *,
    voice: str = "ruta",
    slot: str | None = None,
    status: str = "pending_review",
    prod: bool = False,
) -> AudioQualityReview:
    row = AudioQualityReview(
        guid=guid,
        language_code="lt",
        voice_name=voice,
        grammatical_form=slot,
        expected_text="oro uostas",
        filename=f"{md5}.mp3",
        manifest_md5=md5,
        status=status,
        s3_prod_url=f"https://example.com/{md5}" if prod else None,
        s3_staging_url=f"https://example.com/staging/{md5}",
    )
    session.add(row)
    session.flush()
    return row


def test_historical_guid_cannot_leak_even_when_requested(session: Session) -> None:
    audio(session, "N07_022", "historical", prod=True)
    audio(session, "N30_078", "preferred", prod=True)
    result = build_audio_index(session, ["N07_022", "N30_078"], "lt")
    assert result == {("N30_078", None): {"ruta": "preferred"}}
    exporter = WirewordExporter(language="lt")
    assert exporter._get_audio_hashes(session, "N07_022", "lt") is None
    assert exporter._get_audio_hashes(session, "N30_078", "lt") == {"ruta": "preferred"}


def test_competing_current_takes_are_withheld_not_arbitrarily_selected(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    audio(session, "N30_078", "first")
    audio(session, "N30_078", "second")
    audio(session, "N30_078", "male", voice="jonas")
    assert build_audio_index(session, ["N30_078"], "lt", include_staging=True) == {
        ("N30_078", None): {"jonas": "male"}
    }
    assert "Withholding ambiguous WireWord audio" in caplog.text


def test_duplicate_references_to_the_same_asset_are_safe(session: Session) -> None:
    audio(session, "N30_078", "same")
    audio(session, "N30_078", "same")
    assert build_audio_index(session, ["N30_078"], "lt", include_staging=True) == {
        ("N30_078", None): {"ruta": "same"}
    }


def test_upload_and_rejection_policy_is_preserved(session: Session) -> None:
    audio(session, "N30_078", "staging")
    audio(session, "N30_078", "rejected", status="needs_replacement")
    assert build_audio_index(session, ["N30_078"], "lt") == {}
    assert build_audio_index(session, ["N30_078"], "lt", include_staging=True) == {
        ("N30_078", None): {"ruta": "staging"}
    }


def test_missing_asset_and_separate_slots_do_not_collide(session: Session) -> None:
    audio(session, "N30_078", "base")
    audio(session, "N30_078", "", voice="jonas")
    audio(session, "N30_078", "variant", slot="variant/gender/female/base")
    assert build_audio_index(session, ["N30_078"], "lt", include_staging=True) == {
        ("N30_078", None): {"ruta": "base"},
        ("N30_078", "variant/gender/female/base"): {"ruta": "variant"},
    }
