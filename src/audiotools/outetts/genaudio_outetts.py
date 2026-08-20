#!/usr/bin/env python3
"""
Text-to-Speech Generator using OuteAI/Llama-OuteTTS-1.0-1B

This script uses the OuteTTS model to generate audio files from text input.
It's optimized for Mac with M3 chip (Apple Silicon) and doesn't require NVIDIA/CUDA.
Supports multiple audio formats (WAV, MP3, OGG, FLAC) with configurable quality settings.

Usage:
    # Basic usage (defaults to WAV format)
    python genaudio_outetts.py --text "Your text here" --output output.wav
    
    # Generate MP3 audio (more space-efficient)
    python genaudio_outetts.py --text "Your text here" --format mp3 --output output.mp3
    
    # Process a text file with each line as separate audio, convert to OGG format
    python genaudio_outetts.py --file input.txt --format ogg --quality high --output-dir ./audio_files

    # Lithuanian pronunciation examples
    python genaudio_outetts.py --lithuanian "duona" --format mp3 --output lithuanian_audio.mp3
    python genaudio_outetts.py --lithuanian "Laba diena" --format flac --output laba_diena.flac
    python genaudio_outetts.py --lithuanian-batch words.txt --format mp3 --output-dir ./lithuanian_audio
    
Audio Format Options:
    --format wav|mp3|ogg|flac   Select audio format (default: wav)
    --quality low|medium|high   Set quality level (default: medium)
    --keep-wav                  Keep original WAV files after conversion

Logging Options:
    --debug                     Enable debug mode with verbose logging from underlying libraries
    --quiet                     Suppress verbose logs from underlying libraries (default behavior)

Voice Files:
    Lithuanian voice files (lithuanian_ash.json, lithuanian_alloy.json,
    lithuanian_nova.json) are not checked in here. They live in the audio/
    submodule (github.com/powera/audiotools) under outetts/outetts_voices/ .
    Point OUTETTS_VOICES_DIR at that directory, or copy the files into an
    'outetts_voices' subdirectory beside this script.
"""

import argparse
import contextlib
import io
import json
import logging
import os
import re
import subprocess
import soundfile as sf
import time
import outetts
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from audiotools.file_utils import (
    ensure_output_directory,
    read_words_from_file,
)
from langtools.lt.utils import sanitize_lithuanian_word

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent

# Directory for OuteTTS voice files. The voice JSONs are not checked into this
# repo -- they live in the audio/ submodule -- so allow pointing at a checkout
# of it rather than requiring the files be copied in beside this script.
VOICES_DIR = Path(os.environ.get("OUTETTS_VOICES_DIR", SCRIPT_DIR / "outetts_voices"))

# Audio format options
AUDIO_FORMATS = {
    "wav": {"extension": ".wav", "description": "WAV (uncompressed, largest files)"},
    "mp3": {"extension": ".mp3", "description": "MP3 (compressed, good compatibility)"},
    "ogg": {
        "extension": ".ogg",
        "description": "OGG Vorbis (compressed, better quality/size ratio)",
    },
    "flac": {"extension": ".flac", "description": "FLAC (lossless compression, medium size)"},
}


def configure_logging(debug_mode: bool = False) -> AbstractContextManager[Any]:
    """Configure logging levels to reduce verbose output from underlying libraries."""
    if debug_mode:
        # Enable debug logging
        logging.basicConfig(level=logging.DEBUG)
        print("Debug mode enabled - showing all logs")
    else:
        # Suppress verbose logs from underlying libraries
        logging.basicConfig(level=logging.WARNING)

        # Try to suppress llama.cpp logs through environment variables
        os.environ["LLAMA_LOG_LEVEL"] = "2"  # Only errors and warnings
        os.environ["GGML_LOG_LEVEL"] = "2"  # Only errors and warnings

        # Suppress other common verbose loggers
        logging.getLogger("outetts").setLevel(logging.WARNING)
        logging.getLogger("llama_cpp").setLevel(logging.WARNING)
        logging.getLogger("ggml").setLevel(logging.WARNING)

        # Redirect stderr temporarily during model initialization to suppress ggml logs
        # This is a bit aggressive but necessary for the verbose ggml_metal_init logs
        return contextlib.redirect_stderr(io.StringIO())

    return contextlib.nullcontext()


def setup_tts_interface(debug_mode: bool = False) -> Any:
    """Initialize and return the TTS interface with the 1B model."""
    if not debug_mode:
        print("Initializing OuteTTS model (this may take a moment)...")
    else:
        print("Initializing OuteTTS model in debug mode (this may take a moment)...")

    # Configure logging suppression
    stderr_context = configure_logging(debug_mode)

    with stderr_context:
        # Configure for Apple Silicon (M3)
        interface = outetts.Interface(
            config=outetts.ModelConfig.auto_config(
                model=outetts.Models.VERSION_1_0_SIZE_1B,
                # Using llama.cpp backend which works well on Apple Silicon
                backend=outetts.Backend.LLAMACPP,
                # FP16 is a good balance for Apple Silicon
                quantization=outetts.LlamaCppQuantization.FP16,
            )
        )

    return interface


def list_available_speakers(interface: Any) -> List[str]:
    """List all available speaker profiles."""
    print("\nAvailable speaker profiles:")
    # outetts is untyped, so list_speakers() comes back as Any.
    speakers: List[str] = list(interface.list_speakers())
    for i, speaker in enumerate(speakers):
        print(f"{i+1}. {speaker}")
    return speakers


def generate_audio(
    interface: Any,
    text: str,
    output_path: Union[str, Path],
    speaker_name: Optional[str] = None,
    debug_mode: bool = False,
) -> Union[str, Path]:
    """Generate audio from text and save to the specified output path."""
    start_time = time.time()

    # Load speaker profile
    if speaker_name is None:
        # Default to English female neutral voice if none specified
        speaker = interface.load_default_speaker("EN-FEMALE-1-NEUTRAL")
        print(f"Using default speaker: EN-FEMALE-1-NEUTRAL")
    else:
        speaker = interface.load_default_speaker(speaker_name)
        print(f"Using speaker: {speaker_name}")

    print(f"Generating audio for text: '{text}'")

    # Configure stderr suppression for generation if not in debug mode
    stderr_context = configure_logging(debug_mode) if not debug_mode else contextlib.nullcontext()

    with stderr_context:
        # Generate speech
        output = interface.generate(
            config=outetts.GenerationConfig(
                text=text,
                speaker=speaker,
                # Optional parameters for generation quality
                # temperature=0.7,
                # top_p=0.9,
            )
        )

        # Save to file
        output.save(output_path)

    elapsed_time = time.time() - start_time
    print(f"Audio generated and saved to {output_path} in {elapsed_time:.2f} seconds")

    return output_path


def process_file(
    interface: Any,
    file_path: Union[str, Path],
    output_dir: Union[str, Path],
    speaker_name: Optional[str] = None,
    force: bool = False,
    output_format: str = "wav",
    debug_mode: bool = False,
) -> None:
    """
    Process a text file and generate audio for each line.

    Args:
        interface: The TTS interface
        file_path: Path to the text file
        output_dir: Directory to save the audio files
        speaker_name: Speaker profile to use
        force: Whether to overwrite existing files
        output_format: The desired final output format (wav, mp3, ogg, flac)
        debug_mode: Whether to show debug logs
    """
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found")
        return

    # Create output directory if it doesn't exist
    output_dir = ensure_output_directory(output_dir)

    lines = read_words_from_file(file_path)

    if not lines:
        print("No lines found in the file")
        return

    print(f"Processing {len(lines)} lines from {file_path}")

    # Get the extension for the target format
    target_extension = AUDIO_FORMATS.get(output_format, {}).get("extension", ".wav")

    for i, line in enumerate(lines):
        wav_file = output_dir / f"audio_{i+1}.wav"
        target_file = output_dir / f"audio_{i+1}{target_extension}"

        # Skip if target file exists and not forcing overwrite
        if target_file.exists() and not force:
            print(f"Skipping line {i+1}: file already exists in {output_format} format")
            continue

        # Skip if WAV file exists and not forcing overwrite
        if wav_file.exists() and not force and output_format == "wav":
            print(f"Skipping line {i+1}: WAV file already exists")
            continue

        print(f"Processing line {i+1}/{len(lines)}")
        generate_audio(interface, line, str(wav_file), speaker_name, debug_mode)


def generate_lithuanian_audio(
    interface: Any,
    text: str,
    output_path: Union[str, Path],
    speaker_name: str = "ash",
    debug_mode: bool = False,
) -> Optional[str]:
    """
    Generate audio for a Lithuanian word or phrase with proper pronunciation.

    Args:
        interface: The OuteTTS interface
        text: The Lithuanian word or phrase to pronounce
        output_path: Path to save the audio file
        speaker_name: Speaker voice to use (ash, alloy, or nova). Default is ash.
        debug_mode: Whether to show debug logs

    Returns:
        Path to the generated audio file or None if failed
    """
    # Map speaker name to the corresponding JSON file in the outetts_voices directory
    speaker_file = VOICES_DIR / f"lithuanian_{speaker_name}.json"

    # Verify that the speaker file exists
    if not speaker_file.exists():
        raise Exception(
            f"Speaker file {speaker_file} not found. Available options are: ash, alloy, nova. "
            f"The OuteTTS voice JSONs are not checked into this repo; set "
            f"OUTETTS_VOICES_DIR to the audio/ submodule's outetts/outetts_voices/ directory."
        )
    sanitized_text = sanitize_lithuanian_word(text)
    if not sanitized_text:
        print(f"Error: Invalid Lithuanian text format: {text}")
        return None

    print(f"Generating Lithuanian pronunciation for: {text}")

    # Load speaker profile
    if speaker_file is None:
        raise Exception("Speaker file is required for Lithuanian audio generation")
    else:
        speaker = interface.load_speaker(str(speaker_file))
        print(f"Using speaker from file: {speaker_file}")

    try:
        # Configure stderr suppression for generation if not in debug mode
        stderr_context = (
            configure_logging(debug_mode) if not debug_mode else contextlib.nullcontext()
        )

        with stderr_context:
            # Generate speech with just the Lithuanian text
            # The model should handle Lithuanian pronunciation based on the characters
            output = interface.generate(
                config=outetts.GenerationConfig(
                    text=text, speaker=speaker  # Just use the Lithuanian text directly
                )
            )

            # Save to file - convert Path to string if needed
            output_path_str = str(output_path) if hasattr(output_path, "is_file") else output_path
            output.save(output_path_str)

        print(f"Lithuanian audio saved to {output_path_str}")
        return output_path_str

    except Exception as e:
        print(f"Error generating Lithuanian audio for '{text}': {str(e)}")
        return None


def convert_audio(
    input_path: Union[str, Path],
    output_format: str = "mp3",
    quality: str = "medium",
    delete_original: bool = False,
) -> Optional[Path]:
    """
    Convert audio file to a more space-efficient format.

    Args:
        input_path: Path to the input audio file (typically WAV)
        output_format: Target format - "mp3", "ogg", or "flac" (default: "mp3")
        quality: Quality setting - "low", "medium", or "high" (default: "medium")
        delete_original: Whether to delete the original file after conversion (default: False)

    Returns:
        Path to the converted file or None if conversion failed
    """
    if output_format not in AUDIO_FORMATS:
        print(
            f"Error: Unsupported output format '{output_format}'. Supported formats: {', '.join(AUDIO_FORMATS.keys())}"
        )
        return None

    input_path = Path(input_path)
    if not input_path.exists():
        print(f"Error: Input file {input_path} not found")
        return None

    # Determine output path with new extension
    output_extension = AUDIO_FORMATS[output_format]["extension"]
    output_path = input_path.with_suffix(output_extension)

    # Set quality parameters based on format
    quality_settings = {
        "mp3": {"low": "96k", "medium": "128k", "high": "192k"},
        "ogg": {"low": "3", "medium": "5", "high": "7"},
        "flac": {"low": "1", "medium": "5", "high": "8"},
    }

    quality_value = quality_settings.get(output_format, {}).get(quality, "medium")

    try:
        # Method 1: Try using soundfile if format is supported
        if output_format in ["flac", "ogg"]:
            try:
                data, samplerate = sf.read(str(input_path))
                sf.write(str(output_path), data, samplerate, format=output_format.upper())
                print(f"Converted {input_path} to {output_path} using soundfile")

                if delete_original:
                    input_path.unlink()

                return output_path
            except Exception as e:
                print(f"Warning: soundfile conversion failed: {e}. Trying ffmpeg...")

        # Method 2: Use ffmpeg as a fallback or for MP3
        cmd = []
        if output_format == "mp3":
            cmd = ["ffmpeg", "-y", "-i", str(input_path), "-b:a", quality_value, str(output_path)]
        elif output_format == "ogg":
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-c:a",
                "libvorbis",
                "-q:a",
                quality_value,
                str(output_path),
            ]
        elif output_format == "flac":
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-compression_level",
                quality_value,
                str(output_path),
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error during conversion: {result.stderr}")
            return None

        print(f"Converted {input_path} to {output_path} using ffmpeg")

        # Get file sizes for comparison
        original_size = input_path.stat().st_size
        converted_size = output_path.stat().st_size
        size_reduction = (1 - (converted_size / original_size)) * 100

        print(
            f"Size reduction: {size_reduction:.1f}% (from {original_size/1024:.1f}KB to {converted_size/1024:.1f}KB)"
        )

        if delete_original:
            input_path.unlink()
            print(f"Deleted original file: {input_path}")

        return output_path

    except Exception as e:
        print(f"Error converting audio: {str(e)}")
        return None


def process_lithuanian_batch(
    interface: Any,
    file_path: Union[str, Path],
    output_dir: Union[str, Path],
    force: bool = False,
    speaker_name: str = "ash",
    output_format: str = "wav",
    debug_mode: bool = False,
) -> Tuple[int, int]:
    """
    Process a batch of Lithuanian words or phrases from a file.

    Args:
        interface: The OuteTTS interface
        file_path: Path to the file containing Lithuanian words or phrases (one per line)
        output_dir: Directory to save the audio files
        force: Whether to overwrite existing files
        speaker_name: Lithuanian speaker voice to use (ash, alloy, or nova). Default is ash.
        output_format: The desired final output format (wav, mp3, ogg, flac)
        debug_mode: Whether to show debug logs

    Returns:
        Tuple of (success_count, total_count)
    """
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found")
        return 0, 0

    # Create output directory if it doesn't exist
    output_dir = ensure_output_directory(output_dir)

    entries = read_words_from_file(file_path)

    if not entries:
        print("No entries found in the file")
        return 0, 0

    print(f"Processing {len(entries)} Lithuanian entries from {file_path}")

    success_count = 0
    total_count = len(entries)

    # Get the extension for the target format
    target_extension = AUDIO_FORMATS.get(output_format, {}).get("extension", ".wav")

    for i, entry in enumerate(entries, 1):
        sanitized = sanitize_lithuanian_word(entry)
        if not sanitized:
            print(f"[{i}/{total_count}] Skipping invalid entry: {entry}")
            continue

        # Check if the target format file already exists
        target_file = output_dir / f"{sanitized}{target_extension}"
        wav_file = output_dir / f"{sanitized}.wav"

        # Skip if target file exists and not forcing overwrite
        if target_file.exists() and not force:
            print(
                f"[{i}/{total_count}] Skipping {entry}: file already exists in {output_format} format"
            )
            success_count += 1  # Count as success since file exists
            continue

        # Skip if WAV file exists and not forcing overwrite
        if wav_file.exists() and not force:
            print(f"[{i}/{total_count}] Skipping {entry}: WAV file already exists")
            success_count += 1  # Count as success since file exists
            continue

        print(f"[{i}/{total_count}] Processing: {entry}")
        if generate_lithuanian_audio(interface, entry, wav_file, speaker_name, debug_mode):
            success_count += 1
            # Add a small delay between generations to avoid overloading
            time.sleep(0.5)

    return success_count, total_count


def process_json_file(
    interface: Any,
    json_path: Union[str, Path],
    output_dir: Union[str, Path],
    force: bool = False,
    speaker_name: str = "ash",
    output_format: str = "wav",
    items_key: Optional[str] = None,
    debug_mode: bool = False,
) -> Tuple[int, int]:
    """
    Process a JSON file containing sentences/phrases with explicit filenames.

    Args:
        interface: The OuteTTS interface
        json_path: Path to the JSON file
        output_dir: Directory to save the audio files
        force: Whether to overwrite existing files
        speaker_name: Lithuanian speaker voice to use (ash, alloy, or nova). Default is ash.
        output_format: The desired final output format (wav, mp3, ogg, flac)
        items_key: Key in JSON containing the items (default: auto-detect)
        debug_mode: Whether to show debug logs

    Returns:
        Tuple of (success_count, total_count)
    """
    if not os.path.exists(json_path):
        print(f"Error: File {json_path} not found")
        return 0, 0

    # Load JSON data
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {json_path}: {e}")
        return 0, 0

    # Auto-detect items key if not specified
    if items_key is None:
        common_keys = ["sentences", "phrases", "items", "words", "entries", "data"]
        for key in common_keys:
            if key in data and isinstance(data[key], list):
                items_key = key
                break

        if items_key is None:
            # Look for any list that's not metadata
            for key, value in data.items():
                if isinstance(value, list) and key != "metadata":
                    items_key = key
                    break

        if items_key is None:
            print("Error: Could not auto-detect items key in JSON")
            return 0, 0

        print(f"Auto-detected items key: '{items_key}'")

    if items_key not in data:
        print(f"Error: Key '{items_key}' not found in JSON")
        return 0, 0

    items = data[items_key]
    if not isinstance(items, list):
        print(f"Error: '{items_key}' must be a list")
        return 0, 0

    # Create output directory if it doesn't exist
    output_dir = ensure_output_directory(output_dir)

    print(f"Processing {len(items)} items from {json_path}")
    print(f"Using speaker: {speaker_name}")
    print(f"Output format: {output_format}")
    print()

    success_count = 0
    total_count = len(items)

    # Get the extension for the target format
    target_extension = AUDIO_FORMATS.get(output_format, {}).get("extension", ".wav")

    for i, item in enumerate(items, 1):
        # Extract Lithuanian text
        if "lithuanian" not in item:
            print(f"[{i}/{total_count}] Warning: Item missing 'lithuanian' field, skipping")
            continue

        lithuanian_text = item["lithuanian"]

        # Extract filename
        if "filename" not in item:
            print(f"[{i}/{total_count}] Warning: Item missing 'filename' field, skipping")
            continue

        filename = item["filename"]

        # Check if the target format file already exists
        target_file = output_dir / f"{filename}{target_extension}"
        wav_file = output_dir / f"{filename}.wav"

        # Skip if target file exists and not forcing overwrite
        if target_file.exists() and not force:
            print(
                f"[{i}/{total_count}] Skipping {filename}: file already exists in {output_format} format"
            )
            success_count += 1  # Count as success since file exists
            continue

        # Skip if WAV file exists and not forcing overwrite
        if wav_file.exists() and not force:
            print(f"[{i}/{total_count}] Skipping {filename}: WAV file already exists")
            success_count += 1  # Count as success since file exists
            continue

        print(f"[{i}/{total_count}] Processing: {lithuanian_text} → {filename}")
        if generate_lithuanian_audio(
            interface, lithuanian_text, wav_file, speaker_name, debug_mode
        ):
            success_count += 1
            # Add a small delay between generations to avoid overloading
            time.sleep(0.5)

    return success_count, total_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate audio files using OuteTTS")

    # Create a mutually exclusive group for input methods
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--text", type=str, help="Text to convert to speech")
    input_group.add_argument("--file", type=str, help="Path to a text file to process")
    input_group.add_argument(
        "--lithuanian", type=str, help="Lithuanian word or phrase to generate pronunciation for"
    )
    input_group.add_argument(
        "--lithuanian-batch",
        type=str,
        help="Path to a file with Lithuanian words or phrases (one per line)",
    )
    input_group.add_argument(
        "--json-file",
        type=str,
        help="Path to a JSON file with sentences/phrases (must include 'filename' field)",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Output audio file path (for single text) or directory (for file input)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Output directory for batch processing (alternative to --output)",
    )
    parser.add_argument(
        "--speaker", type=str, help="Speaker profile to use (default: EN-FEMALE-1-NEUTRAL)"
    )
    parser.add_argument(
        "--lithuanian-speaker",
        type=str,
        choices=["ash", "alloy", "nova"],
        default="ash",
        help="Lithuanian speaker voice to use (ash, alloy, or nova) (default: ash)",
    )
    parser.add_argument(
        "--items-key", type=str, help="Key in JSON containing items (default: auto-detect)"
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing files instead of skipping them"
    )

    # Audio format options
    parser.add_argument(
        "--format",
        type=str,
        choices=list(AUDIO_FORMATS.keys()),
        default="wav",
        help="Audio format to use (default: wav)",
    )
    parser.add_argument(
        "--quality",
        type=str,
        choices=["low", "medium", "high"],
        default="medium",
        help="Audio quality setting (default: medium)",
    )
    parser.add_argument(
        "--keep-wav",
        action="store_true",
        help="Keep original WAV files after conversion (default: delete WAV files)",
    )

    # Logging options
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with verbose logging from underlying libraries",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose logs from underlying libraries (default behavior)",
    )

    args = parser.parse_args()

    # Initialize the TTS interface with debug mode if requested
    interface = setup_tts_interface(debug_mode=args.debug)

    # Determine output path/directory
    output_path = args.output or args.output_dir

    try:
        # Check if we need to convert audio (only if format is not wav)
        need_conversion = args.format != "wav"
        delete_original = not args.keep_wav

        if args.text:
            if not output_path:
                # Use the appropriate extension based on format
                extension = AUDIO_FORMATS[args.format]["extension"]
                output_path = f"output{extension}"

            # Check if the target format file already exists
            target_path = Path(output_path)
            if target_path.exists() and not args.force:
                print(
                    f"Skipping generation: {target_path.name} already exists in {args.format} format"
                )
            else:
                # Always generate WAV first if we need to convert
                if need_conversion and not output_path.endswith(".wav"):
                    wav_path = Path(output_path).with_suffix(".wav")

                    # Check if WAV exists and we're not forcing overwrite
                    if wav_path.exists() and not args.force:
                        print(f"WAV file {wav_path.name} already exists, using it for conversion")
                    else:
                        generate_audio(
                            interface, args.text, str(wav_path), args.speaker, args.debug
                        )

                    # Convert to desired format if target doesn't exist or force is True
                    if not target_path.exists() or args.force:
                        convert_audio(wav_path, args.format, args.quality, delete_original)
                else:
                    generate_audio(interface, args.text, output_path, args.speaker, args.debug)

        elif args.file:
            if not output_path:
                output_path = "output_audio"

            # Create output directory
            os.makedirs(output_path, exist_ok=True)

            # Process file to generate WAV files
            process_file(
                interface, args.file, output_path, args.speaker, args.force, args.format, args.debug
            )

            # Convert all WAV files if needed
            if need_conversion:
                print(f"\nConverting audio files to {args.format.upper()} format...")
                wav_files = list(Path(output_path).glob("*.wav"))

                converted_count = 0
                for wav_file in wav_files:
                    # Check if the target format file already exists
                    target_file = wav_file.with_suffix(AUDIO_FORMATS[args.format]["extension"])
                    if target_file.exists() and not args.force:
                        print(
                            f"Skipping conversion of {wav_file.name}: {target_file.name} already exists"
                        )
                        continue

                    if convert_audio(wav_file, args.format, args.quality, delete_original):
                        converted_count += 1

                print(
                    f"Converted {converted_count}/{len(wav_files)} files to {args.format.upper()} format"
                )

        elif args.lithuanian:
            if not output_path:
                sanitized = sanitize_lithuanian_word(args.lithuanian)
                extension = AUDIO_FORMATS[args.format]["extension"]
                # Use the new directory structure with speaker-specific subdirectory
                output_dir = ensure_output_directory(
                    SCRIPT_DIR / f"lithuanian-audio-cache/{args.lithuanian_speaker}"
                )
                output_path = output_dir / f"{sanitized}{extension}"

            # Check if the target format file already exists
            target_path = Path(output_path)
            if target_path.exists() and not args.force:
                print(
                    f"Skipping generation: {target_path.name} already exists in {args.format} format"
                )
            else:
                # Always generate WAV first if we need to convert
                if need_conversion and not str(output_path).endswith(".wav"):
                    wav_path = Path(output_path).with_suffix(".wav")

                    # Check if WAV exists and we're not forcing overwrite
                    if wav_path.exists() and not args.force:
                        print(f"WAV file {wav_path.name} already exists, using it for conversion")
                    else:
                        generate_lithuanian_audio(
                            interface,
                            args.lithuanian,
                            str(wav_path),
                            args.lithuanian_speaker,
                            args.debug,
                        )

                    # Convert to desired format if target doesn't exist or force is True
                    if not target_path.exists() or args.force:
                        convert_audio(wav_path, args.format, args.quality, delete_original)
                else:
                    generate_lithuanian_audio(
                        interface,
                        args.lithuanian,
                        str(output_path),
                        args.lithuanian_speaker,
                        args.debug,
                    )

        elif args.lithuanian_batch:
            if not output_path:
                # Use the new directory structure with speaker-specific subdirectory
                output_path = SCRIPT_DIR / f"lithuanian-audio-cache/{args.lithuanian_speaker}"

            # Process batch to generate WAV files, passing the target format
            success_count, total_count = process_lithuanian_batch(
                interface,
                args.lithuanian_batch,
                output_path,
                args.force,
                args.lithuanian_speaker,
                args.format,  # Pass the target format
                args.debug,  # Pass debug mode
            )

            # Convert all WAV files if needed
            if need_conversion:
                print(f"\nConverting audio files to {args.format.upper()} format...")
                # Make sure we're looking in the right directory
                output_dir = Path(output_path)
                wav_files = list(output_dir.glob("*.wav"))

                converted_count = 0
                for wav_file in wav_files:
                    # Check if the target format file already exists
                    target_file = wav_file.with_suffix(AUDIO_FORMATS[args.format]["extension"])
                    if target_file.exists() and not args.force:
                        print(
                            f"Skipping conversion of {wav_file.name}: {target_file.name} already exists"
                        )
                        continue

                    if convert_audio(wav_file, args.format, args.quality, delete_original):
                        converted_count += 1

                print(
                    f"Converted {converted_count}/{len(wav_files)} files to {args.format.upper()} format"
                )

            print(
                f"\nCompleted: {success_count}/{total_count} Lithuanian audio files generated successfully"
            )

        elif args.json_file:
            if not output_path:
                # Use the new directory structure with speaker-specific subdirectory
                output_path = SCRIPT_DIR / f"lithuanian-audio-cache/{args.lithuanian_speaker}"

            # Process JSON file to generate WAV files
            success_count, total_count = process_json_file(
                interface,
                args.json_file,
                output_path,
                args.force,
                args.lithuanian_speaker,
                args.format,
                args.items_key,
                args.debug,
            )

            # Convert all WAV files if needed
            if need_conversion:
                print(f"\nConverting audio files to {args.format.upper()} format...")
                # Make sure we're looking in the right directory
                output_dir = Path(output_path)
                wav_files = list(output_dir.glob("*.wav"))

                converted_count = 0
                for wav_file in wav_files:
                    # Check if the target format file already exists
                    target_file = wav_file.with_suffix(AUDIO_FORMATS[args.format]["extension"])
                    if target_file.exists() and not args.force:
                        print(
                            f"Skipping conversion of {wav_file.name}: {target_file.name} already exists"
                        )
                        continue

                    if convert_audio(wav_file, args.format, args.quality, delete_original):
                        converted_count += 1

                print(
                    f"Converted {converted_count}/{len(wav_files)} files to {args.format.upper()} format"
                )

            print(
                f"\nCompleted: {success_count}/{total_count} audio files from JSON generated successfully"
            )

    except KeyboardInterrupt:
        print("\nProcess interrupted by user")
    except Exception as e:
        print(f"Error: {e}")

    print("Done!")


if __name__ == "__main__":
    main()
