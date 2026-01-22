#!/usr/bin/python3
"""
Qwen3-TTS client for audio generation.

Qwen3-TTS is a high-quality neural text-to-speech system with multilingual support,
voice cloning, and voice design capabilities.
Repository: https://github.com/QwenLM/Qwen3-TTS
"""

import io
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional, Union

import torch

# Add src directory to path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from audioshoe.qwen.types import QWEN_LANGUAGE_NAMES, QwenVoice
from clients.audio.types import AudioFormat, AudioGenerationResult

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_device() -> torch.device:
    """
    Get the best available device for inference.

    Returns MPS for Apple Silicon, CUDA for NVIDIA GPUs, or CPU as fallback.
    """
    if torch.backends.mps.is_available():
        return torch.device("mps")
    elif torch.cuda.is_available():
        return torch.device("cuda:0")
    else:
        return torch.device("cpu")


def get_dtype(device: torch.device) -> torch.dtype:
    """
    Get the appropriate dtype for the given device.

    Args:
        device: The torch device to use

    Returns:
        Appropriate dtype (bfloat16 for CUDA, float16 for MPS, float32 for CPU)
    """
    if device.type == "cuda":
        return torch.bfloat16
    elif device.type == "mps":
        return torch.float16
    else:
        return torch.float32


class QwenTTSClient:
    """Client for generating audio using Qwen3-TTS."""

    # Available model variants
    MODEL_VOICE_DESIGN = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
    MODEL_CUSTOM_VOICE = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    MODEL_BASE = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    MODEL_CUSTOM_VOICE_SMALL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
    MODEL_BASE_SMALL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[Union[str, torch.device]] = None,
        dtype: Optional[torch.dtype] = None,
        use_flash_attention: bool = False,
        ref_audio_dir: Optional[Path] = None,
        debug: bool = False,
    ):
        """
        Initialize Qwen3-TTS client.

        Args:
            model_name: Qwen3-TTS model to use. Default: VoiceDesign model.
                       Options: MODEL_VOICE_DESIGN, MODEL_CUSTOM_VOICE, MODEL_BASE
            device: Device to run on ("mps", "cuda:0", "cpu", or torch.device).
                   Default: auto-detect (MPS for Mac, CUDA for NVIDIA, CPU fallback)
            dtype: Data type for model weights. Default: auto-select based on device
            use_flash_attention: Use Flash Attention 2 for faster inference (CUDA only)
            ref_audio_dir: Directory containing reference audio files for voice cloning.
                          Default: ~/.local/share/qwen-tts/speakers
            debug: Enable debug logging
        """
        self.debug = debug
        self.model = None  # Lazy-loaded model instance
        self._loaded_model_name: Optional[str] = None

        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized QwenTTSClient in debug mode")

        # Set model name
        self.model_name = model_name or self.MODEL_VOICE_DESIGN

        # Set device
        if device is None:
            self.device = get_device()
        elif isinstance(device, str):
            self.device = torch.device(device)
        else:
            self.device = device

        # Set dtype
        if dtype is None:
            self.dtype = get_dtype(self.device)
        else:
            self.dtype = dtype

        # Flash attention only works on CUDA
        self.use_flash_attention = use_flash_attention and self.device.type == "cuda"

        # Set reference audio directory for voice cloning
        if ref_audio_dir is None:
            self.ref_audio_dir = Path.home() / ".local" / "share" / "qwen-tts" / "speakers"
        else:
            self.ref_audio_dir = Path(ref_audio_dir)

        # Create speaker directory if it doesn't exist
        self.ref_audio_dir.mkdir(parents=True, exist_ok=True)

        if self.debug:
            logger.debug(f"Device: {self.device}")
            logger.debug(f"Dtype: {self.dtype}")
            logger.debug(f"Model: {self.model_name}")
            logger.debug(f"Flash Attention: {self.use_flash_attention}")

        # Verify qwen-tts library is available
        try:
            import qwen_tts

            logger.info(f"Qwen TTS library loaded successfully")
        except ImportError:
            logger.error("Qwen TTS library not found. Please install it: pip install qwen-tts")
            raise RuntimeError(
                "Qwen TTS library not found. Please install it with: pip install qwen-tts"
            )

    def _get_model(self, model_name: Optional[str] = None) -> Any:
        """
        Get or create model instance for the specified model.

        Args:
            model_name: TTS model name to load. Default: self.model_name

        Returns:
            Qwen3TTSModel instance
        """
        from qwen_tts import Qwen3TTSModel

        target_model = model_name or self.model_name

        # Return cached model if same model is requested
        if self.model is not None and self._loaded_model_name == target_model:
            return self.model

        if self.debug:
            logger.debug(f"Loading Qwen TTS model: {target_model}")

        # Build kwargs for model loading
        kwargs = {
            "device_map": str(self.device) if self.device.type != "cpu" else "cpu",
            "dtype": self.dtype,
        }

        # Add flash attention if requested and available
        if self.use_flash_attention:
            kwargs["attn_implementation"] = "flash_attention_2"

        self.model = Qwen3TTSModel.from_pretrained(target_model, **kwargs)
        self._loaded_model_name = target_model

        if self.debug:
            logger.debug(f"Model loaded successfully on {self.device}")

        return self.model

    def _get_ref_audio(self, voice: QwenVoice) -> Optional[Path]:
        """
        Get reference audio file for voice cloning.

        Args:
            voice: QwenVoice to get reference audio for

        Returns:
            Path to reference audio file or None if not found
        """
        # Look for voice-specific reference audio
        # Example: qwen-zh-f1.wav
        ref_filename = f"{voice.ui_name}.wav"
        ref_path = self.ref_audio_dir / ref_filename

        if ref_path.exists():
            if self.debug:
                logger.debug(f"Found reference audio: {ref_path}")
            return ref_path

        # Also check for language-gender-pitch specific
        # Example: zh-female-soprano.wav
        gender_name = "female" if voice.gender == "f" else "male"
        lang_ref = f"{voice.language_code}-{gender_name}-{voice.pitch_type}.wav"
        lang_ref_path = self.ref_audio_dir / lang_ref

        if lang_ref_path.exists():
            if self.debug:
                logger.debug(f"Found language reference audio: {lang_ref_path}")
            return lang_ref_path

        # Check for language-gender default
        # Example: zh-female.wav
        default_ref = f"{voice.language_code}-{gender_name}.wav"
        default_ref_path = self.ref_audio_dir / default_ref

        if default_ref_path.exists():
            if self.debug:
                logger.debug(f"Found default reference audio: {default_ref_path}")
            return default_ref_path

        if self.debug:
            logger.debug(f"No reference audio found for {voice.ui_name}")
        return None

    def _wav_to_bytes(self, wav_data: Any, sample_rate: int, audio_format: AudioFormat) -> bytes:
        """
        Convert WAV tensor/array to bytes in requested format.

        Args:
            wav_data: Audio waveform (tensor or numpy array)
            sample_rate: Sample rate of audio
            audio_format: Desired output format

        Returns:
            Audio data as bytes
        """
        import numpy as np
        import scipy.io.wavfile as wavfile

        # Convert tensor to numpy if needed
        if isinstance(wav_data, torch.Tensor):
            wav_np = wav_data.cpu().numpy()
        else:
            wav_np = np.array(wav_data)

        # Ensure proper shape (1D for mono)
        if wav_np.ndim > 1:
            wav_np = wav_np.squeeze()

        # Normalize to int16 range
        if wav_np.dtype in [np.float32, np.float64]:
            wav_np = (wav_np * 32767).astype(np.int16)

        # Write to WAV buffer
        wav_buffer = io.BytesIO()
        wavfile.write(wav_buffer, sample_rate, wav_np)
        wav_bytes = wav_buffer.getvalue()

        # Return WAV directly if requested
        if audio_format == AudioFormat.WAV:
            return wav_bytes

        # Convert to MP3 if requested
        if audio_format == AudioFormat.MP3:
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                    tmp_wav.write(wav_bytes)
                    wav_path = Path(tmp_wav.name)

                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_mp3:
                    mp3_path = Path(tmp_mp3.name)

                # Use ffmpeg to convert
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i",
                    str(wav_path),
                    "-codec:a",
                    "libmp3lame",
                    "-qscale:a",
                    "2",
                    "-y",
                    str(mp3_path),
                ]

                if self.debug:
                    logger.debug(f"Converting to MP3: {' '.join(ffmpeg_cmd)}")

                result = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    mp3_bytes = mp3_path.read_bytes()
                    mp3_path.unlink(missing_ok=True)
                    wav_path.unlink(missing_ok=True)
                    return mp3_bytes
                else:
                    logger.warning(f"ffmpeg conversion failed: {result.stderr}")
                    wav_path.unlink(missing_ok=True)

            except FileNotFoundError:
                logger.warning("ffmpeg not found. Returning WAV format instead.")
            except Exception as e:
                logger.warning(f"MP3 conversion failed: {e}. Returning WAV format instead.")

        # Fallback to WAV
        return wav_bytes

    def generate_audio(
        self,
        text: str,
        voice: QwenVoice,
        audio_format: AudioFormat = AudioFormat.MP3,
        instruct: Optional[str] = None,
        use_voice_cloning: bool = False,
        ref_audio: Optional[Union[str, Path]] = None,
        ref_text: Optional[str] = None,
    ) -> AudioGenerationResult:
        """
        Generate audio from text using Qwen3-TTS.

        Args:
            text: Text to convert to speech
            voice: QwenVoice to use for generation
            audio_format: Output audio format (MP3 or WAV supported)
            instruct: Optional style/emotion instruction (e.g., "happy", "serious")
            use_voice_cloning: Use voice cloning with reference audio instead of voice design
            ref_audio: Path to reference audio for voice cloning (overrides auto-detect)
            ref_text: Transcript of reference audio (required for voice cloning)

        Returns:
            AudioGenerationResult with audio data and metadata
        """
        start_time = time.time()

        if self.debug:
            logger.debug(f"Generating audio for text: {text}")
            logger.debug(f"Voice: {voice.name}, Language: {voice.language_code}")
            logger.debug(f"Voice design prompt: {voice.voice_design_prompt[:100]}...")

        # Validate audio format
        if audio_format not in [AudioFormat.MP3, AudioFormat.WAV]:
            error_msg = (
                f"Unsupported audio format: {audio_format.value}. Only MP3 and WAV are supported."
            )
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=voice.language_code,
                model="qwen3-tts",
                duration_ms=0,
                success=False,
                error=error_msg,
            )

        try:
            # Determine generation method
            if use_voice_cloning:
                return self._generate_with_voice_cloning(
                    text=text,
                    voice=voice,
                    audio_format=audio_format,
                    ref_audio=ref_audio,
                    ref_text=ref_text,
                    start_time=start_time,
                )
            else:
                return self._generate_with_voice_design(
                    text=text,
                    voice=voice,
                    audio_format=audio_format,
                    instruct=instruct,
                    start_time=start_time,
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
                model="qwen3-tts",
                duration_ms=0,
                success=False,
                error=error_msg,
            )

    def _generate_with_voice_design(
        self,
        text: str,
        voice: QwenVoice,
        audio_format: AudioFormat,
        instruct: Optional[str],
        start_time: float,
    ) -> AudioGenerationResult:
        """Generate audio using voice design (natural language description)."""
        model = self._get_model(self.MODEL_VOICE_DESIGN)

        # Build voice design instruction
        design_prompt = voice.voice_design_prompt
        if instruct:
            design_prompt = f"{design_prompt} Speaking style: {instruct}."

        if self.debug:
            logger.debug(f"Voice design prompt: {design_prompt}")

        # Generate audio
        wavs, sr = model.generate_voice_design(
            text=text,
            language=voice.qwen_language,
            instruct=design_prompt,
        )

        # Convert to bytes
        audio_data = self._wav_to_bytes(wavs[0], sr, audio_format)

        duration_ms = (time.time() - start_time) * 1000

        if self.debug:
            logger.debug(f"Generated {len(audio_data)} bytes in {duration_ms:.0f}ms")

        return AudioGenerationResult(
            audio_data=audio_data,
            text=text,
            voice=None,
            language_code=voice.language_code,
            model="qwen3-tts-voice-design",
            duration_ms=duration_ms,
            success=True,
            error=None,
        )

    def _generate_with_voice_cloning(
        self,
        text: str,
        voice: QwenVoice,
        audio_format: AudioFormat,
        ref_audio: Optional[Union[str, Path]],
        ref_text: Optional[str],
        start_time: float,
    ) -> AudioGenerationResult:
        """Generate audio using voice cloning from reference audio."""
        model = self._get_model(self.MODEL_BASE)

        # Get reference audio
        if ref_audio is None:
            ref_audio = self._get_ref_audio(voice)

        if ref_audio is None:
            error_msg = (
                f"No reference audio found for voice cloning. "
                f"Please provide ref_audio or place a file at: "
                f"{self.ref_audio_dir / voice.ui_name}.wav"
            )
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=voice.language_code,
                model="qwen3-tts",
                duration_ms=0,
                success=False,
                error=error_msg,
            )

        if ref_text is None:
            error_msg = "ref_text (transcript of reference audio) is required for voice cloning"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=None,
                language_code=voice.language_code,
                model="qwen3-tts",
                duration_ms=0,
                success=False,
                error=error_msg,
            )

        if self.debug:
            logger.debug(f"Reference audio: {ref_audio}")
            logger.debug(f"Reference text: {ref_text}")

        # Generate audio with voice cloning
        wavs, sr = model.generate_voice_clone(
            text=text,
            language=voice.qwen_language,
            ref_audio=str(ref_audio),
            ref_text=ref_text,
        )

        # Convert to bytes
        audio_data = self._wav_to_bytes(wavs[0], sr, audio_format)

        duration_ms = (time.time() - start_time) * 1000

        if self.debug:
            logger.debug(f"Generated {len(audio_data)} bytes in {duration_ms:.0f}ms")

        return AudioGenerationResult(
            audio_data=audio_data,
            text=text,
            voice=None,
            language_code=voice.language_code,
            model="qwen3-tts-voice-clone",
            duration_ms=duration_ms,
            success=True,
            error=None,
        )


# Create default client instance
_client: Optional[QwenTTSClient] = None


def get_client() -> QwenTTSClient:
    """Get or create the default Qwen TTS client instance."""
    global _client
    if _client is None:
        _client = QwenTTSClient(debug=False)
    return _client


def generate_audio(
    text: str,
    voice: QwenVoice,
    audio_format: AudioFormat = AudioFormat.MP3,
    instruct: Optional[str] = None,
) -> AudioGenerationResult:
    """
    Generate audio from text using Qwen3-TTS.

    Convenience function that uses the default client instance with voice design.

    Args:
        text: Text to convert to speech
        voice: QwenVoice to use for generation
        audio_format: Output audio format (MP3 or WAV)
        instruct: Optional style/emotion instruction

    Returns:
        AudioGenerationResult with audio data and metadata
    """
    return get_client().generate_audio(text, voice, audio_format, instruct=instruct)
