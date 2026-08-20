#!/usr/bin/env python3
"""Create and update AudioQualityReview rows.

Every audio-generating or audio-importing path ends by recording that a file
exists and needs review. Doing that correctly is subtler than an insert, and it
was implemented separately in three places before this module existed
(agents.gandras, agents.vieversys, workqueue.handlers.vieversys).

Two constraints make a plain insert wrong, in opposite ways:

* Sentence audio is covered by uq_audio_review_sentence (sentence_id,
  language_code, voice_name), all non-NULL, so re-generating raised
  IntegrityError.
* Lemma audio is covered by uq_audio_review_lemma, which includes
  grammatical_form. Callers generating base forms leave it NULL, and SQL
  compares NULLs as distinct, so nothing caught the duplicate and a second row
  appeared on every run.

find_existing_review() performs the correct lookup for both shapes; callers
that find a row update it rather than inserting.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview

logger = logging.getLogger(__name__)

# Fields describing a *previous* review verdict. Whenever a row is pointed at
# new audio, these must be cleared together -- leaving any of them behind
# attributes an old human judgement to a file nobody has heard.
_VERDICT_FIELDS = ("quality_issues", "notes", "reviewed_at", "reviewed_by")


def find_existing_review(
    session: Session,
    language_code: str,
    voice_name: str,
    guid: Optional[str] = None,
    sentence_id: Optional[int] = None,
    grammatical_form: Optional[str] = None,
) -> Optional[AudioQualityReview]:
    """Look up the AudioQualityReview row a new audio file would collide with.

    Mirrors the two unique constraints on the table: sentence audio is keyed by
    (sentence_id, language_code, voice_name), lemma audio by (guid,
    language_code, voice_name, grammatical_form).

    Args:
        session: Database session
        language_code: Language of the audio
        voice_name: Voice the audio was generated with
        guid: Lemma GUID, for lemma audio
        sentence_id: Sentence ID, for sentence audio
        grammatical_form: Form for lemma audio; None means the base form

    Returns:
        The existing row, or None if this audio is new.
    """
    if sentence_id is not None:
        row: Optional[AudioQualityReview] = (
            session.query(AudioQualityReview)
            .filter_by(
                sentence_id=sentence_id,
                language_code=language_code,
                voice_name=voice_name,
            )
            .first()
        )
        return row

    if guid is not None:
        row = (
            session.query(AudioQualityReview)
            .filter_by(
                guid=guid,
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=grammatical_form,
            )
            .first()
        )
        return row

    raise ValueError("find_existing_review requires one of guid or sentence_id")


def clear_review_verdict(review: AudioQualityReview) -> None:
    """Drop any previous review verdict from a row being pointed at new audio.

    Call this whenever a row's audio changes. The status is left to the caller,
    which knows whether the new file is pending review or auto-approved.
    """
    for field in _VERDICT_FIELDS:
        setattr(review, field, None)
