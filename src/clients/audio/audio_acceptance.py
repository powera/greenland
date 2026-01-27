#!/usr/bin/python3
"""Audio acceptance workflow - move audio from staging to production."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

if TYPE_CHECKING:
    from wordfreq.storage.models.schema import AudioQualityReview

from clients.audio.s3_uploader import S3AudioUploader

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def accept_audio_for_production(
    session: Any,
    audio_review_id: int,
    accepted_by: Optional[str] = None,
    s3_uploader: Optional[S3AudioUploader] = None,
) -> Tuple[bool, str]:
    """
    Accept an audio file for production by moving it from staging to prod.

    Args:
        session: Database session
        audio_review_id: ID of the AudioQualityReview record
        accepted_by: Username or identifier of person accepting the audio
        s3_uploader: S3AudioUploader instance (creates new one if None)

    Returns:
        Tuple of (success: bool, message: str)
    """
    from wordfreq.storage.models.schema import AudioQualityReview

    # Get the audio review record
    audio_review = session.query(AudioQualityReview).filter_by(id=audio_review_id).first()

    if not audio_review:
        return False, f"Audio review record not found: {audio_review_id}"

    # Check if audio is in staging
    if not audio_review.s3_staging_url:
        return False, f"Audio {audio_review_id} has no staging URL - cannot accept"

    # Check if already in production
    if audio_review.s3_prod_url:
        logger.warning(
            f"Audio {audio_review_id} already in production at {audio_review.s3_prod_url}"
        )
        return True, f"Audio already in production: {audio_review.s3_prod_url}"

    # Check if we have the required info
    if not audio_review.staging_agent or not audio_review.manifest_md5:
        return False, f"Audio {audio_review_id} missing staging_agent or manifest_md5"

    # Initialize S3 uploader if not provided
    if s3_uploader is None:
        try:
            s3_uploader = S3AudioUploader()
        except Exception as e:
            return False, f"Failed to initialize S3 uploader: {e}"

    # Move audio from staging to prod
    success, prod_url = s3_uploader.move_to_production(
        md5_hash=audio_review.manifest_md5,
        agent=audio_review.staging_agent,
        language_code=audio_review.language_code,
        voice_name=audio_review.voice_name,
    )

    if not success:
        return False, f"Failed to move audio to production: {audio_review.manifest_md5}"

    # Update database record
    audio_review.s3_prod_url = prod_url
    audio_review.accepted_at = datetime.utcnow()
    audio_review.accepted_by = accepted_by

    try:
        session.commit()
        logger.info(f"Accepted audio {audio_review_id} for production: {prod_url}")
        return True, f"Audio accepted for production: {prod_url}"
    except Exception as e:
        session.rollback()
        return False, f"Database error: {e}"


def accept_multiple_audio(
    session: Any,
    audio_review_ids: List[int],
    accepted_by: Optional[str] = None,
) -> Tuple[int, int, List[str]]:
    """
    Accept multiple audio files for production.

    Args:
        session: Database session
        audio_review_ids: List of AudioQualityReview IDs to accept
        accepted_by: Username or identifier of person accepting the audio

    Returns:
        Tuple of (success_count: int, failure_count: int, error_messages: List[str])
    """
    # Initialize S3 uploader once for all operations
    try:
        s3_uploader = S3AudioUploader()
    except Exception as e:
        return 0, len(audio_review_ids), [f"Failed to initialize S3 uploader: {e}"]

    success_count = 0
    failure_count = 0
    error_messages = []

    for audio_id in audio_review_ids:
        success, message = accept_audio_for_production(
            session=session,
            audio_review_id=audio_id,
            accepted_by=accepted_by,
            s3_uploader=s3_uploader,
        )

        if success:
            success_count += 1
        else:
            failure_count += 1
            error_messages.append(f"Audio {audio_id}: {message}")

    return success_count, failure_count, error_messages


def get_pending_staging_audio(
    session: Any,
    language_code: Optional[str] = None,
    staging_agent: Optional[str] = None,
    status: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Any]:
    """
    Get audio files that are in staging and ready for acceptance.

    Args:
        session: Database session
        language_code: Filter by language code
        staging_agent: Filter by staging agent (vieversys, strazdas)
        status: Filter by review status (default: approved)
        limit: Maximum number of results

    Returns:
        List of AudioQualityReview objects
    """
    from wordfreq.storage.models.schema import AudioQualityReview

    query = session.query(AudioQualityReview).filter(
        AudioQualityReview.s3_staging_url.isnot(None),  # Has staging URL
        AudioQualityReview.s3_prod_url.is_(None),  # Not yet in prod
    )

    if language_code:
        query = query.filter(AudioQualityReview.language_code == language_code)

    if staging_agent:
        query = query.filter(AudioQualityReview.staging_agent == staging_agent)

    if status:
        query = query.filter(AudioQualityReview.status == status)
    else:
        # Default to approved audio
        query = query.filter(AudioQualityReview.status == "approved")

    if limit:
        query = query.limit(limit)

    result: List["AudioQualityReview"] = query.all()
    return result
