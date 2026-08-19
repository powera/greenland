#!/usr/bin/env python3
"""
Script to generate Lithuanian audio from JSON files containing sentences or phrases.

This is a convenience wrapper around genaudio_outetts.py that simplifies generating
audio for multiple speakers from a single JSON file. Can also upload generated files
to a remote server.

JSON Format:
{
  "metadata": {
    "description": "Description of the dataset"
  },
  "sentences": [  // or "phrases", "items", etc.
    {
      "english": "I saw the bank.",
      "lithuanian": "Aš mačiau banką.",
      "filename": "sentence_a1_1"  // Required: custom filename (without extension)
    },
    ...
  ]
}

Usage:
    # Generate audio for all sentences with default speaker (ash)
    python generate_json_audio.py --input wireword_level1_sentences.json

    # Use specific speaker
    python generate_json_audio.py --input wireword_level1_sentences.json --speaker nova

    # Generate with all three speakers
    python generate_json_audio.py --input wireword_level1_sentences.json --multi-voice

    # Generate and upload to remote server
    python generate_json_audio.py --input wireword_level1_sentences.json --multi-voice --upload

    # Custom output directory
    python generate_json_audio.py --input wireword_level1_sentences.json --output-dir ./custom_audio

    # Force overwrite existing files
    python generate_json_audio.py --input wireword_level1_sentences.json --force
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent

# Path to the genaudio script
GENAUDIO_SCRIPT = SCRIPT_DIR / "outetts" / "genaudio_outetts.py"

# Available Lithuanian speakers
SPEAKERS = ["ash", "alloy", "nova"]

# Default speaker
DEFAULT_SPEAKER = "ash"

# Default remote server configuration (from oneword_audio.sh)
DEFAULT_REMOTE_USER = "atacama"
DEFAULT_REMOTE_HOST = "137.184.45.132"
DEFAULT_REMOTE_DIR = "/home/atacama/trakaido"


def run_genaudio(
    json_path: Path,
    speaker: str,
    output_dir: Path = None,
    force: bool = False,
    format: str = "mp3",
    items_key: str = None,
    debug: bool = False,
) -> bool:
    """
    Run genaudio_outetts.py with the specified parameters.

    Returns True if successful, False otherwise.
    """
    cmd = [
        "python3",
        str(GENAUDIO_SCRIPT),
        "--json-file",
        str(json_path),
        "--lithuanian-speaker",
        speaker,
        "--format",
        format,
    ]

    if output_dir:
        cmd.extend(["--output-dir", str(output_dir)])

    if force:
        cmd.append("--force")

    if items_key:
        cmd.extend(["--items-key", items_key])

    if not debug:
        cmd.append("--quiet")

    try:
        print(f"\n{'='*60}")
        print(f"Generating audio with speaker: {speaker}")
        print(f"{'='*60}\n")

        # genaudio_outetts.py imports audiotools.*, so the child needs src/ on
        # its path the same way the project's other scripts get it.
        env = dict(os.environ)
        src_root = str(SCRIPT_DIR.parent)
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = f"{src_root}{os.pathsep}{existing}" if existing else src_root

        result = subprocess.run(cmd, check=False, env=env)

        if result.returncode == 0:
            print(f"\n✓ Successfully generated audio with speaker: {speaker}")
            return True
        else:
            print(f"\n✗ Failed to generate audio with speaker: {speaker}")
            return False

    except Exception as e:
        print(f"\n✗ Error running genaudio: {e}")
        return False


def upload_files(
    local_dir: Path,
    speaker: str,
    remote_user: str,
    remote_host: str,
    remote_dir: str,
    format: str = "mp3",
) -> bool:
    """
    Upload generated audio files to remote server.

    Args:
        local_dir: Local directory containing audio files for this speaker
        speaker: Speaker name (used for remote subdirectory)
        remote_user: Remote SSH username
        remote_host: Remote SSH hostname
        remote_dir: Base remote directory
        format: Audio format/extension

    Returns:
        True if successful, False otherwise
    """
    print(f"\nUploading {speaker} files to {remote_user}@{remote_host}...")

    # Create remote directory for this speaker
    remote_speaker_dir = f"{remote_dir}/{speaker}"
    ssh_cmd = ["ssh", f"{remote_user}@{remote_host}", f"mkdir -p '{remote_speaker_dir}'"]

    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"Warning: Could not create remote directory: {result.stderr}")
            # Continue anyway, directory might already exist

        # Find all audio files for this speaker
        audio_files = list(local_dir.glob(f"*.{format}"))

        if not audio_files:
            print(f"No {format} files found in {local_dir}")
            return True  # Not an error, just nothing to upload

        print(f"Found {len(audio_files)} files to upload")

        # Upload files using scp
        # Use a single scp command for efficiency
        scp_cmd = (
            ["scp"]
            + [str(f) for f in audio_files]
            + [f"{remote_user}@{remote_host}:{remote_speaker_dir}/"]
        )

        result = subprocess.run(scp_cmd, check=False)

        if result.returncode == 0:
            print(f"✓ Successfully uploaded {len(audio_files)} files for speaker {speaker}")
            return True
        else:
            print(f"✗ Failed to upload files for speaker {speaker}")
            return False

    except Exception as e:
        print(f"✗ Error uploading files: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate Lithuanian audio from JSON files (wrapper for genaudio_outetts.py)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate audio with default speaker (ash)
  python generate_json_audio.py --input sentences.json

  # Generate with all three speakers
  python generate_json_audio.py --input sentences.json --multi-voice

  # Use specific speaker
  python generate_json_audio.py --input sentences.json --speaker nova

  # Custom output directory
  python generate_json_audio.py --input sentences.json --output-dir ./my_audio
        """,
    )

    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="Path to JSON file containing sentences/phrases",
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default=None,
        help="Output directory (default: ./lithuanian-audio-cache/<speaker>)",
    )

    parser.add_argument(
        "--speaker",
        type=str,
        choices=SPEAKERS,
        default=DEFAULT_SPEAKER,
        help=f"Speaker voice to use (default: {DEFAULT_SPEAKER})",
    )

    parser.add_argument(
        "--multi-voice",
        action="store_true",
        help="Generate audio with all three speakers (ash, alloy, nova)",
    )

    parser.add_argument(
        "--voices",
        type=str,
        nargs="+",
        choices=SPEAKERS,
        help="Specific voices to use (overrides --speaker and --multi-voice)",
    )

    parser.add_argument(
        "--items-key", type=str, help="JSON key containing the items list (default: auto-detect)"
    )

    parser.add_argument("--force", action="store_true", help="Overwrite existing audio files")

    parser.add_argument(
        "--format",
        type=str,
        choices=["wav", "mp3", "ogg", "flac"],
        default="mp3",
        help="Audio format (default: mp3)",
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    # Upload options
    parser.add_argument(
        "--upload", action="store_true", help="Upload generated files to remote server"
    )

    parser.add_argument(
        "--remote-user",
        type=str,
        default=DEFAULT_REMOTE_USER,
        help=f"Remote SSH username (default: {DEFAULT_REMOTE_USER})",
    )

    parser.add_argument(
        "--remote-host",
        type=str,
        default=DEFAULT_REMOTE_HOST,
        help=f"Remote SSH hostname (default: {DEFAULT_REMOTE_HOST})",
    )

    parser.add_argument(
        "--remote-dir",
        type=str,
        default=DEFAULT_REMOTE_DIR,
        help=f"Remote base directory (default: {DEFAULT_REMOTE_DIR})",
    )

    args = parser.parse_args()

    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Determine output directory
    output_dir = Path(args.output_dir) if args.output_dir else None

    # Determine which speakers to use
    if args.voices:
        speakers = args.voices
    elif args.multi_voice:
        speakers = SPEAKERS
    else:
        speakers = [args.speaker]

    # Check if genaudio script exists
    if not GENAUDIO_SCRIPT.exists():
        print(f"Error: Audio generation script not found: {GENAUDIO_SCRIPT}")
        sys.exit(1)

    # Process with each speaker
    try:
        success_count = 0
        total_count = len(speakers)
        generated_dirs = []  # Track directories for upload

        for speaker in speakers:
            # Set speaker-specific output directory if base output_dir was provided
            if output_dir:
                speaker_output_dir = output_dir / speaker
            else:
                # Use default location
                speaker_output_dir = SCRIPT_DIR / "lithuanian-audio-cache" / speaker

            if run_genaudio(
                input_path,
                speaker,
                (
                    speaker_output_dir if output_dir else None
                ),  # Let genaudio use default if not specified
                args.force,
                args.format,
                args.items_key,
                args.debug,
            ):
                success_count += 1
                generated_dirs.append((speaker, speaker_output_dir))

        print("\n" + "=" * 60)
        print(f"Generation Summary: {success_count}/{total_count} speakers completed successfully")
        print("=" * 60)

        if success_count < total_count:
            print("\nWarning: Some speakers failed to generate audio")

        # Upload files if requested
        if args.upload and success_count > 0:
            print("\n" + "=" * 60)
            print("Uploading files to remote server")
            print("=" * 60)

            upload_success_count = 0
            for speaker, local_dir in generated_dirs:
                if upload_files(
                    local_dir,
                    speaker,
                    args.remote_user,
                    args.remote_host,
                    args.remote_dir,
                    args.format,
                ):
                    upload_success_count += 1

            print("\n" + "=" * 60)
            print(
                f"Upload Summary: {upload_success_count}/{len(generated_dirs)} speakers uploaded successfully"
            )
            print("=" * 60)

            if upload_success_count < len(generated_dirs):
                print("\nWarning: Some uploads failed")
                sys.exit(1)

        if success_count < total_count:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nProcess interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
