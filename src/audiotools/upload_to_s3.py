#!/usr/bin/env python3
"""
Upload audio files to Digital Ocean Spaces with MD5-based filenames.

This script uploads audio files from the local wireword-audio repository to
Digital Ocean Spaces (S3-compatible storage) with MD5 hashes as filenames
for automatic cache invalidation.

Usage:
    # Upload all audio for Chinese, ash voice
    python upload_to_s3.py --language zh --voice ash

    # Upload all voices for Chinese
    python upload_to_s3.py --language zh --all-voices

    # Dry run (preview what would be uploaded)
    python upload_to_s3.py --language zh --voice ash --dry-run

    # Upload specific voices
    python upload_to_s3.py --language zh --voice ash --voice alloy

Environment Variables:
    DO_SPACES_ENDPOINT  - Digital Ocean Spaces endpoint (default: https://nyc3.digitaloceanspaces.com)
    DO_SPACES_KEY       - Digital Ocean Spaces access key (required)
    DO_SPACES_SECRET    - Digital Ocean Spaces secret key (required)
    DO_SPACES_BUCKET    - Bucket name (default: trakaido-audio)

Example:
    export DO_SPACES_KEY="your-access-key"
    export DO_SPACES_SECRET="your-secret-key"
    python upload_to_s3.py --language zh --all-voices
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("Error: boto3 not installed. Run: pip install boto3")
    sys.exit(1)

# Supported languages (audio directories use language codes directly, e.g., 'lt', 'zh')
SUPPORTED_LANGUAGES = ["zh", "lt", "ko", "fr", "de", "es", "pt", "sw", "vi"]

# Base directory for local audio files
AUDIO_BASE_DIR = Path.home() / "repo/wireword-audio/trakaido"


class S3AudioUploader:
    """Upload audio files to Digital Ocean Spaces with MD5-based filenames."""

    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket_name: str):
        """
        Initialize S3 client.

        Args:
            endpoint_url: e.g., "https://nyc3.digitaloceanspaces.com"
            access_key: Digital Ocean Spaces access key
            secret_key: Digital Ocean Spaces secret key
            bucket_name: e.g., "trakaido-audio"
        """
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self.bucket_name = bucket_name
        self.uploaded_count = 0
        self.skipped_count = 0
        self.error_count = 0

    def upload_file(
        self, local_path: Path, s3_key: str, md5_hash: str, dry_run: bool = False
    ) -> bool:
        """
        Upload a single file to S3.

        Args:
            local_path: Path to local file
            s3_key: S3 key (e.g., "zh/ash/ab4d3513...mp3")
            md5_hash: Expected MD5 hash
            dry_run: If True, don't actually upload

        Returns:
            True if uploaded, False if skipped or error
        """
        # Check if file already exists in S3
        try:
            response = self.s3.head_object(Bucket=self.bucket_name, Key=s3_key)
            # File exists - check if MD5 matches
            existing_etag = response["ETag"].strip('"')
            if existing_etag == md5_hash:
                print(f"  ⏭️  Skip (already exists): {s3_key}")
                self.skipped_count += 1
                return False
            else:
                print(f"  ⚠️  MD5 mismatch for {s3_key} - re-uploading")
        except ClientError as e:
            if e.response["Error"]["Code"] != "404":
                print(f"  ❌ Error checking {s3_key}: {e}")
                self.error_count += 1
                return False
            # File doesn't exist - proceed with upload

        if dry_run:
            print(f"  [DRY RUN] Would upload: {s3_key}")
            return True

        # Upload file
        try:
            extra_args = {
                "ContentType": "audio/mpeg",
                "ACL": "public-read",  # Make files publicly accessible
                "CacheControl": "public, max-age=31536000, immutable",  # Cache for 1 year
            }

            self.s3.upload_file(str(local_path), self.bucket_name, s3_key, ExtraArgs=extra_args)

            print(f"  ✅ Uploaded: {s3_key}")
            self.uploaded_count += 1
            return True

        except Exception as e:
            print(f"  ❌ Error uploading {s3_key}: {e}")
            self.error_count += 1
            return False

    def upload_from_manifest(
        self, manifest_path: Path, language: str, voice: str, dry_run: bool = False
    ):
        """
        Upload all files listed in a manifest.

        Args:
            manifest_path: Path to audio_manifest.json
            language: Language code (e.g., "zh")
            voice: Voice name (e.g., "ash")
            dry_run: If True, don't actually upload
        """
        print(f"\n📂 Processing manifest: {manifest_path}")

        if not manifest_path.exists():
            print(f"  ❌ Manifest not found: {manifest_path}")
            return

        # Load manifest
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as e:
            print(f"  ❌ Invalid JSON in manifest: {e}")
            return

        files = manifest.get("files", {})

        if not files:
            print(f"  ⚠️  No files in manifest")
            return

        print(f"  Found {len(files)} files in manifest")

        # Process each file
        for filename, metadata in files.items():
            local_path = manifest_path.parent / filename

            if not local_path.exists():
                print(f"  ⚠️  Local file not found: {local_path}")
                continue

            # Get MD5 from manifest
            md5_hash = metadata.get("md5")
            if not md5_hash:
                print(f"  ⚠️  No MD5 hash in manifest for {filename}")
                continue

            # Verify MD5 hash matches actual file
            actual_md5 = hashlib.md5(local_path.read_bytes()).hexdigest()
            if actual_md5 != md5_hash:
                print(f"  ⚠️  MD5 mismatch for {filename}")
                print(f"      Manifest: {md5_hash}")
                print(f"      Actual:   {actual_md5}")
                print(f"      Using actual MD5 from file")
                md5_hash = actual_md5

            # S3 key uses MD5 as filename (not GUID)
            s3_key = f"{language}/{voice}/{md5_hash}.mp3"

            # Upload
            self.upload_file(local_path, s3_key, md5_hash, dry_run)

    def print_summary(self):
        """Print upload summary."""
        print(f"\n{'='*60}")
        print(f"Upload Summary:")
        print(f"  ✅ Uploaded: {self.uploaded_count}")
        print(f"  ⏭️  Skipped:  {self.skipped_count}")
        print(f"  ❌ Errors:   {self.error_count}")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="Upload audio files to Digital Ocean Spaces",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload Chinese audio for ash voice
  python upload_to_s3.py --language zh --voice ash

  # Upload all voices for Chinese
  python upload_to_s3.py --language zh --all-voices

  # Dry run (preview without uploading)
  python upload_to_s3.py --language zh --voice ash --dry-run

Environment Variables:
  DO_SPACES_KEY       Digital Ocean Spaces access key (required)
  DO_SPACES_SECRET    Digital Ocean Spaces secret key (required)
  DO_SPACES_ENDPOINT  Endpoint URL (default: https://nyc3.digitaloceanspaces.com)
  DO_SPACES_BUCKET    Bucket name (default: trakaido-audio)
        """,
    )
    parser.add_argument("--language", required=True, help="Language code (zh, lt, ko, fr)")
    parser.add_argument(
        "--voice",
        action="append",
        help="Voice name (ash, alloy, echo, etc.) - can specify multiple times",
    )
    parser.add_argument("--all-voices", action="store_true", help="Upload all voices")
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    args = parser.parse_args()

    # Validate arguments
    if not args.voice and not args.all_voices:
        print("Error: Must specify --voice or --all-voices")
        sys.exit(1)

    if args.language not in SUPPORTED_LANGUAGES:
        print(f"Error: Unsupported language '{args.language}'")
        print(f"Supported: {', '.join(SUPPORTED_LANGUAGES)}")
        sys.exit(1)

    # Get credentials from environment
    endpoint_url = os.getenv("DO_SPACES_ENDPOINT", "https://nyc3.digitaloceanspaces.com")
    access_key = os.getenv("DO_SPACES_KEY")
    secret_key = os.getenv("DO_SPACES_SECRET")
    bucket_name = os.getenv("DO_SPACES_BUCKET", "trakaido-audio")

    if not access_key or not secret_key:
        print("Error: Set DO_SPACES_KEY and DO_SPACES_SECRET environment variables")
        print("\nExample:")
        print('  export DO_SPACES_KEY="your-access-key"')
        print('  export DO_SPACES_SECRET="your-secret-key"')
        sys.exit(1)

    # Initialize uploader
    print(f"Connecting to {endpoint_url}")
    print(f"Bucket: {bucket_name}")
    if args.dry_run:
        print("DRY RUN MODE - No files will be uploaded")

    uploader = S3AudioUploader(endpoint_url, access_key, secret_key, bucket_name)

    # Get language directory (uses language code directly, e.g., 'lt', 'zh')
    lang_dir = AUDIO_BASE_DIR / args.language

    if not lang_dir.exists():
        print(f"Error: Language directory not found: {lang_dir}")
        sys.exit(1)

    # Determine which voices to upload
    if args.all_voices:
        voices = [d.name for d in lang_dir.iterdir() if d.is_dir()]
        if not voices:
            print(f"Error: No voice directories found in {lang_dir}")
            sys.exit(1)
        print(f"Found voices: {', '.join(voices)}")
    else:
        voices = args.voice

    # Upload each voice
    for voice in voices:
        voice_dir = lang_dir / voice
        if not voice_dir.exists():
            print(f"⚠️  Voice directory not found: {voice_dir}")
            continue

        manifest_path = voice_dir / "audio_manifest.json"
        uploader.upload_from_manifest(manifest_path, args.language, voice, args.dry_run)

    # Print summary
    uploader.print_summary()


if __name__ == "__main__":
    main()
