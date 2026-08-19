#!/usr/bin/env python3
"""
S3 staging/production operations for generated audio.

These are the S3-side building blocks the audio agents (vieversys, strazdas,
gandras) used to carry as private methods: uploading a generated file plus its
manifest to staging, promoting it to production, and reading staged artifacts
back out again. None of it touches the database, so it lives here rather than
in an agent.

Every function takes the uploader as its first argument instead of reaching
for a module-level singleton, so callers keep control of credentials. The
parameter is typed as a Protocol covering only what each helper actually
uses, so an S3AudioUploader satisfies it and a test double needs no
subclassing.

Key layout is owned by clients.audio.s3_uploader -- use get_staging_audio_key,
get_staging_manifest_key, and get_prod_audio_key rather than formatting the
paths by hand, so a layout change lands in one place.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

from clients.audio.s3_uploader import get_staging_prefix

logger = logging.getLogger(__name__)


class SupportsS3(Protocol):
    """The slice of S3AudioUploader these helpers actually use.

    Typing against the raw client plus bucket name -- rather than the concrete
    S3AudioUploader -- keeps the read/list helpers honest about their
    dependencies and lets tests pass a double without subclassing.
    """

    @property
    def s3(self) -> Any: ...

    # Optional to match S3AudioUploader, whose bucket_name is typed from an
    # Optional constructor argument. In practice it always resolves to a str
    # via DEFAULT_BUCKET; boto3 would reject None at call time either way.
    @property
    def bucket_name(self) -> Optional[str]: ...


class SupportsUpload(SupportsS3, Protocol):
    """Adds the higher-level upload methods, for the write helpers."""

    def upload_to_staging(
        self,
        audio_path: Path,
        manifest_data: Dict[str, Any],
        language_code: str,
        voice_name: str,
        check_existing: bool = ...,
    ) -> Tuple[bool, str, str, str]: ...

    def upload_to_production(
        self,
        audio_path: Path,
        md5_hash: str,
        language_code: str,
        voice_name: str,
        check_existing: bool = ...,
    ) -> Tuple[bool, str]: ...


# Manifests sit beside their audio file, same key with a different suffix.
AUDIO_SUFFIX = ".mp3"
MANIFEST_SUFFIX = ".manifest"


def upload_to_staging(
    uploader: SupportsUpload,
    audio_path: Path,
    manifest_data: Dict[str, Any],
    language_code: str,
    voice_path_name: str,
    md5_hash: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """
    Upload an audio file and its manifest to staging/{language}/{voice}/.

    Args:
        uploader: Configured S3AudioUploader
        audio_path: Path to the local audio file
        manifest_data: Manifest dictionary to store alongside the audio
        language_code: Language code (e.g. "lt", "zh")
        voice_path_name: Voice path name (e.g. "ruta", "jonas")
        md5_hash: Precomputed MD5 of the audio bytes; computed from the file
            when omitted

    Returns:
        Tuple of (success, audio_url, manifest_url). URLs are empty on failure.
    """
    if md5_hash is None:
        md5_hash = hashlib.md5(audio_path.read_bytes()).hexdigest()

    success, audio_url, manifest_url, _ = uploader.upload_to_staging(
        audio_path=audio_path,
        manifest_data=manifest_data,
        language_code=language_code,
        voice_name=voice_path_name,
    )
    return success, audio_url, manifest_url


def upload_to_production(
    uploader: SupportsUpload,
    audio_path: Path,
    md5_hash: str,
    language_code: str,
    voice_path_name: str,
) -> Tuple[bool, str]:
    """
    Upload an audio file straight to prod/{language}/{voice}/.

    Args:
        uploader: Configured S3AudioUploader
        audio_path: Path to the local audio file
        md5_hash: MD5 of the audio bytes; names the object
        language_code: Language code (e.g. "lt", "zh")
        voice_path_name: Voice path name (e.g. "ruta", "jonas")

    Returns:
        Tuple of (success, prod_url). URL is empty on failure.
    """
    return uploader.upload_to_production(
        audio_path=audio_path,
        md5_hash=md5_hash,
        language_code=language_code,
        voice_name=voice_path_name,
    )


def staging_manifest_prefix(
    language_code: Optional[str] = None,
    voice_name: Optional[str] = None,
    agent_filter: Optional[str] = None,
) -> str:
    """
    Build the S3 prefix to scan for staged manifests.

    Supports the current staging/{language}/{voice}/ layout and the legacy
    staging/{agent}/ layout. Narrowest available filter wins.
    """
    base = get_staging_prefix()

    if language_code and voice_name:
        return f"{base}/{language_code}/{voice_name}/"
    if language_code:
        return f"{base}/{language_code}/"
    if agent_filter:
        return f"{base}/{agent_filter}/"
    return f"{base}/"


def list_staging_manifests(
    uploader: SupportsS3,
    language_code: Optional[str] = None,
    voice_name: Optional[str] = None,
    agent_filter: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """
    List staged manifests, paging through the bucket.

    Args:
        uploader: Configured S3AudioUploader
        language_code: Restrict to one language
        voice_name: Restrict to one voice (requires language_code to apply)
        agent_filter: Restrict to one agent, for the legacy layout
        limit: Stop after this many manifests

    Returns:
        List of (audio_key, manifest_key) tuples.

    Raises:
        Exception: propagated from the S3 client, so a credentials or
            connectivity failure is not mistaken for an empty bucket.
    """
    prefix = staging_manifest_prefix(language_code, voice_name, agent_filter)
    logger.info(f"Listing manifests with prefix: {prefix}")

    manifests: List[Tuple[str, str]] = []
    paginator = uploader.s3.get_paginator("list_objects_v2")

    try:
        for page in paginator.paginate(Bucket=uploader.bucket_name, Prefix=prefix):
            if "Contents" not in page:
                continue

            for obj in page["Contents"]:
                key = obj["Key"]
                if not key.endswith(MANIFEST_SUFFIX):
                    continue

                audio_key = key[: -len(MANIFEST_SUFFIX)] + AUDIO_SUFFIX
                manifests.append((audio_key, key))

                if limit and len(manifests) >= limit:
                    return manifests

    except Exception as e:
        logger.error(f"Error listing S3 objects: {e}")
        raise

    logger.info(f"Found {len(manifests)} manifest files")
    return manifests


def download_manifest(
    uploader: SupportsS3,
    manifest_key: str,
) -> Optional[Dict[str, Any]]:
    """
    Download and parse one manifest.

    Returns the parsed dict, or None if the object is missing or unparseable.
    """
    try:
        response = uploader.s3.get_object(Bucket=uploader.bucket_name, Key=manifest_key)
        content = response["Body"].read().decode("utf-8")
        result: Dict[str, Any] = json.loads(content)
        return result
    except Exception as e:
        logger.error(f"Error downloading manifest {manifest_key}: {e}")
        return None


def download_audio_file(
    uploader: SupportsS3,
    audio_key: str,
    output_path: Path,
) -> Tuple[bool, Optional[str]]:
    """
    Download an audio object and return its MD5.

    Creates the parent directory if needed. The hash is computed from the
    bytes that actually landed on disk, so it doubles as a transfer check.

    Returns:
        Tuple of (success, md5_hash). The hash is None on failure.
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        uploader.s3.download_file(uploader.bucket_name, audio_key, str(output_path))

        md5_hash = hashlib.md5(output_path.read_bytes()).hexdigest()
        logger.info(f"Downloaded {audio_key} to {output_path} (MD5: {md5_hash})")
        return True, md5_hash
    except Exception as e:
        logger.error(f"Error downloading {audio_key}: {e}")
        return False, None
