#!/usr/bin/env python3
"""
WireWord manifest generator.

Generates wireword_manifest_v2.json files that describe available data files
for a language, including MD5 checksums for cache validation.
"""

import glob
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from langtools.manifest_grammar import get_manifest_conjugation_config
from storage.translation_helpers import LANGUAGE_NAMES
from exports.wireword.readings import get_manifest_reading_config

# Configure logging
logger = logging.getLogger(__name__)

# Voice names per language for manifest generation
# Maps language code to list of path_name strings (used in audio URLs).
# Keyed on the exact code, dialects included: a dialect's audio is recorded from
# its own text in its own accent, so zh-tw stays absent until Taiwanese voices
# exist rather than advertising zh's mainland recordings of Simplified text.
LANGUAGE_VOICE_NAMES: Dict[str, List[str]] = {
    "lt": ["ruta", "jonas"],
    "zh": ["meiling", "zhiyuan"],
    "fr": ["marie", "pierre"],
    "ja": ["sakura", "haruto"],  # Placeholder names for Japanese
    "ko": ["yuna", "minho"],  # Placeholder names for Korean
}


def _slugify_language_name(display_name: str) -> str:
    """Lowercase a display name into a manifest-safe identifier.

    "Lithuanian" stays "lithuanian"; the parenthesized dialect names become
    underscore-joined words ("Chinese (Taiwan)" -> "chinese_taiwan").
    """
    return "_".join(re.findall(r"[a-z0-9]+", display_name.lower()))


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
    include_unreviewed_audio: bool = False,
    source_language: str = "en",
    cdn_base: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Generate wireword_manifest_v2.json for the exported files.

    Discovers ``wireword_levels_*.json`` files in *wireword_dir* and produces
    one word_files entry per level-range file.

    Args:
        wireword_dir: The wireword output directory containing the exported files
        language: Language code (e.g., "lt", "zh", "zh-tw", "fr")
        include_unreviewed_audio: If True, set audio_prefix to staging path
        source_language: Source language code (default: "en"). When not "en", adds
            source_language metadata to the manifest.
        cdn_base: Optional CDN base URL (e.g. "https://wireword.trakaido.com").
            When set, non-manifest filenames in the manifest use the file's MD5
            hash so they can be served as immutable cache objects.

    Returns:
        Tuple of (success flag, manifest path)
    """
    manifest_path = os.path.join(wireword_dir, "wireword_manifest_v2.json")

    # Determine language name and code.  A dialect is an ordinary language here:
    # zh-tw is its own code with its own display name, not a variant flag on zh.
    language_name = _slugify_language_name(LANGUAGE_NAMES.get(language, language))
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
    # Key ordering matters for client compatibility: source_language fields
    # must appear between generated_at and config.
    manifest: Dict[str, Any] = {
        "version": 1,
        "language": language_name,
        "language_code": language_code,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # Add source language metadata between generated_at and config
    if source_language != "en":
        source_lang_name = _slugify_language_name(
            LANGUAGE_NAMES.get(source_language, source_language)
        )
        manifest["source_language"] = source_lang_name
        manifest["source_language_code"] = source_language
    config: Dict[str, Any] = {
        "audio_prefix": audio_prefix,
        "available_voices": available_voices,
        "default_voice": default_voice,
    }
    if cdn_base:
        config["cdn_base"] = cdn_base
    manifest["config"] = config
    reading_manifest_config = get_manifest_reading_config(language)
    if reading_manifest_config:
        manifest["config"]["reading"] = reading_manifest_config
    conjugation_manifest_config = get_manifest_conjugation_config(language)
    if conjugation_manifest_config:
        manifest["config"]["grammar"] = {
            "conjugation": conjugation_manifest_config,
        }
    manifest["word_files"] = []
    manifest["sentence_files"] = []
    manifest["auxiliary_files"] = []

    # Process word files – discover wireword_levels_*.json files
    level_file_pattern = os.path.join(wireword_dir, "wireword_levels_*.json")

    # Sort numerically by start level so manifest entries are monotonic by
    # difficulty (lexicographic sort would put e.g. 11_15 before 1_5).
    def _level_sort_key(path: str) -> Tuple[int, int]:
        m = re.search(r"wireword_levels_(\d+)_(\d+)\.json", path)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)

    level_files = sorted(glob.glob(level_file_pattern), key=_level_sort_key)

    for filepath in level_files:
        disk_filename = os.path.basename(filepath)
        match = re.match(r"wireword_levels_(\d+)_(\d+)\.json", disk_filename)
        if not match:
            continue
        start_level = int(match.group(1))
        end_level = int(match.group(2))

        file_id = f"levels_{start_level}_{end_level}"
        display_name = f"Levels {start_level}-{end_level}"
        file_md5 = calculate_file_md5(filepath)

        # When cdn_base is set, use the MD5 hash as the manifest filename
        # so the CDN can serve the file as an immutable object.
        manifest_filename = f"{file_md5}.json" if cdn_base else disk_filename

        file_stats = get_word_file_stats(filepath)
        file_entry: Dict[str, Any] = {
            "id": file_id,
            "filename": manifest_filename,
            "display_name": display_name,
            "type": "words",
            "md5": file_md5,
            "levels": list(range(start_level, end_level + 1)),
            "required": True,
        }
        if file_stats.get("count"):
            file_entry["word_count"] = file_stats["count"]
        if file_stats.get("groups"):
            file_entry["groups"] = file_stats["groups"]

        manifest["word_files"].append(file_entry)

    # Process sentence files
    sentences_path = os.path.join(wireword_dir, "wireword_sentences.json")
    if os.path.exists(sentences_path):
        sentence_stats = get_sentence_file_stats(sentences_path)
        sentences_md5 = calculate_file_md5(sentences_path)
        sentences_manifest_filename = (
            f"{sentences_md5}.json" if cdn_base else "wireword_sentences.json"
        )
        sentence_entry: Dict[str, Any] = {
            "id": "sentences",
            "filename": sentences_manifest_filename,
            "display_name": "Practice Sentences",
            "description": "Sentences for context-based learning",
            "type": "sentences",
            "md5": sentences_md5,
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

        conversations_md5 = calculate_file_md5(conversations_path)
        conversations_manifest_filename = (
            f"{conversations_md5}.jsonl" if cdn_base else "wireword_conversations.jsonl"
        )
        conversation_entry: Dict[str, Any] = {
            "id": "conversations",
            "filename": conversations_manifest_filename,
            "display_name": "Conversations",
            "description": "Practice conversations for dialogue-based learning",
            "type": "conversations",
            "md5": conversations_md5,
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
