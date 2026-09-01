"""Audio-specific helper functions for the Barsukas UI.

TODO: Consider moving copy_staging_to_prod and related path parsing logic
to src/clients/audio/ to consolidate S3 storage code in one place.
"""

import logging
import re
from typing import Any, Optional, Tuple, cast

from storage.models.schema import Lemma

logger = logging.getLogger(__name__)


def link_audio_to_lemma(
    session: Any, guid: str, expected_text: str, language_code: str
) -> Optional[int]:
    """
    Hybrid approach to link audio file to lemma.

    1. Try to match by GUID
    2. Fallback to matching by text in appropriate language translation field

    Args:
        session: Database session
        guid: GUID like "N01_001"
        expected_text: Text that should be spoken
        language_code: Language code (zh, ko, fr, etc.)

    Returns:
        Lemma ID if found, None otherwise
    """
    # Try GUID match first
    lemma = session.query(Lemma).filter_by(guid=guid).first()
    if lemma:
        return cast(int, lemma.id)

    # Fallback to text matching. Every language lives in LemmaTranslation now;
    # the per-language Lemma columns this used to consult for zh/ko/fr/sw/lt/vi
    # are gone.
    from storage.models.schema import LemmaTranslation

    translation = (
        session.query(LemmaTranslation)
        .filter_by(language_code=language_code, translation=expected_text)
        .first()
    )
    if translation:
        return cast(int, translation.lemma_id)

    return None


def validate_audio_translation(
    session: Any, guid: str, expected_text: str, language_code: str
) -> dict:
    """
    Validate that audio file's expected text matches the current translation in the database.

    Args:
        session: Database session
        guid: GUID like "N01_001"
        expected_text: Text from audio file manifest
        language_code: Language code (zh, ko, fr, etc.)

    Returns:
        Dict with validation results: {
            "valid": bool,
            "current_translation": str or None,
            "mismatch": bool,
            "lemma_found": bool
        }
    """
    # Try to find lemma by GUID
    lemma = session.query(Lemma).filter_by(guid=guid).first()

    if not lemma:
        return {
            "valid": False,
            "current_translation": None,
            "mismatch": False,
            "lemma_found": False,
        }

    # Get current translation from database. All languages live in
    # LemmaTranslation; the per-language Lemma columns are gone.
    from storage.models.schema import LemmaTranslation

    current_translation = None
    translation = (
        session.query(LemmaTranslation)
        .filter_by(lemma_id=lemma.id, language_code=language_code)
        .first()
    )
    if translation:
        current_translation = translation.translation

    # Check if they match
    if current_translation is None:
        return {"valid": False, "current_translation": None, "mismatch": False, "lemma_found": True}

    mismatch = current_translation != expected_text

    return {
        "valid": not mismatch,
        "current_translation": current_translation,
        "mismatch": mismatch,
        "lemma_found": True,
    }


def copy_staging_to_prod(staging_url: str) -> Tuple[bool, str]:
    """
    Copy audio from staging to production.

    Parses staging URL to extract language, voice, and md5, then copies to:
    staging/{language}/{voice}/{md5}.mp3 -> prod/{md5}.mp3

    Args:
        staging_url: Full CDN URL to staging audio file

    Returns:
        Tuple of (success: bool, prod_url_or_error: str)
    """
    from clients.audio.s3_uploader import (
        get_prod_audio_key,
        get_staging_audio_key,
    )

    # Extract path parts from staging URL: staging/{lang}/{voice}/{md5}.mp3
    # (accepting both the "staging" and "staging-postgres" prefixes)
    match = re.search(r"/staging(?:-postgres)?/([^/]+)/([^/]+)/([a-f0-9]+)\.mp3$", staging_url)
    if not match:
        return False, f"Could not parse staging URL: {staging_url}"

    language_code = match.group(1)
    voice_name = match.group(2)
    md5_hash = match.group(3)

    staging_key = get_staging_audio_key(language_code, voice_name, md5_hash)
    prod_key = get_prod_audio_key(language_code, voice_name, md5_hash)

    try:
        from clients.audio.s3_uploader import S3AudioUploader

        s3_uploader = S3AudioUploader()

        # Check if already in prod
        try:
            s3_uploader.s3.head_object(Bucket=s3_uploader.bucket_name, Key=prod_key)
            prod_url = s3_uploader.get_cdn_url(prod_key)
            logger.info(f"Audio already exists in production: {prod_key}")
            return True, prod_url
        except Exception:
            pass  # Not in prod yet, proceed with copy

        # Copy from staging to prod
        copy_source = {"Bucket": s3_uploader.bucket_name, "Key": staging_key}

        s3_uploader.s3.copy_object(
            CopySource=copy_source,
            Bucket=s3_uploader.bucket_name,
            Key=prod_key,
            ACL="public-read",
            ContentType="audio/mpeg",
            CacheControl="public, max-age=31536000, immutable",
            MetadataDirective="REPLACE",
        )

        prod_url = s3_uploader.get_cdn_url(prod_key)
        logger.info(f"Copied to production: {staging_key} -> {prod_key}")
        return True, prod_url

    except Exception as e:
        logger.error(f"Error copying to production: {e}")
        return False, str(e)


def sync_rejection_to_s3(review: Any, rejected_by: str = "rapid_review") -> Tuple[bool, str]:
    """Make the staged manifest agree with this row's review status.

    A rejection recorded only in this database is invisible to everyone else:
    the next database to run gandras re-imports the file and re-adopts audio
    this one threw out. Staged audio is content-addressed -- the key is the
    MD5 -- so the verdict goes in the manifest beside it, where it travels with
    the audio.

    Driven by the row's *current* status rather than by which button was
    pressed, so undo is handled by the same call: moving out of
    'needs_replacement' clears the block that moving into it wrote.

    Callers should treat a False return as non-fatal and leave the database
    verdict standing -- push_audio_rejections_to_s3.py reconciles later. This
    mirrors copy_staging_to_prod, which likewise lets the review stand when S3
    is unreachable.

    Args:
        review: The AudioQualityReview row, already carrying its new status
        rejected_by: Recorded in the manifest as who made the call

    Returns:
        Tuple of (success, message). Success with "no manifest" when the row
        has no MD5 to address, since there is nothing to write.
    """
    from audiotools import s3_ops
    from clients.audio.s3_uploader import S3AudioUploader, get_staging_manifest_key

    if not review.manifest_md5:
        return True, "no manifest to update"

    # Rebuilt from the row's own fields rather than parsed out of the stored
    # CDN URL, so an endpoint change cannot misaddress the write.
    manifest_key = get_staging_manifest_key(
        review.language_code, review.voice_name, review.manifest_md5
    )

    try:
        uploader = S3AudioUploader()

        if review.status == "needs_replacement":
            reason = str(review.notes) if review.notes else "Rejected during audio review"
            ok = s3_ops.mark_manifest_rejected(
                uploader,
                manifest_key=manifest_key,
                reason=reason,
                rejected_by=rejected_by,
                quality_issues=review.quality_issues,
            )
            return (ok, "rejected in S3" if ok else "failed to write rejection")

        # Any other status means this audio is not rejected, so a block left
        # over from a previous rejection (or an undo) must come off.
        ok = s3_ops.clear_manifest_rejection(uploader, manifest_key)
        return (ok, "rejection cleared in S3" if ok else "failed to clear rejection")

    except Exception as e:
        logger.error(f"Error syncing rejection state for {manifest_key}: {e}")
        return False, str(e)
