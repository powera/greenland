#!/usr/bin/python3
"""S3/Digital Ocean Spaces uploader for audio files."""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from types import ModuleType
from typing import Optional as OptionalType, Type

boto3: OptionalType[ModuleType]
ClientError: Type[BaseException]

try:
    import boto3 as _boto3  # type: ignore[no-redef]
    from botocore.exceptions import ClientError as _ClientError

    boto3 = _boto3
    ClientError = _ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

import constants

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_ENDPOINT = "https://sfo3.digitaloceanspaces.com"
DEFAULT_BUCKET = "trakaido-audio"


def get_staging_prefix() -> str:
    """Get the staging directory prefix based on current backend.

    Returns:
        "staging-postgres" if using PostgreSQL backend, "staging" otherwise
    """
    if os.environ.get("STORAGE_BACKEND") == "postgres":
        return "staging-postgres"
    return "staging"


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

    def _load_keys_from_file(self) -> None:
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
                if hasattr(e, "response") and e.response["Error"]["Code"] != "404":
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

            self.s3.upload_file(str(local_path), self.bucket_name, s3_key, ExtraArgs=extra_args)

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
        assert self.endpoint_url is not None, "endpoint_url must be set"
        region = self.endpoint_url.split("//")[1].split(".")[0]  # Extract "sfo3" from URL
        return f"https://{self.bucket_name}.{region}.cdn.digitaloceanspaces.com/{s3_key}"

    def upload_to_staging(
        self,
        audio_path: Path,
        manifest_data: Dict[str, Any],
        agent: str,
        check_existing: bool = True,
    ) -> Tuple[bool, str, str, str]:
        """
        Upload audio file and manifest to staging/{agent}/ directory.

        Args:
            audio_path: Path to local audio file
            manifest_data: Manifest data dictionary
            agent: Agent name (e.g., "vieversys", "strazdas")
            check_existing: If True, skip if file with same MD5 exists

        Returns:
            Tuple of (success: bool, audio_url: str, manifest_url: str, md5_hash: str)
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return False, "", "", ""

        # Calculate MD5 hash
        md5_hash = hashlib.md5(audio_path.read_bytes()).hexdigest()

        # S3 keys for staging (use staging-postgres prefix when in postgres mode)
        staging_prefix = get_staging_prefix()
        audio_key = f"{staging_prefix}/{agent}/{md5_hash}.mp3"
        manifest_key = f"{staging_prefix}/{agent}/{md5_hash}.manifest"

        # Check if audio file already exists
        if check_existing:
            try:
                response = self.s3.head_object(Bucket=self.bucket_name, Key=audio_key)
                existing_etag = response["ETag"].strip('"')
                if existing_etag == md5_hash:
                    logger.info(f"Audio already exists in staging: {audio_key}")
                    audio_url = self.get_cdn_url(audio_key)
                    manifest_url = self.get_cdn_url(manifest_key)
                    return True, audio_url, manifest_url, md5_hash
            except ClientError as e:
                if hasattr(e, "response") and e.response["Error"]["Code"] != "404":
                    logger.error(f"Error checking existing file: {e}")
                    return False, "", "", md5_hash

        try:
            # Upload audio file
            audio_extra_args = {
                "ContentType": "audio/mpeg",
                "ACL": "public-read",
                "CacheControl": "public, max-age=3600",  # Cache for 1 hour (staging)
            }
            self.s3.upload_file(
                str(audio_path), self.bucket_name, audio_key, ExtraArgs=audio_extra_args
            )
            logger.info(f"Uploaded audio to staging: {audio_key}")

            # Upload manifest file
            manifest_json = json.dumps(manifest_data, indent=2, ensure_ascii=False)
            manifest_extra_args = {
                "ContentType": "application/json",
                "ACL": "public-read",
                "CacheControl": "public, max-age=3600",
            }
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=manifest_key,
                Body=manifest_json.encode("utf-8"),
                **manifest_extra_args,
            )
            logger.info(f"Uploaded manifest to staging: {manifest_key}")

            audio_url = self.get_cdn_url(audio_key)
            manifest_url = self.get_cdn_url(manifest_key)
            return True, audio_url, manifest_url, md5_hash

        except Exception as e:
            logger.error(f"Error uploading to staging: {e}")
            return False, "", "", md5_hash

    def move_to_production(self, md5_hash: str, agent: str) -> Tuple[bool, str]:
        """
        Copy audio file from staging/{agent}/ to prod/.

        Does NOT copy the manifest file - only the audio file.

        Args:
            md5_hash: MD5 hash of the audio file
            agent: Agent name (e.g., "vieversys", "strazdas")

        Returns:
            Tuple of (success: bool, prod_url: str)
        """
        staging_prefix = get_staging_prefix()
        staging_key = f"{staging_prefix}/{agent}/{md5_hash}.mp3"
        prod_key = f"prod/{md5_hash}.mp3"

        try:
            # Copy from staging to prod
            copy_source = {"Bucket": self.bucket_name, "Key": staging_key}

            self.s3.copy_object(
                CopySource=copy_source,
                Bucket=self.bucket_name,
                Key=prod_key,
                ACL="public-read",
                ContentType="audio/mpeg",
                CacheControl="public, max-age=31536000, immutable",  # Cache for 1 year
                MetadataDirective="REPLACE",  # Use new metadata
            )

            logger.info(f"Moved to production: {staging_key} -> {prod_key}")
            prod_url = self.get_cdn_url(prod_key)
            return True, prod_url

        except ClientError as e:
            if hasattr(e, "response") and e.response["Error"]["Code"] == "NoSuchKey":
                logger.error(f"Staging file not found: {staging_key}")
            else:
                logger.error(f"Error moving to production: {e}")
            return False, ""
        except Exception as e:
            logger.error(f"Error moving to production: {e}")
            return False, ""

    def upload_to_production(
        self, audio_path: Path, md5_hash: str, check_existing: bool = True
    ) -> Tuple[bool, str]:
        """
        Upload audio file directly to prod/ directory.

        Args:
            audio_path: Path to local audio file
            md5_hash: MD5 hash of the audio file
            check_existing: If True, skip if file with same MD5 exists

        Returns:
            Tuple of (success: bool, prod_url: str)
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return False, ""

        prod_key = f"prod/{md5_hash}.mp3"

        # Check if file already exists
        if check_existing:
            try:
                response = self.s3.head_object(Bucket=self.bucket_name, Key=prod_key)
                existing_etag = response["ETag"].strip('"')
                if existing_etag == md5_hash:
                    logger.info(f"Audio already exists in production: {prod_key}")
                    prod_url = self.get_cdn_url(prod_key)
                    return True, prod_url
            except ClientError as e:
                if hasattr(e, "response") and e.response["Error"]["Code"] != "404":
                    logger.error(f"Error checking existing file: {e}")
                    return False, ""

        try:
            extra_args = {
                "ContentType": "audio/mpeg",
                "ACL": "public-read",
                "CacheControl": "public, max-age=31536000, immutable",  # Cache for 1 year
            }

            self.s3.upload_file(str(audio_path), self.bucket_name, prod_key, ExtraArgs=extra_args)

            logger.info(f"Uploaded to production: {prod_key}")
            prod_url = self.get_cdn_url(prod_key)
            return True, prod_url

        except Exception as e:
            logger.error(f"Error uploading to production: {e}")
            return False, ""


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
