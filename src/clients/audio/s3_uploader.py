#!/usr/bin/python3
"""S3/Digital Ocean Spaces uploader for audio files."""

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None

import constants

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_ENDPOINT = "https://sfo3.digitaloceanspaces.com"
DEFAULT_BUCKET = "trakaido-audio"


class S3AudioUploader:
    """Upload audio files to Digital Ocean Spaces with MD5-based filenames."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
    ):
        """
        Initialize S3 uploader.

        Args:
            endpoint_url: Digital Ocean Spaces endpoint (or from env DO_SPACES_ENDPOINT)
            access_key: Access key (or from env DO_SPACES_KEY or keys/digitalocean.key)
            secret_key: Secret key (or from env DO_SPACES_SECRET or keys/digitalocean.key)
            bucket_name: Bucket name (or from env DO_SPACES_BUCKET)
        """
        if boto3 is None:
            raise ImportError("boto3 not installed. Install with: pip install boto3")

        # Load credentials
        self.endpoint_url = endpoint_url or os.getenv("DO_SPACES_ENDPOINT", DEFAULT_ENDPOINT)
        self.bucket_name = bucket_name or os.getenv("DO_SPACES_BUCKET", DEFAULT_BUCKET)

        # Try to load keys from arguments, environment, or file
        self.access_key = access_key or os.getenv("DO_SPACES_KEY")
        self.secret_key = secret_key or os.getenv("DO_SPACES_SECRET")

        if not self.access_key or not self.secret_key:
            self._load_keys_from_file()

        if not self.access_key or not self.secret_key:
            raise ValueError(
                "Digital Ocean Spaces credentials not found. "
                "Set DO_SPACES_KEY and DO_SPACES_SECRET environment variables "
                "or create keys/digitalocean.key with access key on line 1 and secret on line 2"
            )

        # Initialize S3 client
        self.s3 = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )

        logger.info(f"Initialized S3 uploader for bucket: {self.bucket_name}")

    def _load_keys_from_file(self):
        """Load credentials from keys/digitalocean.key file."""
        key_file = Path(constants.KEY_DIR) / "digitalocean.key"
        if key_file.exists():
            try:
                lines = key_file.read_text().strip().split("\n")
                if len(lines) >= 2:
                    self.access_key = lines[0].strip()
                    self.secret_key = lines[1].strip()
                    logger.info(f"Loaded credentials from {key_file}")
            except Exception as e:
                logger.warning(f"Error reading key file {key_file}: {e}")

    def upload_file(
        self,
        local_path: Path,
        language_code: str,
        voice_name: str,
        check_existing: bool = True,
    ) -> Tuple[bool, str, str]:
        """
        Upload audio file to S3 with MD5-based filename.

        Args:
            local_path: Path to local audio file
            language_code: Language code (e.g., "lt", "zh")
            voice_name: Voice name (e.g., "ash", "alloy")
            check_existing: If True, skip if file with same MD5 exists

        Returns:
            Tuple of (success: bool, s3_key: str, md5_hash: str)
        """
        if not local_path.exists():
            logger.error(f"File not found: {local_path}")
            return False, "", ""

        # Calculate MD5 hash
        md5_hash = hashlib.md5(local_path.read_bytes()).hexdigest()

        # S3 key format: {language}/{voice}/{md5}.mp3
        s3_key = f"{language_code}/{voice_name}/{md5_hash}.mp3"

        # Check if file already exists
        if check_existing:
            try:
                response = self.s3.head_object(Bucket=self.bucket_name, Key=s3_key)
                existing_etag = response["ETag"].strip('"')
                if existing_etag == md5_hash:
                    logger.info(f"File already exists in S3: {s3_key}")
                    return True, s3_key, md5_hash
                else:
                    logger.warning(f"MD5 mismatch for existing file, re-uploading: {s3_key}")
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    logger.error(f"Error checking existing file: {e}")
                    return False, s3_key, md5_hash
                # File doesn't exist, proceed with upload

        # Upload file
        try:
            extra_args = {
                "ContentType": "audio/mpeg",
                "ACL": "public-read",  # Make publicly accessible
                "CacheControl": "public, max-age=31536000, immutable",  # Cache for 1 year
            }

            self.s3.upload_file(
                str(local_path), self.bucket_name, s3_key, ExtraArgs=extra_args
            )

            logger.info(f"Uploaded to S3: {s3_key}")
            return True, s3_key, md5_hash

        except Exception as e:
            logger.error(f"Error uploading to S3: {e}")
            return False, s3_key, md5_hash

    def get_cdn_url(self, s3_key: str) -> str:
        """
        Get CDN URL for an S3 key.

        Args:
            s3_key: S3 key (e.g., "lt/ash/abc123.mp3")

        Returns:
            Full CDN URL
        """
        # Extract bucket name from endpoint and construct CDN URL
        # Format: https://{bucket}.{region}.cdn.digitaloceanspaces.com/{key}
        region = self.endpoint_url.split("//")[1].split(".")[0]  # Extract "sfo3" from URL
        return f"https://{self.bucket_name}.{region}.cdn.digitaloceanspaces.com/{s3_key}"


# Create default uploader instance (lazy initialization)
_default_uploader: Optional[S3AudioUploader] = None


def get_uploader() -> S3AudioUploader:
    """Get or create the default S3 uploader instance."""
    global _default_uploader
    if _default_uploader is None:
        _default_uploader = S3AudioUploader()
    return _default_uploader


def upload_audio_file(
    local_path: Path,
    language_code: str,
    voice_name: str,
    check_existing: bool = True,
) -> Tuple[bool, str, str]:
    """
    Upload audio file to S3.

    Convenience function using default uploader.

    Args:
        local_path: Path to local audio file
        language_code: Language code (e.g., "lt", "zh")
        voice_name: Voice name (e.g., "ash", "alloy")
        check_existing: If True, skip if file with same MD5 exists

    Returns:
        Tuple of (success: bool, s3_key: str, md5_hash: str)
    """
    uploader = get_uploader()
    return uploader.upload_file(local_path, language_code, voice_name, check_existing)
