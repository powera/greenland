#!/usr/bin/env python3
"""Migrate staging audio files to the new path structure.

Old format: staging/{agent}/{md5}.mp3
New format: staging/{language}/{voice}/{md5}.mp3

This script:
1. Lists all files in staging/{agent}/ that match {md5}.mp3 pattern
2. For each file, fetches the corresponding .manifest file to get language and voice
3. Copies to new path staging/{lang}/{voice}/{md5}.mp3
4. Updates AudioQualityReview.s3_staging_url and s3_staging_manifest_url in database
5. Optionally deletes old files after migration

Usage:
    PYTHONPATH=src python scripts/migrate_staging_audio_paths.py --dry-run
    PYTHONPATH=src python scripts/migrate_staging_audio_paths.py --agent strazdas
    PYTHONPATH=src python scripts/migrate_staging_audio_paths.py --agent strazdas --delete-old
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add src to path for imports
if str(Path(__file__).parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clients.audio.s3_uploader import (
    S3AudioUploader,
    get_staging_prefix,
    get_staging_audio_key,
    get_staging_manifest_key,
)
from wordfreq.storage.backend import create_session as create_backend_session
from wordfreq.storage.backend.config import BackendType, DataSourceConfig
from wordfreq.storage.models.schema import AudioQualityReview


def is_old_format_path(key: str, agent: str) -> bool:
    """Check if a key matches the old format: staging/{agent}/{md5}.mp3"""
    staging_prefix = get_staging_prefix()
    pattern = rf"^{staging_prefix}/{agent}/[a-f0-9]+\.mp3$"
    return bool(re.match(pattern, key))


def extract_md5_from_key(key: str) -> Optional[str]:
    """Extract MD5 hash from a staging key."""
    match = re.search(r"/([a-f0-9]+)\.mp3$", key)
    return match.group(1) if match else None


def fetch_manifest(s3_uploader: S3AudioUploader, manifest_key: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse a manifest file from S3."""
    try:
        response = s3_uploader.s3.get_object(Bucket=s3_uploader.bucket_name, Key=manifest_key)
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)
    except Exception as e:
        print(f"  Warning: Could not fetch manifest {manifest_key}: {e}")
        return None


def list_old_format_files(s3_uploader: S3AudioUploader, agent: str) -> List[Tuple[str, str]]:
    """
    List all audio files in old format for the given agent.

    Returns list of (audio_key, manifest_key) tuples.
    """
    staging_prefix = get_staging_prefix()
    prefix = f"{staging_prefix}/{agent}/"

    old_format_files = []
    paginator = s3_uploader.s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=s3_uploader.bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Only match files directly under staging/{agent}/ (not in subdirectories)
            # and with .mp3 extension
            if key.endswith(".mp3") and is_old_format_path(key, agent):
                md5 = extract_md5_from_key(key)
                if md5:
                    manifest_key = key.replace(".mp3", ".manifest")
                    old_format_files.append((key, manifest_key))

    return old_format_files


def migrate_file(
    s3_uploader: S3AudioUploader,
    old_audio_key: str,
    old_manifest_key: str,
    agent: str,
    dry_run: bool = False,
    delete_old: bool = False,
) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Migrate a single audio file to the new path structure.

    Returns:
        Tuple of (success, message, new_audio_url, new_manifest_url)
    """
    md5 = extract_md5_from_key(old_audio_key)
    if not md5:
        return False, f"Could not extract MD5 from {old_audio_key}", None, None

    # Fetch manifest to get language and voice
    manifest = fetch_manifest(s3_uploader, old_manifest_key)
    if not manifest:
        return False, f"Could not fetch manifest for {old_audio_key}", None, None

    language_code = manifest.get("language_code")
    voice_name = manifest.get("voice_name")

    if not language_code or not voice_name:
        return (
            False,
            f"Manifest missing language_code or voice_name: {old_manifest_key}",
            None,
            None,
        )

    # Build new keys: staging/{language}/{voice}/{md5}.mp3
    new_audio_key = get_staging_audio_key(language_code, voice_name, md5)
    new_manifest_key = get_staging_manifest_key(language_code, voice_name, md5)

    if dry_run:
        return (
            True,
            f"Would migrate: {old_audio_key} -> {new_audio_key}",
            s3_uploader.get_cdn_url(new_audio_key),
            s3_uploader.get_cdn_url(new_manifest_key),
        )

    try:
        # Check if new file already exists
        try:
            s3_uploader.s3.head_object(Bucket=s3_uploader.bucket_name, Key=new_audio_key)
            # Already exists, just return the new URLs
            return (
                True,
                f"Already migrated: {new_audio_key}",
                s3_uploader.get_cdn_url(new_audio_key),
                s3_uploader.get_cdn_url(new_manifest_key),
            )
        except Exception:
            pass  # Doesn't exist, proceed with copy

        # Copy audio file
        s3_uploader.s3.copy_object(
            CopySource={"Bucket": s3_uploader.bucket_name, "Key": old_audio_key},
            Bucket=s3_uploader.bucket_name,
            Key=new_audio_key,
            ACL="public-read",
            ContentType="audio/mpeg",
            CacheControl="public, max-age=3600",
            MetadataDirective="REPLACE",
        )

        # Copy manifest file
        s3_uploader.s3.copy_object(
            CopySource={"Bucket": s3_uploader.bucket_name, "Key": old_manifest_key},
            Bucket=s3_uploader.bucket_name,
            Key=new_manifest_key,
            ACL="public-read",
            ContentType="application/json",
            CacheControl="public, max-age=3600",
            MetadataDirective="REPLACE",
        )

        # Optionally delete old files
        if delete_old:
            s3_uploader.s3.delete_object(Bucket=s3_uploader.bucket_name, Key=old_audio_key)
            s3_uploader.s3.delete_object(Bucket=s3_uploader.bucket_name, Key=old_manifest_key)

        return (
            True,
            f"Migrated: {old_audio_key} -> {new_audio_key}",
            s3_uploader.get_cdn_url(new_audio_key),
            s3_uploader.get_cdn_url(new_manifest_key),
        )

    except Exception as e:
        return False, f"Error migrating {old_audio_key}: {e}", None, None


def update_database_urls(
    session: Any,
    old_staging_url: str,
    new_staging_url: str,
    new_manifest_url: str,
    dry_run: bool = False,
) -> Tuple[int, str]:
    """
    Update AudioQualityReview records with new staging URLs.

    Returns:
        Tuple of (count updated, message)
    """
    records = (
        session.query(AudioQualityReview)
        .filter(AudioQualityReview.s3_staging_url == old_staging_url)
        .all()
    )

    if not records:
        return 0, "No matching database records found"

    if dry_run:
        return len(records), f"Would update {len(records)} database records"

    for record in records:
        record.s3_staging_url = new_staging_url
        record.s3_staging_manifest_url = new_manifest_url

    session.commit()
    return len(records), f"Updated {len(records)} database records"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate staging audio files to new path structure"
    )
    parser.add_argument(
        "--agent",
        type=str,
        default="vieversys",
        help="Agent name to migrate (default: vieversys)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--delete-old",
        action="store_true",
        help="Delete old files after successful migration",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="src/wordfreq/data/linguistics.sqlite",
        help="Path to the database file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files to migrate (for testing)",
    )
    args = parser.parse_args()

    print(f"Staging audio path migration")
    print(f"Agent: {args.agent}")
    print(f"Dry run: {args.dry_run}")
    print(f"Delete old: {args.delete_old}")
    print()

    # Initialize S3 uploader
    try:
        s3_uploader = S3AudioUploader()
    except Exception as e:
        print(f"Error: Could not initialize S3 uploader: {e}")
        sys.exit(1)

    # Create database session
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)
    session = create_backend_session(config)

    try:
        # List old format files
        print(f"Scanning for old format files in staging/{args.agent}/...")
        old_files = list_old_format_files(s3_uploader, args.agent)
        print(f"Found {len(old_files)} files to migrate")

        if args.limit:
            old_files = old_files[: args.limit]
            print(f"Limiting to {args.limit} files")

        if not old_files:
            print("Nothing to migrate!")
            return

        print()

        success_count = 0
        failure_count = 0
        db_update_count = 0

        for audio_key, manifest_key in old_files:
            # Get old URL for database lookup
            old_staging_url = s3_uploader.get_cdn_url(audio_key)

            # Migrate the file
            success, message, new_audio_url, new_manifest_url = migrate_file(
                s3_uploader,
                audio_key,
                manifest_key,
                args.agent,
                dry_run=args.dry_run,
                delete_old=args.delete_old,
            )

            print(f"  {message}")

            if success and new_audio_url and new_manifest_url:
                success_count += 1

                # Update database
                count, db_message = update_database_urls(
                    session,
                    old_staging_url,
                    new_audio_url,
                    new_manifest_url,
                    dry_run=args.dry_run,
                )
                if count > 0:
                    print(f"    {db_message}")
                    db_update_count += count
            else:
                failure_count += 1

        print()
        print(f"Migration complete:")
        print(f"  Files migrated: {success_count}")
        print(f"  Files failed: {failure_count}")
        print(f"  Database records updated: {db_update_count}")

        if args.dry_run:
            print()
            print("This was a dry run. No changes were made.")

    finally:
        session.close()


if __name__ == "__main__":
    main()
