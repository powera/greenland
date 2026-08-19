#!/usr/bin/env python3
"""
Multi-language audio generation using OpenAI TTS API.

This script generates audio files for wireword data in multiple languages:
- Chinese (ZH)
- Korean (KO)
- French (FR)
- Lithuanian (LT)

The script uses OpenAI's TTS API to generate high-quality audio and stores
files in a local cache directory. Remote sync operations (S3 or server) are
marked as TODO for future implementation.

Usage:
    # Generate audio for all Chinese files in a directory
    python wireword_audio.py --language zh --file ../data/chinese

    # Generate audio for specific files
    python wireword_audio.py --language zh --file data/chinese/wireword_nouns.json data/chinese/wireword_verbs.json

    # Generate audio for Korean with specific voice
    python wireword_audio.py --language ko --file ../data/korean --voice alloy

    # Generate audio for French with default voices (ash, alloy, echo)
    python wireword_audio.py --language fr --file ../data/french --multi-voice

    # Test with first 5 words only
    python wireword_audio.py --language zh --file ../data/chinese --limit 5

    # Force regeneration of existing files
    python wireword_audio.py --language zh --file ../data/chinese --force

    # Rebuild manifest from existing audio files (directory)
    python wireword_audio.py --language zh --file ../data/chinese --rebuild-manifest

    # Rebuild manifest for specific files with multiple voices
    python wireword_audio.py --language zh --file data/chinese/wireword_nouns.json data/chinese/wireword_verbs.json --rebuild-manifest --multi-voice

Directory structure:
    /Users/powera/repo/wireword-audio/   # Separate repository (sibling to greenland)
        trakaido/
            chinese/                     # Chinese audio (zh -> chinese)
                ash/
                    audio_manifest.json  # Manifest with MD5 checksums and text
                    N01_001.mp3
                    ...
                alloy/
                echo/
            korean/                      # Korean audio (ko -> korean)
                ash/
                alloy/
                echo/
            french/                      # French audio (fr -> french)
                ash/
                alloy/
                echo/
            lithuanian/                  # Lithuanian audio (lt -> lithuanian)
                ash/
                alloy/
                echo/

Manifest file format:
    The audio_manifest.json file tracks audio files with MD5 checksums, source text, and timestamps:
    {
      "generated_at": "2025-11-01T13:59:00Z",
      "language": "zh",
      "voice": "ash",
      "files": {
        "N01_001.mp3": {
          "md5": "abc123def456...",
          "text": "你好",
          "guid": "N01_001",
          "created_at": "2025-11-01T13:40:00Z"
        }
      }
    }

    This allows detecting when translations change and audio needs regeneration.
    The created_at timestamp is preserved when rebuilding if the MD5 checksum hasn't changed,
    so it remains stable when copying files to new computers.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, List, Dict, Optional, Set, Tuple, cast
import os
import hashlib
from datetime import datetime, timezone
import re

try:
    from openai import OpenAI
except ImportError:
    print("Error: OpenAI library not found. Install with: pip install openai")
    sys.exit(1)

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent

# Local cache directory for generated audio files
# Points to separate wireword-audio repository at /Users/powera/repo/wireword-audio/trakaido/
# This is a sibling repository to greenland
CACHE_DIR = SCRIPT_DIR.parent.parent / "wireword-audio" / "trakaido"

# Supported languages
SUPPORTED_LANGUAGES = {
    "zh": {"name": "Chinese", "field": "base_target", "data_dir": "data/chinese"},
    "ko": {"name": "Korean", "field": "base_target", "data_dir": "data/korean"},
    "fr": {"name": "French", "field": "base_target", "data_dir": "data/french"},
    "lt": {"name": "Lithuanian", "field": "base_target", "data_dir": "data/lithuanian"},
}

# Audio directories now use language codes directly (lt, zh, etc.)
# No mapping needed - this matches the actual directory structure

# Available OpenAI TTS voices
AVAILABLE_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer", "ash"]

# Default voices for multi-voice mode
DEFAULT_MULTI_VOICES = ["ash", "alloy", "echo"]

# Default voice
DEFAULT_VOICE = "ash"

# OpenAI TTS model
TTS_MODEL = "gpt-4o-mini-tts"

# Audio format
AUDIO_FORMAT = "mp3"

# Manifest filename
MANIFEST_FILENAME = "audio_manifest.json"

# API key location (in parent repo, since audio is a submodule)
API_KEY_FILE = SCRIPT_DIR.parent / "keys" / "openai.key"


def get_language_dir(language: str) -> str:
    """
    Get the directory name for a language code.

    The audio directory structure uses language codes directly (e.g., 'zh', 'lt').

    Args:
        language: Language code (zh, ko, fr, lt)

    Returns:
        Language code (same as input)
    """
    return language


def load_api_key() -> Optional[str]:
    """
    Load OpenAI API key from file or environment variable.

    Returns:
        API key string or None if not found
    """
    # Try environment variable first
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        return api_key

    # Try reading from file
    if API_KEY_FILE.exists():
        with open(API_KEY_FILE, "r") as f:
            return f.read().strip()

    return None


def load_wireword_data(file_path: Path) -> List[Dict]:
    """
    Load wireword data from JSON file.

    Args:
        file_path: Path to wireword JSON file

    Returns:
        List of word dictionaries
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Try standard JSON first
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # If that fails, try stripping trailing commas (common in generated files)
            # This is a simple regex that removes trailing commas before } or ]
            import re

            content_fixed = re.sub(r",(\s*[}\]])", r"\1", content)
            data = json.loads(content_fixed)

    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parsing error in {file_path}: {e}")

    # Handle both array and object formats
    # json.loads returns Any; each branch is checked before being narrowed.
    if isinstance(data, list):
        return cast(List[Dict], data)
    elif isinstance(data, dict) and "words" in data:
        return cast(List[Dict], data["words"])
    elif isinstance(data, dict) and "items" in data:
        return cast(List[Dict], data["items"])
    elif isinstance(data, dict) and "sentences" in data:
        return cast(List[Dict], data["sentences"])
    else:
        raise ValueError(
            f"Unexpected JSON format in {file_path}. Expected list or dict with 'words', 'items', or 'sentences' key."
        )


def resolve_wireword_files(paths: List[Path]) -> List[Path]:
    """
    Resolve file paths or directories to a list of wireword JSON files.

    Skips sentence files (wireword_*_sentences.json) as they have a different format.

    Args:
        paths: List of file paths or directory paths

    Returns:
        List of resolved wireword JSON file paths
    """
    resolved_files = []

    for path in paths:
        if path.is_file():
            # Direct file path - check if it's a sentence file
            if "_sentences.json" in path.name:
                print(f"Skipping sentence file: {path.name}")
                continue
            resolved_files.append(path)
        elif path.is_dir():
            # Directory - find all wireword_*.json files except sentences
            wireword_files = sorted(path.glob("wireword_*.json"))
            # Filter out sentence files
            wireword_files = [f for f in wireword_files if "_sentences.json" not in f.name]

            if not wireword_files:
                print(f"Warning: No wireword_*.json files found in {path}")
            else:
                print(f"Found {len(wireword_files)} wireword files in {path}:")
                for f in wireword_files:
                    print(f"  - {f.name}")
                resolved_files.extend(wireword_files)
        else:
            raise FileNotFoundError(f"Path not found: {path}")

    return resolved_files


def get_output_filename(word_data: Dict, language: str) -> str:
    """
    Generate output filename for a word.

    For Lithuanian (lt), uses the 'base_target' field (the Lithuanian word) as filename.
    For other languages with GUIDs, uses the GUID.
    Otherwise, generates a filename from the English text.

    Args:
        word_data: Dictionary containing word data
        language: Language code (zh, ko, fr, lt)

    Returns:
        Filename without extension
    """
    # Lithuanian audio files use the target word as filename, not GUID
    if language == "lt" and "base_target" in word_data:
        return cast(str, word_data["base_target"])

    # Other languages use GUID if available
    if "guid" in word_data:
        return cast(str, word_data["guid"])

    # Fallback: create filename from English text
    english = word_data.get("base_english", "unknown")
    # Sanitize for filename
    filename = english.lower().replace(" ", "_").replace("/", "_")
    # Remove special characters
    filename = "".join(c for c in filename if c.isalnum() or c == "_")
    return str(filename)


def get_text_to_speak(word_data: Dict, language: str) -> str:
    """
    Extract the text to be spoken from word data.

    Args:
        word_data: Dictionary containing word data
        language: Language code (zh, ko, fr)

    Returns:
        Text to be converted to speech
    """
    lang_config = SUPPORTED_LANGUAGES[language]
    field = lang_config["field"]

    text = word_data.get(field)
    if not text:
        raise ValueError(f"Missing '{field}' field in word data: {word_data}")

    return cast(str, text)


def generate_audio_openai(
    text: str, output_path: Path, voice: str, api_key: str, language: str, model: str = TTS_MODEL
) -> bool:
    """
    Generate audio file using OpenAI TTS API.

    Args:
        text: Text to convert to speech
        output_path: Path where audio file should be saved
        voice: Voice name to use
        api_key: OpenAI API key
        language: Language code (zh, ko, fr) for instructions
        model: TTS model to use

    Returns:
        True if successful, False otherwise
    """
    try:
        client = OpenAI(api_key=api_key)

        # Get language name for instructions
        language_name = SUPPORTED_LANGUAGES[language]["name"]

        # Build request parameters
        request_params = {
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": AUDIO_FORMAT,
        }

        # Add instructions field for gpt-4o-mini-tts
        if model == "gpt-4o-mini-tts":
            request_params["instructions"] = f"Speak in {language_name}."

        response = client.audio.speech.create(**request_params)

        # Write audio to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        response.stream_to_file(str(output_path))

        return True

    except Exception as e:
        print(f"Error generating audio: {e}")
        return False


def calculate_md5(file_path: Path) -> str:
    """
    Calculate MD5 checksum of a file.

    Args:
        file_path: Path to file

    Returns:
        MD5 hex digest
    """
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    return md5.hexdigest()


def load_manifest(cache_dir: Path, language: str, voice: str) -> Dict:
    """
    Load manifest file for a language/voice combination.

    Args:
        cache_dir: Base cache directory
        language: Language code
        voice: Voice name

    Returns:
        Manifest dictionary or empty structure if not found
    """
    language_dir = get_language_dir(language)
    manifest_path = cache_dir / language_dir / voice / MANIFEST_FILENAME

    if not manifest_path.exists():
        return {"generated_at": None, "language": language, "voice": voice, "files": {}}

    with open(manifest_path, "r", encoding="utf-8") as f:
        return cast(Dict, json.load(f))


def save_manifest(cache_dir: Path, language: str, voice: str, manifest: Dict) -> None:
    """
    Save manifest file for a language/voice combination.

    Args:
        cache_dir: Base cache directory
        language: Language code
        voice: Voice name
        manifest: Manifest dictionary to save
    """
    language_dir = get_language_dir(language)
    manifest_path = cache_dir / language_dir / voice / MANIFEST_FILENAME
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Update timestamp
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    manifest["language"] = language
    manifest["voice"] = voice

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def add_to_manifest(manifest: Dict, filename: str, text: str, file_path: Path, guid: str) -> None:
    """
    Add or update an entry in the manifest.

    Args:
        manifest: Manifest dictionary
        filename: Audio filename (e.g., "N01_001.mp3")
        text: Text that was spoken
        file_path: Path to audio file (for MD5 calculation)
        guid: GUID identifier
    """
    md5 = calculate_md5(file_path)

    # Check if entry exists with same MD5 - preserve timestamp if so
    existing_entry = manifest["files"].get(filename)
    if existing_entry and existing_entry.get("md5") == md5 and existing_entry.get("created_at"):
        # MD5 unchanged and we have a valid timestamp, preserve it
        timestamp = existing_entry.get("created_at")
    else:
        # New file, changed MD5, or missing timestamp - use file creation time
        stat = file_path.stat()
        # Use birthtime (creation) if available, otherwise mtime
        creation_time = getattr(stat, "st_birthtime", stat.st_mtime)
        timestamp = (
            datetime.fromtimestamp(creation_time, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    manifest["files"][filename] = {"md5": md5, "text": text, "guid": guid, "created_at": timestamp}


def _load_derivative_forms_from_wireword(wireword_files: List[Path]) -> Dict[str, Tuple[str, str]]:
    """
    Load derivative forms from wireword files for matching audio files.

    Args:
        wireword_files: List of paths to wireword JSON files

    Returns:
        Dict mapping normalized text to (guid, grammatical_form) tuple
        e.g., {"aš gyvenu": ("V01_001", "1s_pres")}
    """
    derivative_map = {}

    for wireword_file in wireword_files:
        try:
            words = load_wireword_data(wireword_file)
            for word in words:
                guid = word.get("guid")
                if not guid:
                    continue

                # Check for grammatical_forms field
                grammatical_forms = word.get("grammatical_forms", {})
                for form_key, form_data in grammatical_forms.items():
                    # Extract target text
                    target_text = form_data.get("target")
                    if not target_text:
                        continue

                    # Normalize text for matching (lowercase, remove extra spaces)
                    normalized_text = target_text.strip().lower()

                    # Store mapping: normalized text -> (guid, grammatical_form_key)
                    derivative_map[normalized_text] = (guid, form_key)

        except Exception as e:
            print(f"  Warning: Could not load derivative forms from {wireword_file.name}: {e}")
            continue

    print(f"  Loaded {len(derivative_map)} derivative forms from wireword files")
    return derivative_map


def rebuild_manifest_from_files(
    cache_dir: Path, language: str, voice: str, wireword_files: List[Path]
) -> Dict:
    """
    Rebuild manifest by scanning existing audio files and matching with wireword data.

    Args:
        cache_dir: Base cache directory
        language: Language code
        voice: Voice name
        wireword_files: List of paths to wireword JSON files for text lookup

    Returns:
        New manifest dictionary
    """
    print(f"\nRebuilding manifest for {language}/{voice}...")

    # Load existing manifest to preserve timestamps where MD5 matches
    existing_manifest = load_manifest(cache_dir, language, voice)

    # Load wireword data for text lookup from all files
    # Build TWO mappings:
    # 1. filename -> text (for all files)
    # 2. filename -> guid (for manifest GUID field)
    text_by_filename = {}
    guid_by_filename = {}
    for wireword_file in wireword_files:
        print(f"  Loading {wireword_file.name}...")
        words = load_wireword_data(wireword_file)
        for word in words:
            filename = get_output_filename(word, language)
            text = get_text_to_speak(word, language)
            guid = word.get("guid", filename)  # Use actual GUID from wireword data

            text_by_filename[filename] = text
            guid_by_filename[filename] = guid

    print(f"  Loaded {len(text_by_filename)} total words from {len(wireword_files)} file(s)")

    # Load derivative forms from wireword files for matching conjugated/declined forms
    derivative_form_map = _load_derivative_forms_from_wireword(wireword_files)

    # Scan audio files
    language_dir = get_language_dir(language)
    voice_dir = cache_dir / language_dir / voice
    if not voice_dir.exists():
        print(f"  No audio files found in {voice_dir}")
        return {"generated_at": None, "language": language, "voice": voice, "files": {}}

    # Heterogeneous values, so the type is spelled out rather than inferred
    # as a union that would reject manifest["files"][...] assignment.
    manifest: Dict[str, Any] = {
        "generated_at": None,
        "language": language,
        "voice": voice,
        "files": {},
    }

    audio_files = list(voice_dir.glob(f"*.{AUDIO_FORMAT}"))
    print(f"  Found {len(audio_files)} audio files")

    for audio_file in audio_files:
        file_stem = audio_file.stem
        filename = audio_file.name

        # Try to match as derivative form first (e.g., "aš_gyvenu")
        # Convert filename to text form (replace underscores with spaces)
        text_form = file_stem.replace("_", " ").strip().lower()
        # Named apart from the guid/text used above when loading wireword data:
        # these describe the audio file being matched, not a source word.
        grammatical_form: Optional[str] = None
        file_guid: Optional[str] = None
        file_text: Optional[str] = None

        if text_form in derivative_form_map:
            # This is a derivative form (e.g., "aš gyvenu")
            file_guid, grammatical_form = derivative_form_map[text_form]
            file_text = file_stem.replace("_", " ")  # Keep original casing for text
        else:
            # This is a base form - look up GUID from wireword data
            file_guid = guid_by_filename.get(file_stem)
            file_text = text_by_filename.get(file_stem)

        if not file_text or not file_guid:
            print(f"  Warning: No match found for {filename}, skipping")
            continue

        # Calculate MD5
        md5 = calculate_md5(audio_file)

        # Check if we should preserve timestamp from existing manifest
        existing_entry = existing_manifest["files"].get(filename)
        if existing_entry and existing_entry.get("md5") == md5 and existing_entry.get("created_at"):
            # MD5 matches and we have a valid timestamp, preserve it
            timestamp = existing_entry.get("created_at")
        else:
            # New file, changed MD5, or missing timestamp - get from file stats
            stat = audio_file.stat()
            # Use birthtime (creation) if available, otherwise mtime
            creation_time = getattr(stat, "st_birthtime", stat.st_mtime)
            timestamp = (
                datetime.fromtimestamp(creation_time, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )

        manifest["files"][filename] = {
            "md5": md5,
            "text": file_text,
            "guid": file_guid,
            "grammatical_form": grammatical_form,  # None for base forms
            "created_at": timestamp,
        }

    print(f"  Added {len(manifest['files'])} entries to manifest")

    return manifest


def get_existing_files(cache_dir: Path, language: str, voice: str) -> Set[str]:
    """
    Get set of existing audio files in cache.

    Args:
        cache_dir: Base cache directory
        language: Language code
        voice: Voice name

    Returns:
        Set of filenames (without extension) that already exist
    """
    language_dir = get_language_dir(language)
    voice_dir = cache_dir / language_dir / voice
    if not voice_dir.exists():
        return set()

    existing = set()
    for file in voice_dir.glob(f"*.{AUDIO_FORMAT}"):
        existing.add(file.stem)

    return existing


def check_remote_files(language: str, voice: str) -> Set[str]:
    """
    Check which files are available on the remote server/S3.

    TODO: Implement remote file checking
    - For DigitalOcean Spaces (S3-compatible), use boto3
    - For remote server, use SSH/SFTP

    Args:
        language: Language code
        voice: Voice name

    Returns:
        Set of filenames available remotely
    """
    # TODO: Implement remote checking
    print(f"TODO: Check remote files for {language}/{voice}")
    return set()


def sync_to_remote(local_dir: Path, language: str, voice: str) -> bool:
    """
    Sync generated audio files to remote storage.

    TODO: Implement remote sync
    Options:
    1. DigitalOcean Spaces (S3-compatible):
       - Use boto3 with Spaces endpoint
       - More scalable, CDN support

    2. Remote server directory:
       - Use rsync or scp
       - Simpler, but need to update server path

    Args:
        local_dir: Local directory containing audio files
        language: Language code
        voice: Voice name

    Returns:
        True if successful, False otherwise
    """
    # TODO: Implement remote sync
    print(f"TODO: Sync {local_dir} to remote storage for {language}/{voice}")
    print("Options:")
    print("  1. DigitalOcean Spaces: s3://trakaido-audio/{language}/{voice}/")
    print("  2. Remote server: user@host:/path/to/audio/{language}/{voice}/")
    return False


def generate_audio_for_file(
    file_paths: List[Path],
    language: str,
    voices: List[str],
    force: bool = False,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, int]:
    """
    Generate audio files for all words in wireword files.

    Args:
        file_paths: List of paths to wireword JSON files
        language: Language code (zh, ko, fr)
        voices: List of voice names to use
        force: If True, regenerate existing files
        dry_run: If True, only show what would be done
        limit: If set, only process first N words (for testing)

    Returns:
        Dictionary with statistics (generated, skipped, failed)
    """
    # Load API key
    api_key = load_api_key()
    if not api_key and not dry_run:
        raise ValueError(
            "OpenAI API key not found. Set OPENAI_API_KEY environment variable or create keys/openai.key"
        )

    # Load word data from all files
    print(f"Loading data from {len(file_paths)} file(s)...")
    words = []
    for file_path in file_paths:
        print(f"  Loading {file_path.name}...")
        words.extend(load_wireword_data(file_path))

    # Apply limit if specified
    if limit is not None and limit > 0:
        words = words[:limit]
        print(f"Limited to first {len(words)} words (--limit {limit})")
    else:
        print(f"Found {len(words)} total words")

    stats = {"generated": 0, "skipped": 0, "failed": 0}

    for voice in voices:
        print(f"\n{'='*60}")
        print(f"Processing with voice: {voice}")
        print(f"{'='*60}\n")

        # Load manifest
        manifest = load_manifest(CACHE_DIR, language, voice)

        # Get existing files
        existing_files = get_existing_files(CACHE_DIR, language, voice)
        print(f"Found {len(existing_files)} existing files in cache")

        voice_stats = {"generated": 0, "skipped": 0, "failed": 0}

        for i, word_data in enumerate(words, 1):
            try:
                # Get filename and text
                filename = get_output_filename(word_data, language)
                text = get_text_to_speak(word_data, language)
                full_filename = f"{filename}.{AUDIO_FORMAT}"

                # Check if file already exists
                if not force and filename in existing_files:
                    voice_stats["skipped"] += 1
                    continue

                # Generate output path
                language_dir = get_language_dir(language)
                output_path = CACHE_DIR / language_dir / voice / full_filename

                if dry_run:
                    print(f"[DRY RUN] Would generate: {full_filename} - '{text}'")
                    voice_stats["generated"] += 1
                else:
                    # Generate audio
                    print(f"[{i}/{len(words)}] Generating {full_filename} - '{text}'")

                    # Guaranteed by the load_api_key() guard above, which raises
                    # unless dry_run; this branch is the not-dry_run path.
                    assert api_key is not None
                    if generate_audio_openai(text, output_path, voice, api_key, language):
                        voice_stats["generated"] += 1
                        # Add to manifest
                        add_to_manifest(manifest, full_filename, text, output_path, filename)
                    else:
                        voice_stats["failed"] += 1

                    # Small delay to avoid rate limits
                    time.sleep(0.1)

            except Exception as e:
                print(f"Error processing word: {e}")
                voice_stats["failed"] += 1

        # Save manifest after processing all words for this voice
        if not dry_run:
            save_manifest(CACHE_DIR, language, voice, manifest)
            print(f"\nManifest saved with {len(manifest['files'])} entries")

        # Print voice statistics
        print(f"\nVoice '{voice}' statistics:")
        print(f"  Generated: {voice_stats['generated']}")
        print(f"  Skipped:   {voice_stats['skipped']}")
        print(f"  Failed:    {voice_stats['failed']}")

        # Update overall stats
        for key in stats:
            stats[key] += voice_stats[key]

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate multi-language audio using OpenAI TTS API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate Chinese audio with default voice
  python wireword_audio.py --language zh --file data/chinese/wireword_nouns.json

  # Generate with default voices (ash, alloy, echo)
  python wireword_audio.py --language ko --file data/korean/wireword_nouns.json --multi-voice

  # Generate with specific voices
  python wireword_audio.py --language fr --file data/french/wireword_nouns.json --voices alloy nova

  # Test with first 5 words only
  python wireword_audio.py --language zh --file data/chinese/wireword_nouns.json --limit 5

  # Check what would be generated (dry run)
  python wireword_audio.py --language zh --file data/chinese/wireword_nouns.json --dry-run
        """,
    )

    parser.add_argument(
        "--language",
        "-l",
        type=str,
        required=True,
        choices=list(SUPPORTED_LANGUAGES.keys()),
        help="Language code (zh=Chinese, ko=Korean, fr=French, lt=Lithuanian)",
    )

    parser.add_argument(
        "--file",
        "-f",
        type=str,
        nargs="+",
        required=True,
        help="Path(s) to wireword JSON file(s) or directory containing wireword_*.json files. Can specify multiple paths.",
    )

    parser.add_argument(
        "--voice",
        type=str,
        choices=AVAILABLE_VOICES,
        default=DEFAULT_VOICE,
        help=f"Voice to use (default: {DEFAULT_VOICE})",
    )

    parser.add_argument(
        "--voices",
        type=str,
        nargs="+",
        choices=AVAILABLE_VOICES,
        help="Specific voices to use (overrides --voice and --multi-voice)",
    )

    parser.add_argument(
        "--multi-voice", action="store_true", help="Generate audio with all available voices"
    )

    parser.add_argument(
        "--force", action="store_true", help="Regenerate files even if they already exist"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually generating files",
    )

    parser.add_argument("--limit", type=int, help="Only process first N words (useful for testing)")

    parser.add_argument(
        "--check-remote",
        action="store_true",
        help="Check which files are available remotely (TODO: not yet implemented)",
    )

    parser.add_argument(
        "--sync",
        action="store_true",
        help="Sync generated files to remote storage (TODO: not yet implemented)",
    )

    parser.add_argument(
        "--model",
        type=str,
        choices=["gpt-4o-mini-tts", "tts-1", "tts-1-hd"],
        default=TTS_MODEL,
        help=f"OpenAI TTS model to use (default: {TTS_MODEL})",
    )

    parser.add_argument(
        "--rebuild-manifest",
        action="store_true",
        help="Rebuild manifest file from existing audio files by scanning cache and matching with wireword data",
    )

    args = parser.parse_args()

    # Resolve file paths (handles both files and directories)
    input_paths = [Path(f) for f in args.file]
    for path in input_paths:
        if not path.exists():
            print(f"Error: Path not found: {path}")
            sys.exit(1)

    file_paths = resolve_wireword_files(input_paths)
    if not file_paths:
        print("Error: No wireword files found")
        sys.exit(1)

    # Determine which voices to use
    if args.voices:
        voices = args.voices
    elif args.multi_voice:
        voices = DEFAULT_MULTI_VOICES
    else:
        voices = [args.voice]

    # Handle remote check
    if args.check_remote:
        print(f"Checking remote files for {args.language}...")
        for voice in voices:
            remote_files = check_remote_files(args.language, voice)
            print(f"  {voice}: {len(remote_files)} files")
        return

    # Handle manifest rebuild
    if args.rebuild_manifest:
        print(f"Rebuilding manifest for {SUPPORTED_LANGUAGES[args.language]['name']}")
        print(f"Files: {', '.join(str(f.name) for f in file_paths)}")
        print(f"Voices: {', '.join(voices)}\n")

        for voice in voices:
            manifest = rebuild_manifest_from_files(CACHE_DIR, args.language, voice, file_paths)
            save_manifest(CACHE_DIR, args.language, voice, manifest)
            print(f"Manifest saved for {voice}")

        print("\nManifest rebuild complete!")
        return

    # Generate audio
    try:
        print(f"Generating audio for {SUPPORTED_LANGUAGES[args.language]['name']}")
        print(f"Files: {', '.join(str(f.name) for f in file_paths)}")
        print(f"Voices: {', '.join(voices)}")
        print(f"Model: {args.model}")

        if args.dry_run:
            print("\n*** DRY RUN MODE - No files will be generated ***\n")

        stats = generate_audio_for_file(
            file_paths,
            args.language,
            voices,
            force=args.force,
            dry_run=args.dry_run,
            limit=args.limit,
        )

        # Print overall statistics
        print("\n" + "=" * 60)
        print("Overall Statistics:")
        print(f"  Total generated: {stats['generated']}")
        print(f"  Total skipped:   {stats['skipped']}")
        print(f"  Total failed:    {stats['failed']}")
        print("=" * 60)

        # Handle remote sync
        if args.sync and not args.dry_run:
            print("\nSyncing to remote storage...")
            for voice in voices:
                local_dir = CACHE_DIR / args.language / voice
                sync_to_remote(local_dir, args.language, voice)

        # Exit with error if any failures
        if stats["failed"] > 0:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
