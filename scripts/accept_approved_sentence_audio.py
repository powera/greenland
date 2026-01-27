#!/usr/bin/env python3
"""One-off script to accept approved sentence audio and push to production S3.

This script handles both S3 path formats:
  New format: staging/{agent}/{language}/{voice}/{md5}.mp3 -> prod/{md5}.mp3
  Legacy vieversys format: staging/{language}/{voice}/{md5}.mp3 -> prod/{md5}.mp3

Usage:
    PYTHONPATH=src python scripts/accept_approved_sentence_audio.py --language lt --dry-run
    PYTHONPATH=src python scripts/accept_approved_sentence_audio.py --language lt
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Add src to path for imports
if str(Path(__file__).parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clients.audio.s3_uploader import S3AudioUploader
from wordfreq.storage.models.schema import AudioQualityReview
from wordfreq.storage.utils.session import create_database_session


def extract_staging_path_parts(
    staging_url: str,
) -> Optional[Tuple[Optional[str], str, str, str]]:
    """
    Extract agent, language, voice, and md5 from a staging URL.

    Supports two formats:
    - New format: .../staging/{agent}/{language}/{voice}/{md5}.mp3
    - Legacy vieversys format: .../staging/{language}/{voice}/{md5}.mp3

    Returns:
        Tuple of (agent or None, language, voice, md5) or None if parsing fails
    """
    # Try new format first: staging/{agent}/{lang}/{voice}/{md5}.mp3
    match = re.search(r"/staging/([^/]+)/([^/]+)/([^/]+)/([a-f0-9]+)\.mp3$", staging_url)
    if match:
        return match.group(1), match.group(2), match.group(3), match.group(4)

    # Try legacy vieversys format: staging/{lang}/{voice}/{md5}.mp3
    match = re.search(r"/staging/([^/]+)/([^/]+)/([a-f0-9]+)\.mp3$", staging_url)
    if match:
        return None, match.group(1), match.group(2), match.group(3)

    return None


def copy_staging_to_prod(
    s3_uploader: S3AudioUploader,
    agent: Optional[str],
    language_code: str,
    voice_name: str,
    md5_hash: str,
) -> Tuple[bool, str]:
    """
    Copy audio from staging to production.

    Supports both formats:
    - New: staging/{agent}/{language}/{voice}/{md5}.mp3 -> prod/{md5}.mp3
    - Legacy: staging/{language}/{voice}/{md5}.mp3 -> prod/{md5}.mp3
    """
    if agent:
        staging_key = f"staging/{agent}/{language_code}/{voice_name}/{md5_hash}.mp3"
    else:
        staging_key = f"staging/{language_code}/{voice_name}/{md5_hash}.mp3"
    prod_key = f"prod/{md5_hash}.mp3"

    try:
        # Check if already in prod
        try:
            s3_uploader.s3.head_object(Bucket=s3_uploader.bucket_name, Key=prod_key)
            prod_url = s3_uploader.get_cdn_url(prod_key)
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
        return True, prod_url

    except Exception as e:
        return False, str(e)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Accept approved sentence audio and push to production S3"
    )
    parser.add_argument(
        "--language",
        type=str,
        required=True,
        help="Language code to filter by (e.g., 'lt')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="src/wordfreq/data/linguistics.sqlite",
        help="Path to the database file",
    )
    args = parser.parse_args()

    # Create database session
    session = create_database_session(args.db_path)

    # Initialize S3 uploader
    s3_uploader: Optional[S3AudioUploader] = None
    if not args.dry_run:
        s3_uploader = S3AudioUploader()

    try:
        # Find approved sentence audio in staging that's not yet in prod
        query = session.query(AudioQualityReview).filter(
            AudioQualityReview.sentence_id.isnot(None),  # Sentence audio only
            AudioQualityReview.language_code == args.language,
            AudioQualityReview.status.in_(["approved", "approved_with_issues"]),
            AudioQualityReview.s3_staging_url.isnot(None),  # Has staging URL
            AudioQualityReview.s3_prod_url.is_(None),  # Not yet in prod
        )

        audio_files = query.all()
        print(
            f"Found {len(audio_files)} approved {args.language} sentence audio files to push to production"
        )

        if args.dry_run:
            print("\nDry run - would accept the following files:")
            for audio in audio_files:
                parts = extract_staging_path_parts(audio.s3_staging_url)
                if parts:
                    agent, lang, voice, md5 = parts
                    print(f"  ID {audio.id}: {audio.expected_text[:50]}...")
                    if agent:
                        print(f"      staging/{agent}/{lang}/{voice}/{md5}.mp3 -> prod/{md5}.mp3")
                    else:
                        print(f"      staging/{lang}/{voice}/{md5}.mp3 -> prod/{md5}.mp3")
                else:
                    print(
                        f"  ID {audio.id}: {audio.expected_text[:50]}... (INVALID URL: {audio.s3_staging_url})"
                    )
            return

        success_count = 0
        failure_count = 0

        for audio in audio_files:
            print(f"Accepting ID {audio.id}: {audio.expected_text[:50]}...")

            # Extract path parts from staging URL
            parts = extract_staging_path_parts(audio.s3_staging_url)
            if not parts:
                print(f"  -> Failed: Could not parse staging URL: {audio.s3_staging_url}")
                failure_count += 1
                continue

            agent, lang, voice, md5 = parts

            # Copy to production
            assert s3_uploader is not None
            success, result = copy_staging_to_prod(s3_uploader, agent, lang, voice, md5)

            if success:
                # Update database record
                audio.s3_prod_url = result
                audio.accepted_at = datetime.utcnow()
                audio.accepted_by = "accept_approved_sentence_audio.py"
                session.commit()

                success_count += 1
                print(f"  -> Success: {result}")
            else:
                failure_count += 1
                print(f"  -> Failed: {result}")

        print(f"\nDone: {success_count} succeeded, {failure_count} failed")

    finally:
        session.close()


if __name__ == "__main__":
    main()
