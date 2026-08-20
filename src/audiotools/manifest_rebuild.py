#!/usr/bin/env python3
"""
Directory-scanning manifest generation.

Builds an audio_manifest.json for a directory of already-generated MP3s by
reading the files themselves -- no database involved. This is the rebuild
path: it recovers a manifest from whatever is on disk, deriving each entry's
GUID and text from the filename convention.

Distinct from clients.audio.manifest.generate_manifest, which builds a
manifest for a single freshly generated file from the metadata the caller
already holds. Use that one when generating; use this one when reconstructing
after the fact.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "audio_manifest.json"

# Generated audio is named "{GUID}_{text}.mp3"; the split is on the first
# underscore only, since the text itself may contain underscores.
FILENAME_SEPARATOR = "_"
UNKNOWN_GUID = "UNKNOWN"


def build_manifest_for_directory(
    voice_dir: Path,
    language_code: str,
    voice_name: str,
) -> Dict[str, Any]:
    """
    Scan a voice directory and build its manifest contents.

    Args:
        voice_dir: Directory holding the generated .mp3 files
        language_code: Language code recorded in the manifest
        voice_name: Voice name recorded in the manifest

    Returns:
        The manifest dictionary, with one "files" entry per MP3 found.

    Raises:
        ValueError: If voice_dir does not exist.
    """
    if not voice_dir.exists():
        raise ValueError(f"Voice directory not found: {voice_dir}")

    manifest: Dict[str, Any] = {
        "language": language_code,
        "voice": voice_name,
        "files": {},
    }

    for mp3_file in sorted(voice_dir.glob("*.mp3")):
        md5_hash = hashlib.md5(mp3_file.read_bytes()).hexdigest()

        # Filename format: {GUID}_{text}.mp3 . Text is best-effort -- it is
        # recovered from the filename, so it has already lost anything the
        # sanitizer stripped when the file was written.
        guid, separator, text = mp3_file.stem.partition(FILENAME_SEPARATOR)
        if not guid:
            guid = UNKNOWN_GUID
        if not separator:
            text = guid

        manifest["files"][mp3_file.name] = {
            "guid": guid,
            "text": text,
            "md5": md5_hash,
            "grammatical_form": None,
        }

    return manifest


def write_manifest_for_directory(
    voice_dir: Path,
    language_code: str,
    voice_name: str,
) -> Path:
    """
    Build a directory's manifest and write it as audio_manifest.json.

    Args:
        voice_dir: Directory holding the generated .mp3 files
        language_code: Language code recorded in the manifest
        voice_name: Voice name recorded in the manifest

    Returns:
        Path to the manifest that was written.

    Raises:
        ValueError: If voice_dir does not exist.
    """
    manifest = build_manifest_for_directory(voice_dir, language_code, voice_name)

    manifest_path = voice_dir / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    logger.info(f"Generated manifest: {manifest_path} ({len(manifest['files'])} files)")
    return manifest_path
