#!/usr/bin/env python3
"""
WireWord manifest generator.

Generates wireword_manifest.json files that describe available data files
for a language, including MD5 checksums for cache validation.
"""

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from storage.translation_helpers import LANGUAGE_NAMES

# Configure logging
logger = logging.getLogger(__name__)

# Voice names per language for manifest generation
# Maps language code to list of path_name strings (used in audio URLs)
LANGUAGE_VOICE_NAMES: Dict[str, List[str]] = {
    "lt": ["ruta", "jonas"],
    "zh": ["meiling", "zhiyuan"],
    "fr": ["marie", "pierre"],
    "ko": ["yuna", "minho"],  # Placeholder names for Korean
}


def calculate_file_md5(filepath: str) -> str:
    """Calculate MD5 hash of a file's contents."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def get_word_file_stats(filepath: str) -> Dict[str, Any]:
    """Get statistics from a wireword JSON file (word count, levels, groups)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return {}

        levels: set[int] = set()
        groups: set[str] = set()

        for item in data:
            if isinstance(item, dict):
                if "level" in item and item["level"] is not None:
                    levels.add(item["level"])
                if "group" in item and item["group"]:
                    groups.add(item["group"])

        return {
            "count": len(data),
            "levels": sorted(levels),
            "groups": sorted(groups),
        }
    except (json.JSONDecodeError, IOError):
        return {}


def get_sentence_file_stats(filepath: str) -> Dict[str, Any]:
    """Get statistics from a wireword sentences JSON file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return {}

        min_level: Optional[int] = None
        max_level: Optional[int] = None

        for item in data:
            if isinstance(item, dict) and "minimum_level" in item:
                level = item["minimum_level"]
                if level is not None:
                    if min_level is None or level < min_level:
                        min_level = level
                    if max_level is None or level > max_level:
                        max_level = level

        return {
            "count": len(data),
            "min_level": min_level,
            "max_level": max_level,
        }
    except (json.JSONDecodeError, IOError):
        return {}


def generate_manifest(
    wireword_dir: str,
    language: str,
    simplified_chinese: bool = True,
    include_unreviewed_audio: bool = False,
) -> Tuple[bool, str]:
    """
    Generate wireword_manifest.json for the exported files.

    Args:
        wireword_dir: The wireword output directory containing the exported files
        language: Language code (e.g., "lt", "zh", "fr")
        simplified_chinese: For Chinese, whether simplified (True) or traditional (False)
        include_unreviewed_audio: If True, set audio_prefix to staging path

    Returns:
        Tuple of (success flag, manifest path)
    """
    manifest_path = os.path.join(wireword_dir, "wireword_manifest.json")

    # Determine language name and code
    if language == "zh" and not simplified_chinese:
        language_name = "chinese_traditional"
        language_code = "zh_Hant"
    else:
        language_name = LANGUAGE_NAMES.get(language, language).lower()
        language_code = language

    # Get available voices for this language
    available_voices = LANGUAGE_VOICE_NAMES.get(language, [])
    default_voice = available_voices[0] if available_voices else None

    # Determine audio prefix
    # When including unreviewed audio, point to staging path:
    # staging/{language}/{voice}/{md5}.mp3
    # The client constructs: {audio_prefix}/{language}/{voice}/{md5}.mp3
    if include_unreviewed_audio:
        from clients.audio.s3_uploader import get_staging_prefix

        staging_prefix = get_staging_prefix()
        audio_prefix = f"/{staging_prefix}"
    else:
        audio_prefix = "/prod"

    # Build manifest structure
    manifest: Dict[str, Any] = {
        "version": 1,
        "language": language_name,
        "language_code": language_code,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "audio_prefix": audio_prefix,
            "available_voices": available_voices,
            "default_voice": default_voice,
        },
        "word_files": [],
        "sentence_files": [],
        "auxiliary_files": [],
    }

    # Process word files
    word_files_info = [
        ("nouns", "wireword_nouns.json", "Nouns", "Words (nouns, adjectives, etc.)"),
        ("verbs", "wireword_verbs.json", "Verbs", "Verbs with conjugations"),
    ]

    for file_id, filename, display_name, description in word_files_info:
        filepath = os.path.join(wireword_dir, filename)
        if os.path.exists(filepath):
            file_stats = get_word_file_stats(filepath)
            file_entry: Dict[str, Any] = {
                "id": file_id,
                "filename": filename,
                "display_name": display_name,
                "description": description,
                "type": "words",
                "md5": calculate_file_md5(filepath),
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "required": True,
            }
            if file_stats.get("count"):
                file_entry["word_count"] = file_stats["count"]
            if file_stats.get("levels"):
                file_entry["levels"] = file_stats["levels"]
            if file_stats.get("groups"):
                file_entry["groups"] = file_stats["groups"]

            manifest["word_files"].append(file_entry)

    # Process sentence files
    sentences_path = os.path.join(wireword_dir, "wireword_sentences.json")
    if os.path.exists(sentences_path):
        sentence_stats = get_sentence_file_stats(sentences_path)
        sentence_entry: Dict[str, Any] = {
            "id": "sentences",
            "filename": "wireword_sentences.json",
            "display_name": "Practice Sentences",
            "description": "Sentences for context-based learning",
            "type": "sentences",
            "md5": calculate_file_md5(sentences_path),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "required": False,
        }
        if sentence_stats.get("count"):
            sentence_entry["sentence_count"] = sentence_stats["count"]
        if sentence_stats.get("min_level") is not None:
            sentence_entry["min_level"] = sentence_stats["min_level"]
        if sentence_stats.get("max_level") is not None:
            sentence_entry["max_level"] = sentence_stats["max_level"]

        manifest["sentence_files"].append(sentence_entry)

    # Process conversations file (JSONL format - auxiliary file)
    conversations_path = os.path.join(wireword_dir, "wireword_conversations.jsonl")
    if os.path.exists(conversations_path):
        # Count lines in JSONL file
        try:
            with open(conversations_path, "r", encoding="utf-8") as f:
                conversation_count = sum(1 for line in f if line.strip())
        except IOError:
            conversation_count = 0

        conversation_entry: Dict[str, Any] = {
            "id": "conversations",
            "filename": "wireword_conversations.jsonl",
            "display_name": "Conversations",
            "description": "Practice conversations for dialogue-based learning",
            "type": "conversations",
            "md5": calculate_file_md5(conversations_path),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "required": False,
            "conversation_count": conversation_count,
        }
        manifest["auxiliary_files"].append(conversation_entry)

    # Write manifest file
    try:
        os.makedirs(wireword_dir, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        logger.info(f"Generated manifest: {manifest_path}")
        return True, manifest_path
    except IOError as e:
        logger.error(f"Failed to write manifest: {e}")
        return False, ""
