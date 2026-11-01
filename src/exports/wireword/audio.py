"""Select unambiguous recordings attached to current lemma GUIDs."""

import logging
from collections import defaultdict
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview, Lemma

logger = logging.getLogger(__name__)
AudioIndex = dict[tuple[str, Optional[str]], dict[str, str]]


def build_audio_index(
    session: Session,
    guids: Sequence[str],
    language: str,
    *,
    include_staging: bool = False,
) -> AudioIndex:
    """Exclude historical takes and withhold conflicting assets for one voice.

    Repeated references to one hash are harmless. Different eligible hashes
    for the same current GUID, form, and voice require a review choice; query
    order must never decide which recording reaches the learner.
    """
    if not guids:
        return {}
    recordings = (
        session.query(AudioQualityReview)
        .join(Lemma, Lemma.guid == AudioQualityReview.guid)
        .filter(
            Lemma.guid.in_(guids),
            AudioQualityReview.language_code == language,
            AudioQualityReview.sentence_id.is_(None),
        )
        .all()
    )
    candidates: dict[tuple[str, Optional[str], str], set[str]] = defaultdict(set)
    for recording in recordings:
        if recording.status == "needs_replacement" or not recording.manifest_md5:
            continue
        if not (recording.s3_prod_url or (include_staging and recording.s3_staging_url)):
            continue
        assert recording.guid is not None
        identity = (recording.guid, recording.grammatical_form, recording.voice_name)
        candidates[identity].add(recording.manifest_md5)
    result: AudioIndex = {}
    for (guid, slot, voice), hashes in candidates.items():
        if len(hashes) != 1:
            logger.warning(
                "Withholding ambiguous WireWord audio for %s/%s/%s/%s: %s assets",
                guid,
                language,
                voice,
                slot or "base",
                len(hashes),
            )
            continue
        result.setdefault((guid, slot), {})[voice] = next(iter(hashes))
    return result
