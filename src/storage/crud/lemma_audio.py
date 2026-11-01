"""Keep lemma audio references attached when their owning GUID changes."""

from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview, Lemma


def move_lemma_audio_guid(
    session: Session,
    lemma: Lemma,
    old_guid: str,
    new_guid: str,
    *,
    invalidate_all: bool = False,
    invalidate_forms: bool = False,
) -> int:
    """Move review metadata without changing assets, hashes, or review verdicts.

    A POS change invalidates recordings whose translations/forms were cleared.
    A subtype-only move preserves the existing pronunciation and review state.
    The caller owns the transaction, including the lemma and tombstone updates.
    """
    if old_guid == new_guid:
        return 0
    recordings = session.query(AudioQualityReview).filter_by(guid=old_guid, sentence_id=None).all()
    if session.query(AudioQualityReview).filter_by(guid=new_guid, sentence_id=None).first():
        raise ValueError(f"Audio already exists for replacement GUID {new_guid}")
    for recording in recordings:
        recording.guid = new_guid
        recording.lemma_id = lemma.id
        cleared_form = (
            invalidate_forms
            and recording.grammatical_form is not None
            and not recording.grammatical_form.startswith("variant/")
        )
        if invalidate_all or cleared_form:
            recording.status = "needs_replacement"
    session.flush()
    return len(recordings)
