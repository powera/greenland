"""Stable audio addresses for gender variants within a lemma."""

import json
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from langtools.dialect_overrides import get_dialects_reading, normalize_language_code
from storage.models.schema import AudioQualityReview
from storage.models.variant_form import GENDER_VARIANT_KEYS

logger = logging.getLogger(__name__)

# The issue recorded on a recording whose text no longer matches its word,
# shared with storage.translation_helpers.invalidate_audio_for_translation_change.
TEXT_MISMATCH_ISSUE = "translation_mismatch"


def gender_audio_slot(referent_gender: str, grammatical_form: Optional[str] = None) -> str:
    """Address variant audio in the existing grammatical_form audio key.

    Ordinary lemma audio keeps its existing NULL/base or inflection key. A
    variant needs a namespace so female and male singular audio cannot collide.
    """
    if referent_gender not in GENDER_VARIANT_KEYS:
        raise ValueError(f"Invalid gender variant key: {referent_gender!r}")
    return f"variant/gender/{referent_gender}/{grammatical_form or 'base'}"


def invalidate_gender_variant_audio(
    session: Session,
    guid: Optional[str],
    language_code: str,
    referent_gender: str,
    grammatical_form: Optional[str] = None,
) -> List[int]:
    """Mark a gender variant's recordings as needing replacement; the caller commits.

    The audio keys are stable per (referent gender, grammatical form), so a
    recording outlives the word it was made for: replacing female "actriz" with
    "intérprete" would otherwise export the actriz recording for intérprete.
    The WireWord export skips needs_replacement recordings.  Call this whenever
    a variant's text changes or the variant is removed.

    With *grammatical_form*, only that form's recording; without it, every
    recording of the variant (its base word changed, so its whole paradigm did).
    Presentation dialects reading the language are included, as for a
    translation change.

    Returns:
        The ids of the recordings invalidated.
    """
    if not guid or referent_gender not in GENDER_VARIANT_KEYS:
        return []
    languages = [normalize_language_code(language_code)]
    languages.extend(get_dialects_reading(language_code))
    query = session.query(AudioQualityReview).filter(
        AudioQualityReview.guid == guid,
        AudioQualityReview.language_code.in_(languages),
        AudioQualityReview.status != "needs_replacement",
    )
    if grammatical_form is None:
        prefix = f"variant/gender/{referent_gender}/"
        query = query.filter(AudioQualityReview.grammatical_form.like(f"{prefix}%"))
    else:
        query = query.filter(
            AudioQualityReview.grammatical_form
            == gender_audio_slot(referent_gender, grammatical_form)
        )
    invalidated: List[int] = []
    for audio in query.all():
        audio.status = "needs_replacement"
        try:
            issues: List[str] = json.loads(audio.quality_issues) if audio.quality_issues else []
        except (json.JSONDecodeError, TypeError):
            issues = []
        if TEXT_MISMATCH_ISSUE not in issues:
            issues.append(TEXT_MISMATCH_ISSUE)
            audio.quality_issues = json.dumps(issues)
        invalidated.append(audio.id)
    if invalidated:
        logger.info(
            "Invalidated %d %s/%s %s variant recording(s)",
            len(invalidated),
            guid,
            language_code,
            referent_gender,
        )
    return invalidated
