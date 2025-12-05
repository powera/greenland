#!/usr/bin/python3
"""eSpeak-NG TTS client for audio generation."""

import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import sys
from pathlib import Path

# Add src directory to path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.audio.types import Voice, AudioFormat, AudioGenerationResult

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Language code mapping to eSpeak-NG voice identifiers
# Based on eSpeak-NG documentation and BCP 47 language tags
ESPEAK_LANGUAGE_MAP = {
    "lt": "lt",  # Lithuanian
    "zh": "zh",  # Chinese (Mandarin)
    "ko": "ko",  # Korean
    "fr": "fr",  # French
    "de": "de",  # German
    "es": "es",  # Spanish
    "pt": "pt",  # Portuguese (Brazilian)
    "sw": "sw",  # Swahili
    "vi": "vi",  # Vietnamese
}

# Voice variant mapping - eSpeak-NG has different voice variants
# For now, we'll use numeric variants (1-7) which provide different pitch/tone characteristics
# The Voice enum from OpenAI doesn't directly map to eSpeak variants, so we map to numbers
VOICE_VARIANT_MAP = {
    Voice.ALLOY: "1",
    Voice.ASH: "2",
    Voice.BALLAD: "3",
    Voice.CORAL: "4",
    Voice.ECHO: "5",
    Voice.FABLE: "6",
    Voice.NOVA: "7",
    Voice.ONYX: "1",  # Reuse variants since eSpeak has limited options
    Voice.SAGE: "2",
    Voice.SHIMMER: "3",
}


class EspeakNGClient:
    """Client for generating audio using eSpeak-NG TTS."""

    def __init__(self, espeak_command: str = "espeak-ng", debug: bool = False):
        """
        Initialize eSpeak-NG TTS client.

        Args:
            espeak_command: Path to espeak-ng executable (default: "espeak-ng")
            debug: Enable debug logging
        """
        self.espeak_command = espeak_command
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized EspeakNGClient in debug mode")

        # Verify espeak-ng is available
        try:
            result = subprocess.run(
                [self.espeak_command, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info(f"eSpeak-NG version: {result.stdout.strip()}")
            else:
                logger.warning("eSpeak-NG may not be properly installed")
        except FileNotFoundError:
            logger.error(f"eSpeak-NG not found at: {self.espeak_command}")
            raise RuntimeError(
                f"eSpeak-NG not found. Please install it or specify the correct path."
            )
        except Exception as e:
            logger.warning(f"Could not verify eSpeak-NG installation: {e}")

    def generate_audio(
        self,
        text: str,
        voice: Voice = Voice.ALLOY,
        language_code: str = "lt",
        audio_format: AudioFormat = AudioFormat.MP3,
        speed: int = 150,  # eSpeak uses words per minute (default: 175, range: 80-450)
        pitch: int = 50,  # Pitch adjustment (default: 50, range: 0-99)
        ipa_input: bool = False,  # Whether input is IPA phonemes
    ) -> AudioGenerationResult:
        """
        Generate audio from text using eSpeak-NG TTS.

        Args:
            text: Text to convert to speech (or IPA if ipa_input=True)
            voice: Voice variant to use (mapped to eSpeak variants)
            language_code: Language code for voice selection
            audio_format: Output audio format (only MP3 and WAV are supported)
            speed: Speech speed in words per minute (80-450, default: 150)
            pitch: Pitch adjustment (0-99, default: 50)
            ipa_input: If True, treat input as IPA phonemes

        Returns:
            AudioGenerationResult with audio data and metadata
        """
        start_time = time.time()

        if self.debug:
            logger.debug(f"Generating audio for text: {text}")
            logger.debug(f"Voice: {voice.value}, Language: {language_code}")

        # Get eSpeak language identifier
        espeak_lang = ESPEAK_LANGUAGE_MAP.get(language_code)
        if not espeak_lang:
            error_msg = f"Unsupported language code: {language_code}"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=voice,
                language_code=language_code,
                model="espeak-ng",
                duration_ms=0,
                success=False,
                error=error_msg,
            )

        # Get voice variant
        voice_variant = VOICE_VARIANT_MAP.get(voice, "1")
        espeak_voice = f"{espeak_lang}+{voice_variant}"

        # Validate audio format (eSpeak-NG directly supports WAV)
        # For MP3, we'll generate WAV first then convert
        if audio_format not in [AudioFormat.MP3, AudioFormat.WAV]:
            error_msg = f"Unsupported audio format: {audio_format.value}. Only MP3 and WAV are supported."
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=voice,
                language_code=language_code,
                model="espeak-ng",
                duration_ms=0,
                success=False,
                error=error_msg,
            )

        try:
            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                wav_path = Path(tmp_wav.name)

            # Build eSpeak-NG command
            cmd = [
                self.espeak_command,
                "-v", espeak_voice,
                "-s", str(speed),
                "-p", str(pitch),
                "-w", str(wav_path),
            ]

            # Add IPA flag if needed
            if ipa_input:
                cmd.extend(["--ipa"])

            # Add text
            cmd.append(text)

            if self.debug:
                logger.debug(f"Running command: {' '.join(cmd)}")

            # Run eSpeak-NG
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = f"eSpeak-NG failed with code {result.returncode}: {result.stderr}"
                logger.error(error_msg)
                wav_path.unlink(missing_ok=True)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=voice,
                    language_code=language_code,
                    model="espeak-ng",
                    duration_ms=0,
                    success=False,
                    error=error_msg,
                )

            # Read WAV file
            if not wav_path.exists():
                error_msg = "eSpeak-NG did not generate output file"
                logger.error(error_msg)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=voice,
                    language_code=language_code,
                    model="espeak-ng",
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
                voice=voice,
                language_code=language_code,
                model="espeak-ng",
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

        except subprocess.TimeoutExpired:
            error_msg = "eSpeak-NG command timed out"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=voice,
                language_code=language_code,
                model="espeak-ng",
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
                voice=voice,
                language_code=language_code,
                model="espeak-ng",
                duration_ms=0,
                success=False,
                error=error_msg,
            )


# Create default client instance
_client: Optional[EspeakNGClient] = None


def get_client() -> EspeakNGClient:
    """Get or create the default eSpeak-NG client instance."""
    global _client
    if _client is None:
        _client = EspeakNGClient(debug=False)
    return _client


def generate_audio(
    text: str,
    voice: Voice = Voice.ALLOY,
    language_code: str = "lt",
    audio_format: AudioFormat = AudioFormat.MP3,
    speed: int = 150,
    pitch: int = 50,
    ipa_input: bool = False,
) -> AudioGenerationResult:
    """
    Generate audio from text using eSpeak-NG TTS.

    Convenience function that uses the default client instance.

    Args:
        text: Text to convert to speech (or IPA if ipa_input=True)
        voice: Voice variant to use
        language_code: Language code for voice selection
        audio_format: Output audio format (MP3 or WAV)
        speed: Speech speed in words per minute (80-450, default: 150)
        pitch: Pitch adjustment (0-99, default: 50)
        ipa_input: If True, treat input as IPA phonemes

    Returns:
        AudioGenerationResult with audio data and metadata
    """
    return get_client().generate_audio(
        text, voice, language_code, audio_format, speed, pitch, ipa_input
    )
