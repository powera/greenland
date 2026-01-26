"""Audio-specific helper functions for the Barsukas UI."""

import logging
import re
from typing import Any, Optional, Tuple, cast

from wordfreq.storage.models.schema import Lemma

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

    # Fallback to text matching based on language
    # Map language codes to column names
    language_column_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "sw": "swahili_translation",
        "lt": "lithuanian_translation",
        "vi": "vietnamese_translation",
    }

    # For table-based translations (es, de, pt), query LemmaTranslation
    if language_code in ["es", "de", "pt"]:
        from wordfreq.storage.models.schema import LemmaTranslation

        translation = (
            session.query(LemmaTranslation)
            .filter_by(language_code=language_code, translation=expected_text)
            .first()
        )
        if translation:
            return cast(int, translation.lemma_id)

    # For column-based translations
    elif language_code in language_column_map:
        column_name = language_column_map[language_code]
        lemma = session.query(Lemma).filter(getattr(Lemma, column_name) == expected_text).first()
        if lemma:
            return cast(int, lemma.id)

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
    # Map language codes to column names
    language_column_map = {
        "zh": "chinese_translation",
        "ko": "korean_translation",
        "fr": "french_translation",
        "sw": "swahili_translation",
        "lt": "lithuanian_translation",
        "vi": "vietnamese_translation",
    }

    # Try to find lemma by GUID
    lemma = session.query(Lemma).filter_by(guid=guid).first()

    if not lemma:
        return {
            "valid": False,
            "current_translation": None,
            "mismatch": False,
            "lemma_found": False,
        }

    # Get current translation from database
    current_translation = None

    # For table-based translations (es, de, pt)
    if language_code in ["es", "de", "pt"]:
        from wordfreq.storage.models.schema import LemmaTranslation

        translation = (
            session.query(LemmaTranslation)
            .filter_by(lemma_id=lemma.id, language_code=language_code)
            .first()
        )
        if translation:
            current_translation = translation.translation

    # For column-based translations
    elif language_code in language_column_map:
        column_name = language_column_map[language_code]
        current_translation = getattr(lemma, column_name, None)

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
    Copy audio from staging to production using the new path format.

    Parses staging URL to extract language, voice, and md5, then copies to:
    staging/{language}/{voice}/{md5}.mp3 -> prod/{language}/{voice}/{md5}.mp3

    Args:
        staging_url: Full CDN URL to staging audio file

    Returns:
        Tuple of (success: bool, prod_url_or_error: str)
    """
    # Extract path parts from staging URL
    # Pattern: staging/{lang}/{voice}/{md5}.mp3
    match = re.search(r"/staging/([^/]+)/([^/]+)/([a-f0-9]+)\.mp3$", staging_url)
    if not match:
        return False, f"Could not parse staging URL: {staging_url}"

    language_code = match.group(1)
    voice_name = match.group(2)
    md5_hash = match.group(3)

    staging_key = f"staging/{language_code}/{voice_name}/{md5_hash}.mp3"
    prod_key = f"prod/{language_code}/{voice_name}/{md5_hash}.mp3"

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
