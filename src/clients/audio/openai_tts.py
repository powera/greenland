#!/usr/bin/python3
"""OpenAI TTS client for audio generation."""

import array
import base64
import io
import json
import math
import subprocess
import shutil
import sys
import wave
import logging
import time
from pathlib import Path
from typing import Any, Optional

import requests

import clients.lib
from clients.keys import load_key
from langtools.dialect_overrides import (
    get_dialect_display_name,
    get_parent_language,
    get_translation_language,
    normalize_language_code,
)

from clients.audio.types import AudioFormat, AudioGenerationResult, Voice

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Model configuration
DEFAULT_MODEL = "gpt-realtime-2.1-mini"
REALTIME_VOICES = frozenset(
    {"alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "marin", "cedar"}
)
API_BASE = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 60
MP3_BITRATE = "128k"

# Realtime output is 24 kHz mono signed 16-bit little-endian PCM.
PCM_SAMPLE_RATE = 24000
# Edge trimming: audio quieter than this (dBFS, per 10 ms frame) counts as silence,
# and at most this much of it is kept before the first and after the last loud frame.
# -50 dB catches the faint noise tails Realtime sometimes appends (seen at -50..-60 dB).
SILENCE_THRESHOLD_DB = -50.0
MAX_EDGE_SILENCE_MS = 100

# Pricing estimates (as of Jan 2025)
# gpt-4o-mini-tts: $0.60/1M input tokens, $12/1M output audio tokens
# Empirically ~300 bytes per audio token, ~4 chars per input token
BYTES_PER_AUDIO_TOKEN = 300
CHARS_PER_INPUT_TOKEN = 4
PRICE_PER_1M_INPUT_TOKENS = 0.60
PRICE_PER_1M_OUTPUT_TOKENS = 12.00

# Path to prompts directory (ROOT/prompts/audio/)
PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts" / "audio"

# Cache for loaded prompts
_prompt_cache: dict[tuple[str, str], str] = {}


def _load_prompt(prompt_type: str, language_code: str) -> str:
    """
    Load a prompt from file.

    A dialect uses its own file when one exists, then the file of the variety
    it reads, then its base language's.  The middle step matters: es-mx speaks
    es-419's text, and prompts/audio/word/es.txt asks for a *Castilian*
    accent, so falling straight back to the base language would instruct the
    wrong pronunciation of the very words being read.

    Args:
        prompt_type: Either "word" or "sentence"
        language_code: Language code (e.g., "lt", "zh", "es-419")

    Returns:
        The prompt text, or a default fallback if no file is found
    """
    language_code = normalize_language_code(language_code)
    cache_key = (prompt_type, language_code)
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    candidates = (
        language_code,
        get_translation_language(language_code),
        get_parent_language(language_code),
    )
    for candidate in candidates:
        prompt_file = PROMPTS_DIR / prompt_type / f"{candidate}.txt"
        if prompt_file.exists():
            prompt_text = prompt_file.read_text().strip()
            _prompt_cache[cache_key] = prompt_text
            return prompt_text

    # Fallback to default
    default_prompt = "Speak clearly and naturally."
    _prompt_cache[cache_key] = default_prompt
    return default_prompt


def get_instructions(language_code: str, is_sentence: bool = False) -> str:
    """
    Get TTS instructions for a language.

    Args:
        language_code: Language code (e.g., "lt", "zh")
        is_sentence: If True, use sentence-level prompt; otherwise use word-level

    Returns:
        The instruction text for TTS
    """
    prompt_type = "sentence" if is_sentence else "word"
    return _load_prompt(prompt_type, language_code)


def get_realtime_session_instructions(
    language_code: str, pronunciation_notes: str, is_sentence: bool = False
) -> str:
    """
    Frame a language's pronunciation notes as a Realtime recording session.

    Realtime is a conversational model, not a text reader: it pronounces words
    more reliably when told it is recording flashcard audio and handed each
    word as the next turn than when the word trails the instructions.

    Args:
        language_code: Language code (e.g., "lt", "es-mx")
        pronunciation_notes: The language's word or sentence prompt, plus any
            character description
        is_sentence: If True, frame a sentence session; otherwise a word session

    Returns:
        Session instructions for the Realtime session.update event
    """
    prompt_type = "sentence" if is_sentence else "word"
    template = (PROMPTS_DIR / "realtime" / f"{prompt_type}.txt").read_text().strip()
    return template.format(
        language=get_dialect_display_name(language_code),
        pronunciation_notes=pronunciation_notes,
    )


def trim_pcm_silence(
    data: bytes,
    threshold_db: float = SILENCE_THRESHOLD_DB,
    max_edge_ms: int = MAX_EDGE_SILENCE_MS,
    frame_ms: int = 10,
) -> bytes:
    """
    Trim leading and trailing silence from 24 kHz mono s16le PCM.

    Keeps at most max_edge_ms of the original audio before the first and after
    the last frame whose RMS reaches threshold_db (relative to full scale).
    Nothing is padded: an edge already shorter than max_edge_ms is left as is.

    Args:
        data: Raw PCM bytes
        threshold_db: Frames below this RMS level (dBFS) count as silence
        max_edge_ms: Most silence to keep at each end, in milliseconds
        frame_ms: Analysis frame length, in milliseconds

    Returns:
        The trimmed PCM bytes, or data unchanged if no frame is loud enough
    """
    samples = array.array("h")
    samples.frombytes(data[: len(data) - len(data) % 2])
    if sys.byteorder == "big":
        samples.byteswap()
    frame_len = PCM_SAMPLE_RATE * frame_ms // 1000
    threshold = 32768.0 * 10 ** (threshold_db / 20)
    loud_frames = [
        start
        for start in range(0, len(samples), frame_len)
        if math.sqrt(
            sum(s * s for s in samples[start : start + frame_len])
            / len(samples[start : start + frame_len])
        )
        >= threshold
    ]
    if not loud_frames:
        return data
    edge = PCM_SAMPLE_RATE * max_edge_ms // 1000
    first = max(0, loud_frames[0] - edge)
    last = min(len(samples), loud_frames[-1] + frame_len + edge)
    return data[first * 2 : last * 2]


def _encode_pcm(data: bytes, audio_format: AudioFormat, speed: float, timeout: int) -> bytes:
    """Encode 24 kHz mono signed 16-bit PCM; preserve the public format/speed contract."""
    if speed == 1.0:
        if audio_format == AudioFormat.PCM:
            return data
        if audio_format == AudioFormat.WAV:
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(24000)
                wav_file.writeframes(data)
            return buffer.getvalue()
    formats = {
        # Without -b:a, libmp3lame picks 32 kbps for 24 kHz mono, which sounds metallic.
        AudioFormat.MP3: ["-c:a", "libmp3lame", "-b:a", MP3_BITRATE, "-f", "mp3"],
        AudioFormat.OPUS: ["-c:a", "libopus", "-f", "ogg"],
        AudioFormat.AAC: ["-c:a", "aac", "-f", "adts"],
        AudioFormat.FLAC: ["-f", "flac"],
        AudioFormat.WAV: ["-f", "wav"],
        AudioFormat.PCM: ["-f", "s16le"],
    }
    # Chaining factors keeps compatibility with ffmpeg versions whose atempo range is 0.5–2.
    filters: list[str] = []
    factor = speed
    while factor < 0.5:
        filters.append("atempo=0.5")
        factor /= 0.5
    while factor > 2.0:
        filters.append("atempo=2.0")
        factor /= 2.0
    filters.append(f"atempo={factor}")
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-i",
            "pipe:0",
            "-af",
            ",".join(filters),
            *formats[audio_format],
            "pipe:1",
        ],
        input=data,
        capture_output=True,
        timeout=timeout,
        check=True,
    )
    return result.stdout


class OpenAITTSClient:
    """Client for generating audio using OpenAI TTS API."""

    def __init__(
        self, timeout: int = DEFAULT_TIMEOUT, debug: bool = False, api_key: Optional[str] = None
    ) -> None:
        """
        Initialize OpenAI TTS client.

        Args:
            timeout: Request timeout in seconds
            debug: Enable debug logging
        """
        self.timeout = timeout
        self.debug = debug
        if debug:
            logger.setLevel(logging.DEBUG)
            logger.debug("Initialized OpenAITTSClient in debug mode")

        self.api_key = api_key or load_key("openai", required=False)
        if self.api_key:
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        else:
            self.headers = {}

    def _generate_realtime(
        self,
        text: str,
        voice: Voice,
        model: str,
        instructions: str,
        audio_format: AudioFormat,
        speed: float,
        language_code: str,
        is_sentence: bool,
    ) -> bytes:
        """Collect GA Realtime PCM output and encode it for existing callers.

        The session is framed as a recording session (see
        get_realtime_session_instructions) and the text is sent as the next
        user turn, "Next word: ...", rather than appended to the instructions.
        """
        from websocket import create_connection

        if voice.value not in REALTIME_VOICES:
            raise ValueError(
                f"Voice {voice.value} is unavailable in Realtime; choose ash, alloy, or echo"
            )
        if not 0.25 <= speed <= 4.0:
            raise ValueError("Speed must be between 0.25 and 4.0")
        if (
            audio_format not in {AudioFormat.PCM, AudioFormat.WAV} or speed != 1.0
        ) and not shutil.which("ffmpeg"):
            raise ValueError("ffmpeg is required for encoded audio or speed adjustment")
        connection = create_connection(
            f"wss://api.openai.com/v1/realtime?model={model}",
            header={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.timeout,
        )
        unit = "sentence" if is_sentence else "word"
        deadline = time.monotonic() + self.timeout
        chunks: list[bytes] = []
        try:
            connection.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "realtime",
                            "instructions": get_realtime_session_instructions(
                                language_code, instructions, is_sentence
                            ),
                            "output_modalities": ["audio"],
                            "audio": {
                                "output": {
                                    "voice": voice.value,
                                    "format": {"type": "audio/pcm", "rate": 24000},
                                }
                            },
                        },
                    }
                )
            )
            requested = False
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Realtime TTS timed out")
                connection.settimeout(remaining)
                raw_event = connection.recv()
                if not raw_event:
                    raise ValueError("Realtime connection closed before response.done")
                event = json.loads(raw_event)
                event_type = event.get("type")
                if event_type == "error":
                    raise ValueError(f"Realtime TTS error: {event.get('error')}")
                if event_type == "session.updated" and not requested:
                    connection.send(
                        json.dumps(
                            {
                                "type": "response.create",
                                "response": {
                                    "conversation": "none",
                                    "input": [
                                        {
                                            "type": "message",
                                            "role": "user",
                                            "content": [
                                                {
                                                    "type": "input_text",
                                                    "text": f"Next {unit}: {text}",
                                                }
                                            ],
                                        }
                                    ],
                                    "output_modalities": ["audio"],
                                },
                            }
                        )
                    )
                    requested = True
                elif event_type == "response.output_audio.delta":
                    chunks.append(base64.b64decode(event["delta"], validate=True))
                elif event_type == "response.done":
                    response_data = event.get("response", {})
                    if response_data.get("status") != "completed":
                        raise ValueError(
                            f"Realtime TTS did not complete: {response_data.get('status_details')}"
                        )
                    break
        finally:
            connection.close()
        pcm_data = b"".join(chunks)
        if not pcm_data:
            raise ValueError("Realtime TTS returned no audio")
        return _encode_pcm(trim_pcm_silence(pcm_data), audio_format, speed, self.timeout)

    def generate_audio(
        self,
        text: str,
        voice: Voice = Voice.ALLOY,
        language_code: str = "lt",
        model: str = DEFAULT_MODEL,
        audio_format: AudioFormat = AudioFormat.MP3,
        speed: float = 1.0,
        is_sentence: bool = False,
        character_description: Optional[str] = None,
    ) -> AudioGenerationResult:
        """
        Generate audio from text using OpenAI TTS.

        Args:
            text: Text to convert to speech
            voice: Voice to use for generation
            language_code: Language code for pronunciation instructions
            model: TTS model to use
            audio_format: Output audio format
            speed: Speed of speech (0.25 to 4.0)
            is_sentence: If True, use sentence-level prompt for natural pacing
            character_description: Optional character persona to prepend to instructions

        Returns:
            AudioGenerationResult with audio data and metadata

        Raises:
            RuntimeError: If API key is not available
        """
        clients.lib.assert_llm_calls_enabled("openai-tts")

        # Check if API key is available
        if not self.api_key:
            raise RuntimeError("OpenAI API key not available. Please ensure the key file exists.")

        start_time = time.time()

        if self.debug:
            logger.debug(f"Generating audio for text: {text}")
            logger.debug(f"Voice: {voice.value}, Language: {language_code}")

        # Get language-specific instructions
        instructions = get_instructions(language_code, is_sentence=is_sentence)

        # Prepend character description if provided
        if character_description:
            instructions = f"{character_description}\n\n{instructions}"

        # Prepare request payload
        payload: dict[str, Any] = {
            "model": model,
            "input": text,
            "voice": voice.value,
            "response_format": audio_format.value,
            "instructions": instructions,
        }

        # Add speed if not default
        if speed != 1.0:
            payload["speed"] = speed

        try:
            if model.startswith("gpt-realtime"):
                audio_data = self._generate_realtime(
                    text,
                    voice,
                    model,
                    instructions,
                    audio_format,
                    speed,
                    language_code,
                    is_sentence,
                )
                return AudioGenerationResult(
                    audio_data=audio_data,
                    text=text,
                    voice=voice,
                    language_code=language_code,
                    model=model,
                    duration_ms=(time.time() - start_time) * 1000,
                )
            # Make API request
            url = f"{API_BASE}/audio/speech"

            # Log API call details
            logger.info(f"Making OpenAI TTS API call:")
            logger.info(f"  URL: {url}")
            logger.info(f"  Payload: {payload}")
            logger.info(f"  Timeout: {self.timeout}s")

            response = requests.post(url, headers=self.headers, json=payload, timeout=self.timeout)

            logger.info(f"API response status: {response.status_code}")

            if response.status_code != 200:
                error_msg = f"OpenAI TTS API error {response.status_code}: {response.text}"
                logger.error(error_msg)
                return AudioGenerationResult(
                    audio_data=b"",
                    text=text,
                    voice=voice,
                    language_code=language_code,
                    model=model,
                    duration_ms=0,
                    success=False,
                    error=error_msg,
                )

            duration_ms = (time.time() - start_time) * 1000
            audio_data = response.content

            # Log input/output sizes and estimated cost
            input_chars = len(text) + len(instructions)
            input_tokens_est = input_chars / CHARS_PER_INPUT_TOKEN
            output_tokens_est = len(audio_data) / BYTES_PER_AUDIO_TOKEN
            cost_est = (
                input_tokens_est * PRICE_PER_1M_INPUT_TOKENS
                + output_tokens_est * PRICE_PER_1M_OUTPUT_TOKENS
            ) / 1_000_000
            logger.info(
                f"TTS Complete - In: ~{input_tokens_est:.0f} tokens, Out: ~{output_tokens_est:.0f} tokens, Cost: ~${cost_est:.6f}, Time: {duration_ms:.0f}ms"
            )

            if self.debug:
                logger.debug(f"Generated {len(audio_data)} bytes in {duration_ms:.0f}ms")

            return AudioGenerationResult(
                audio_data=audio_data,
                text=text,
                voice=voice,
                language_code=language_code,
                model=model,
                duration_ms=duration_ms,
                success=True,
                error=None,
            )

        except Exception as e:
            error_msg = f"Error generating audio: {str(e)}"
            logger.error(error_msg)
            return AudioGenerationResult(
                audio_data=b"",
                text=text,
                voice=voice,
                language_code=language_code,
                model=model,
                duration_ms=0,
                success=False,
                error=error_msg,
            )


# Create default client instance
client = OpenAITTSClient(debug=False)


def generate_audio(
    text: str,
    voice: Voice = Voice.ALLOY,
    language_code: str = "lt",
    model: str = DEFAULT_MODEL,
    audio_format: AudioFormat = AudioFormat.MP3,
    speed: float = 1.0,
    is_sentence: bool = False,
    character_description: Optional[str] = None,
) -> AudioGenerationResult:
    """
    Generate audio from text using OpenAI TTS.

    Convenience function that uses the default client instance.

    Args:
        text: Text to convert to speech
        voice: Voice to use for generation
        language_code: Language code for pronunciation instructions
        model: TTS model to use
        audio_format: Output audio format
        speed: Speed of speech (0.25 to 4.0)
        is_sentence: If True, use sentence-level prompt for natural pacing
        character_description: Optional character persona to prepend to instructions

    Returns:
        AudioGenerationResult with audio data and metadata
    """
    return client.generate_audio(
        text,
        voice,
        language_code,
        model,
        audio_format,
        speed,
        is_sentence,
        character_description,
    )
