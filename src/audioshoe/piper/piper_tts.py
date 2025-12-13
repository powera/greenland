#!/usr/bin/python3
"""
Piper TTS client for audio generation.

Piper is a fast, local neural text-to-speech system.
Repository: https://github.com/rhasspy/piper
"""

import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# Add src directory to path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.audio.types import AudioFormat, AudioGenerationResult
from audioshoe.piper.types import PiperVoice

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class PiperClient:
    """Client for generating audio using Piper TTS."""

    def __init__(
        self,
        piper_command: str = "piper",
        models_dir: Optional[Path] = None,
        debug: bool = False
    ):
        """
        Initialize Piper TTS client.

        Args:
            piper_command: Path to piper executable (default: "piper")
            models_dir: Directory containing Piper voice models (.onnx files)
                       Default: ~/.local/share/piper/models
            debug: Enable debug logging
        """
        self.piper_command = piper_command
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized PiperClient in debug mode")

        # Set models directory
        if models_dir is None:
            self.models_dir = Path.home() / ".local" / "share" / "piper" / "models"
        else:
            self.models_dir = Path(models_dir)

        if not self.models_dir.exists():
            logger.warning(f"Piper models directory not found: {self.models_dir}")
            logger.info(f"You may need to download voice models to {self.models_dir}")

        # Verify piper is available
        try:
            result = subprocess.run(
                [self.piper_command, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info(f"Piper version: {result.stdout.strip()}")
            else:
                logger.warning("Piper may not be properly installed")
        except FileNotFoundError:
            logger.error(f"Piper not found at: {self.piper_command}")
            raise RuntimeError(
                f"Piper not found. Please install it or specify the correct path."
            )
        except Exception as e:
            logger.warning(f"Could not verify Piper installation: {e}")

    def _find_model_file(self, voice: PiperVoice) -> Optional[Path]:
        """
        Find the model file for a given voice.

        Args:
            voice: PiperVoice to find model for

        Returns:
            Path to model file or None if not found
        """
        # Look for model file: {piper_identifier}.onnx
        # Example: lt_LT-human-medium.onnx
        model_filename = f"{voice.piper_identifier}.onnx"
        model_path = self.models_dir / model_filename

        if model_path.exists():
            return model_path

        # Also check in language subdirectories
        lang_dir = self.models_dir / voice.piper_identifier.split("-")[0]
        if lang_dir.exists():
            model_path = lang_dir / model_filename
            if model_path.exists():
                return model_path

        logger.error(f"Model file not found: {model_filename}")
        logger.info(f"Searched in: {self.models_dir}")
        logger.info(f"Expected identifier: {voice.piper_identifier}")
        return None

    def generate_audio(
        self,
        text: str,
        voice: PiperVoice,
        audio_format: AudioFormat = AudioFormat.MP3,
        speed: float = 1.0,  # Piper uses speed multiplier (default: 1.0)
    ) -> AudioGenerationResult:
        """
        Generate audio from text using Piper TTS.

        Args:
            text: Text to convert to speech
            voice: PiperVoice to use for generation
            audio_format: Output audio format (only MP3 and WAV are supported)
            speed: Speech speed multiplier (0.25-4.0, default: 1.0)

        Returns:
            AudioGenerationResult with audio data and metadata
        """
        start_time = time.time()

        if self.debug:
            logger.debug(f"Generating audio for text: {text}")
            logger.debug(f"Voice: {voice.name}, Language: {voice.language_code}")

        # Validate audio format
        if audio_format not in [AudioFormat.MP3, AudioFormat.WAV]:
            error_msg = f"Unsupported audio format: {audio_format.value}. Only MP3 and WAV are supported."
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=voice.language_code,
                model="piper",
                duration_ms=0,
                success=False,
                error=error_msg,
            )

        try:
            # Find model file
            model_path = self._find_model_file(voice)
            if model_path is None:
                error_msg = f"Model file not found for voice: {voice.ui_name} ({voice.piper_identifier})"
                logger.error(error_msg)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=voice.language_code,
                    model="piper",
                    duration_ms=0,
                    success=False,
                    error=error_msg,
                )

            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                wav_path = Path(tmp_wav.name)

            # Build Piper command
            # Piper reads text from stdin and writes WAV to stdout or file
            cmd = [
                self.piper_command,
                "--model", str(model_path),
                "--output_file", str(wav_path),
            ]

            # Add length scale (inverse of speed)
            if speed != 1.0:
                length_scale = 1.0 / speed
                cmd.extend(["--length_scale", str(length_scale)])

            if self.debug:
                logger.debug(f"Running command: {' '.join(cmd)}")
                logger.debug(f"Input text: {text}")

            # Run Piper (text is passed via stdin)
            result = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = f"Piper failed with code {result.returncode}: {result.stderr}"
                logger.error(error_msg)
                logger.error(f"Voice identifier used: '{voice.piper_identifier}' (name: {voice.ui_name})")
                logger.error(f"Model path: {model_path}")
                wav_path.unlink(missing_ok=True)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=voice.language_code,
                    model="piper",
                    duration_ms=0,
                    success=False,
                    error=error_msg,
                )

            # Read WAV file
            if not wav_path.exists():
                error_msg = "Piper did not generate output file"
                logger.error(error_msg)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=voice.language_code,
                    model="piper",
                    duration_ms=0,
                    success=False,
                    error=error_msg,
                )

            audio_data = wav_path.read_bytes()
            final_audio_data = audio_data

            # Convert to MP3 if requested
            if audio_format == AudioFormat.MP3:
                try:
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
                        mp3_path = Path(tmp_mp3.name)

                    # Use ffmpeg to convert WAV to MP3
                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-i", str(wav_path),
                        "-codec:a", "libmp3lame",
                        "-qscale:a", "2",  # High quality
                        "-y",  # Overwrite output file
                        str(mp3_path),
                    ]

                    if self.debug:
                        logger.debug(f"Converting to MP3: {' '.join(ffmpeg_cmd)}")

                    ffmpeg_result = subprocess.run(
                        ffmpeg_cmd,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if ffmpeg_result.returncode != 0:
                        logger.warning(
                            f"ffmpeg conversion failed: {ffmpeg_result.stderr}. "
                            "Returning WAV format instead."
                        )
                    else:
                        final_audio_data = mp3_path.read_bytes()
                        mp3_path.unlink(missing_ok=True)

                except FileNotFoundError:
                    logger.warning("ffmpeg not found. Returning WAV format instead.")
                except Exception as e:
                    logger.warning(f"MP3 conversion failed: {e}. Returning WAV format instead.")

            # Clean up temporary WAV file
            wav_path.unlink(missing_ok=True)

            duration_ms = (time.time() - start_time) * 1000

            if self.debug:
                logger.debug(f"Generated {len(final_audio_data)} bytes in {duration_ms:.0f}ms")

            return AudioGenerationResult(
                audio_data=final_audio_data,
                text=text,
                voice=None,  # No OpenAI voice equivalent
                language_code=voice.language_code,
                model="piper",
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

        except subprocess.TimeoutExpired:
            error_msg = "Piper command timed out"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=voice.language_code,
                model="piper",
                duration_ms=0,
                success=False,
                error=error_msg,
            )
        except Exception as e:
            error_msg = f"Error generating audio: {str(e)}"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=voice.language_code,
                model="piper",
                duration_ms=0,
                success=False,
                error=error_msg,
            )


# Create default client instance
_client: Optional[PiperClient] = None


def get_client() -> PiperClient:
    """Get or create the default Piper client instance."""
    global _client
    if _client is None:
        _client = PiperClient(debug=False)
    return _client


def generate_audio(
    text: str,
    voice: PiperVoice,
    audio_format: AudioFormat = AudioFormat.MP3,
    speed: float = 1.0,
) -> AudioGenerationResult:
    """
    Generate audio from text using Piper TTS.

    Convenience function that uses the default client instance.

    Args:
        text: Text to convert to speech
        voice: PiperVoice to use for generation
        audio_format: Output audio format (MP3 or WAV)
        speed: Speech speed multiplier (0.25-4.0, default: 1.0)

    Returns:
        AudioGenerationResult with audio data and metadata
    """
    return get_client().generate_audio(text, voice, audio_format, speed)
