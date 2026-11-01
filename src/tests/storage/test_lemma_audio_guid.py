"""Audio survives subtype moves and historical repairs retain competing takes."""

import runpy
from pathlib import Path
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.guid_tombstone import create_tombstone
from storage.crud.lemma import handle_lemma_type_subtype_change
from storage.models.guid_tombstone import (
    TOMBSTONE_REASON_SUBTYPE_CHANGE,
    TOMBSTONE_REASON_TYPE_CHANGE,
)
from storage.models.schema import AudioQualityReview, Base, Lemma, LemmaTranslation


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def owner(session: Session, guid: str = "N07_022") -> Lemma:
    lemma = Lemma(
        lemma_text="airport",
        definition_text="air travel facility",
        pos_type="noun",
        pos_subtype="building_structure",
        guid=guid,
    )
    session.add(lemma)
    session.flush()
    session.add(LemmaTranslation(lemma_id=lemma.id, language_code="lt", translation="oro uostas"))
    session.flush()
    return lemma


def recording(
    session: Session, lemma: Lemma, guid: str, *, slot: str | None = None, status: str = "approved"
) -> AudioQualityReview:
    audio = AudioQualityReview(
        guid=guid,
        lemma_id=lemma.id,
        language_code="lt",
        voice_name="ruta",
        grammatical_form=slot,
        expected_text="oro uostas",
        filename=f"{guid}.mp3",
        manifest_md5=guid,
        status=status,
        s3_prod_url=f"https://example.com/{guid}.mp3",
    )
    session.add(audio)
    session.flush()
    return audio


def retire(
    session: Session,
    lemma: Lemma,
    old: str,
    new: str,
    reason: str = TOMBSTONE_REASON_SUBTYPE_CHANGE,
) -> None:
    create_tombstone(
        session, old, "airport", "noun", "building_structure", new, lemma.id, reason=reason
    )


def repair(session: Session, preferred: frozenset[int] = frozenset()) -> dict[str, list[int]]:
    path = Path(__file__).resolve().parents[3] / "migrations/20261101_repair_audio_guids.py"
    namespace: dict[str, Any] = runpy.run_path(str(path))
    result: dict[str, list[int]] = namespace["repair_audio_guids"](session, preferred)
    return result


@pytest.mark.parametrize("slot", [None, "noun/lt_genitive_singular", "variant/gender/female/base"])
def test_subtype_move_preserves_audio_and_verdict(session: Session, slot: str | None) -> None:
    lemma = owner(session)
    audio = recording(session, lemma, "N07_022", slot=slot)
    original_asset = (audio.manifest_md5, audio.filename, audio.s3_prod_url)
    result = handle_lemma_type_subtype_change(session, lemma, "noun", "place_name")
    assert result["audio_records_moved"] == 1
    assert audio.guid == lemma.guid != "N07_022"
    assert audio.lemma_id == lemma.id
    assert audio.status == "approved"
    assert (audio.manifest_md5, audio.filename, audio.s3_prod_url) == original_asset


def test_pos_change_does_not_make_old_pronunciation_usable(session: Session) -> None:
    lemma = owner(session)
    audio = recording(session, lemma, "N07_022")
    handle_lemma_type_subtype_change(session, lemma, "verb", "physical_action")
    assert audio.guid == lemma.guid
    assert audio.status == "needs_replacement"


def test_deleted_forms_are_invalidated_but_base_is_preserved(session: Session) -> None:
    lemma = owner(session)
    base = recording(session, lemma, "N07_022")
    form = recording(session, lemma, "N07_022", slot="noun/lt_genitive_singular")
    variant = recording(session, lemma, "N07_022", slot="variant/gender/female/base")
    handle_lemma_type_subtype_change(
        session, lemma, "noun", "place_name", drop_forms_on_subtype_change=True
    )
    assert base.status == "approved"
    assert form.status == "needs_replacement"
    assert variant.status == "approved"
    assert form.guid == base.guid == lemma.guid


def test_rollback_restores_audio_and_lemma_together(session: Session) -> None:
    lemma = owner(session)
    audio = recording(session, lemma, "N07_022")
    session.commit()
    handle_lemma_type_subtype_change(session, lemma, "noun", "place_name")
    session.rollback()
    assert lemma.guid == audio.guid == "N07_022"


def test_historical_repair_follows_subtype_chain_and_is_rerunnable(session: Session) -> None:
    lemma = owner(session, "N30_078")
    audio = recording(session, lemma, "N07_022")
    retire(session, lemma, "N07_022", "N30_001")
    retire(session, lemma, "N30_001", "N30_078")
    assert repair(session)["moved"] == [audio.id]
    assert audio.guid == lemma.guid
    assert repair(session)["moved"] == []


def test_historical_conflict_preserves_both_until_explicit_choice(session: Session) -> None:
    lemma = owner(session, "N30_078")
    old = recording(session, lemma, "N07_022")
    new = recording(session, lemma, "N30_078")
    retire(session, lemma, "N07_022", "N30_078")
    assert repair(session)["conflicts"] == [old.id]
    assert old.guid == "N07_022" and new.guid == "N30_078"
    assert repair(session, frozenset({old.id}))["preferred"] == [old.id]
    assert old.guid == "N30_078" and new.guid == "N07_022"
    assert old.manifest_md5 == "N07_022" and new.manifest_md5 == "N30_078"
    assert session.query(AudioQualityReview).count() == 2
    assert repair(session, frozenset({old.id}))["preferred"] == []
    assert old.guid == "N30_078"


def test_repair_skips_text_changes_and_pos_changes(session: Session) -> None:
    lemma = owner(session, "N30_078")
    audio = recording(session, lemma, "N07_022")
    retire(session, lemma, "N07_022", "N30_078", reason=TOMBSTONE_REASON_TYPE_CHANGE)
    assert repair(session)["unresolved"] == [audio.id]
    retire(session, lemma, "N07_022", "N30_078")
    audio.expected_text = "wrong text"
    assert repair(session)["text_mismatch"] == [audio.id]
    assert audio.guid == "N07_022"


def test_repair_does_not_trust_an_unrelated_lemma_id_in_history(session: Session) -> None:
    lemma = owner(session, "N30_078")
    other = owner(session, "N30_079")
    audio = recording(session, lemma, "N07_022")
    retire(session, other, "N07_022", "N30_078")
    assert repair(session)["unresolved"] == [audio.id]
    assert audio.guid == "N07_022"
