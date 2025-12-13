#!/usr/bin/python3
"""
Coqui TTS client for audio generation.

Coqui TTS (XTTS) is a high-quality neural text-to-speech system with multilingual support.
Repository: https://github.com/coqui-ai/TTS
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
from audioshoe.coqui.types import CoquiVoice

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class CoquiClient:
    """Client for generating audio using Coqui TTS."""

    def __init__(
        self,
        use_gpu: bool = True,
        speaker_wav_dir: Optional[Path] = None,
        debug: bool = False
    ):
        """
        Initialize Coqui TTS client.

        Args:
            use_gpu: Use GPU acceleration if available (default: True)
            speaker_wav_dir: Directory containing reference speaker WAV files for voice cloning
                            Default: ~/.local/share/coqui/speakers
            debug: Enable debug logging
        """
        self.use_gpu = use_gpu
        self.debug = debug
        self.tts = None  # Lazy-loaded TTS instance

        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized CoquiClient in debug mode")

        # Set speaker WAV directory for voice cloning
        if speaker_wav_dir is None:
            self.speaker_wav_dir = Path.home() / ".local" / "share" / "coqui" / "speakers"
        else:
            self.speaker_wav_dir = Path(speaker_wav_dir)

        # Create speaker directory if it doesn't exist
        self.speaker_wav_dir.mkdir(parents=True, exist_ok=True)

        # Verify TTS library is available
        try:
            import TTS
            logger.info(f"Coqui TTS library version: {TTS.__version__}")
        except ImportError:
            logger.error("Coqui TTS library not found. Please install it: pip install TTS")
            raise RuntimeError(
                "Coqui TTS library not found. Please install it with: pip install TTS"
            )

    def _get_tts(self, model_name: str):
        """
        Get or create TTS instance for the specified model.

        Args:
            model_name: TTS model name to load

        Returns:
            TTS instance
        """
        from TTS.api import TTS

        # For simplicity, we create a new instance each time
        # In production, you might want to cache instances per model
        if self.debug:
            logger.debug(f"Loading TTS model: {model_name}")

        tts = TTS(model_name=model_name, gpu=self.use_gpu)
        return tts

    def _get_speaker_wav(self, voice: CoquiVoice) -> Optional[Path]:
        """
        Get reference speaker WAV file for voice cloning.

        Args:
            voice: CoquiVoice to get speaker file for

        Returns:
            Path to speaker WAV file or None if not found
        """
        # Look for speaker WAV file named after the voice UI name
        # Example: coqui-lt-m1.wav
        speaker_filename = f"{voice.ui_name}.wav"
        speaker_path = self.speaker_wav_dir / speaker_filename

        if speaker_path.exists():
            if self.debug:
                logger.debug(f"Found speaker reference: {speaker_path}")
            return speaker_path

        # Also check for language-specific default speakers
        # Example: lt-male.wav, lt-female.wav
        lang_speaker = f"{voice.language_code}-{'male' if voice.gender == 'm' else 'female'}.wav"
        lang_speaker_path = self.speaker_wav_dir / lang_speaker

        if lang_speaker_path.exists():
            if self.debug:
                logger.debug(f"Found language speaker reference: {lang_speaker_path}")
            return lang_speaker_path

        # No speaker reference found - will use default model voice
        if self.debug:
            logger.debug(f"No speaker reference found for {voice.ui_name}")
        return None

    def generate_audio(
        self,
        text: str,
        voice: CoquiVoice,
        audio_format: AudioFormat = AudioFormat.MP3,
        speed: float = 1.0,  # Speed multiplier (default: 1.0)
    ) -> AudioGenerationResult:
        """
        Generate audio from text using Coqui TTS.

        Args:
            text: Text to convert to speech
            voice: CoquiVoice to use for generation
            audio_format: Output audio format (only MP3 and WAV are supported)
            speed: Speech speed multiplier (0.5-2.0, default: 1.0)

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
                model="coqui",
                duration_ms=0,
                success=False,
                error=error_msg,
            )

        try:
            # Get TTS instance
            tts = self._get_tts(voice.model_name)

            # Get speaker reference WAV if available
            speaker_wav = self._get_speaker_wav(voice)

            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                wav_path = Path(tmp_wav.name)

            # Generate audio
            if self.debug:
                logger.debug(f"Generating to: {wav_path}")
                logger.debug(f"Language: {voice.coqui_language}")
                logger.debug(f"Speaker WAV: {speaker_wav}")

            # XTTS v2 supports voice cloning with speaker_wav
            if speaker_wav and "xtts" in voice.model_name.lower():
                tts.tts_to_file(
                    text=text,
                    file_path=str(wav_path),
                    speaker_wav=str(speaker_wav),
                    language=voice.coqui_language,
                    speed=speed,
                )
            else:
                # Fallback without speaker cloning
                tts.tts_to_file(
                    text=text,
                    file_path=str(wav_path),
                    language=voice.coqui_language,
                    speed=speed,
                )

            # Read WAV file
            if not wav_path.exists():
                error_msg = "Coqui TTS did not generate output file"
                logger.error(error_msg)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=None,
                    language_code=voice.language_code,
                    model="coqui",
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
                model="coqui",
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

        except Exception as e:
            error_msg = f"Error generating audio: {str(e)}"
            logger.error(error_msg)
            if self.debug:
                import traceback
                logger.debug(traceback.format_exc())
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=voice.language_code,
                model="coqui",
                duration_ms=0,
                success=False,
                error=error_msg,
            )


# Create default client instance
_client: Optional[CoquiClient] = None


def get_client() -> CoquiClient:
    """Get or create the default Coqui client instance."""
    global _client
    if _client is None:
        _client = CoquiClient(debug=False)
    return _client


def generate_audio(
    text: str,
    voice: CoquiVoice,
    audio_format: AudioFormat = AudioFormat.MP3,
    speed: float = 1.0,
) -> AudioGenerationResult:
    """
    Generate audio from text using Coqui TTS.

    Convenience function that uses the default client instance.

    Args:
        text: Text to convert to speech
        voice: CoquiVoice to use for generation
        audio_format: Output audio format (MP3 or WAV)
        speed: Speech speed multiplier (0.5-2.0, default: 1.0)

    Returns:
        AudioGenerationResult with audio data and metadata
    """
    return get_client().generate_audio(text, voice, audio_format, speed)
