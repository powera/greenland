#!/usr/bin/python3
"""Audio manifest generator for tracking audio file metadata."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def generate_manifest(
    audio_file_path: Path,
    agent: str,
    voice_name: str,
    language_code: str,
    expected_text: str,
    guid: Optional[str] = None,
    sentence_id: Optional[int] = None,
    grammatical_form: Optional[str] = None,
    generation_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a manifest file for an audio file.

    Args:
        audio_file_path: Path to the audio file
        agent: Agent that generated the audio (e.g., "vieversys", "strazdas")
        voice_name: Voice name (e.g., "ash", "alloy", "Ona")
        language_code: Language code (e.g., "lt", "zh")
        expected_text: The text that should be spoken in the audio
        guid: Optional GUID for lemma audio (e.g., "N01_001")
        sentence_id: Optional sentence ID for sentence audio
        grammatical_form: Optional grammatical form for derivative forms (not currently used)
        generation_params: Optional dict of generation parameters (model, speed, etc.)

    Returns:
        Dictionary containing manifest data
    """
    if not audio_file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

    # Calculate MD5 hash
    audio_bytes = audio_file_path.read_bytes()
    md5_hash = hashlib.md5(audio_bytes).hexdigest()

    # Get file size
    file_size = len(audio_bytes)

    # Build manifest
    manifest: Dict[str, Any] = {
        "md5": md5_hash,
        "agent": agent,
        "voice_name": voice_name,
        "language_code": language_code,
        "expected_text": expected_text,
        "guid": guid,
        "sentence_id": sentence_id,
        "grammatical_form": grammatical_form,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "file_size_bytes": file_size,
    }

    # Add generation parameters if provided
    if generation_params:
        manifest["generation_params"] = generation_params

    return manifest


def save_manifest(manifest: Dict[str, Any], output_path: Path) -> None:
    """
    Save manifest to a JSON file.

    Args:
        manifest: Manifest data dictionary
        output_path: Path where manifest should be saved
    """
    output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def create_and_save_manifest(
    audio_file_path: Path,
    manifest_output_path: Path,
    agent: str,
    voice_name: str,
    language_code: str,
    expected_text: str,
    guid: Optional[str] = None,
    sentence_id: Optional[int] = None,
    grammatical_form: Optional[str] = None,
    generation_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate and save a manifest file.

    Convenience function that combines generate_manifest and save_manifest.

    Args:
        audio_file_path: Path to the audio file
        manifest_output_path: Path where manifest should be saved
        agent: Agent that generated the audio
        voice_name: Voice name
        language_code: Language code
        expected_text: The text that should be spoken
        guid: Optional GUID for lemma audio
        sentence_id: Optional sentence ID for sentence audio
        grammatical_form: Optional grammatical form
        generation_params: Optional generation parameters

    Returns:
        The manifest data that was saved
    """
    manifest = generate_manifest(
        audio_file_path=audio_file_path,
        agent=agent,
        voice_name=voice_name,
        language_code=language_code,
        expected_text=expected_text,
        guid=guid,
        sentence_id=sentence_id,
        grammatical_form=grammatical_form,
        generation_params=generation_params,
    )

    save_manifest(manifest, manifest_output_path)

    return manifest
