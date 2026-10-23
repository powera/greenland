#!/usr/bin/env python3
"""
Tests for OpenAI TTS client.

These tests verify the audio generation client works correctly.
"""

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.audio.openai_tts import DEFAULT_MODEL, OpenAITTSClient
from clients.audio.types import AudioFormat, AudioGenerationResult, Voice


class TestOpenAITTSClient(unittest.TestCase):
    """Test OpenAI TTS client functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock the API key loading
        self.mock_api_key = "sk-test-key-123"

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled", return_value=None)
    @patch("clients.audio.openai_tts.requests.post")
    @patch("clients.audio.openai_tts.load_key")
    def test_generate_audio_success(
        self, mock_load_key: MagicMock, mock_post: MagicMock, mock_guard: MagicMock
    ) -> None:
        """Test successful audio generation."""
        mock_load_key.return_value = self.mock_api_key

        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()
        result = client.generate_audio(
            text="labas", voice=Voice.ASH, language_code="lt", model="gpt-4o-mini-tts"
        )

        # Verify result
        self.assertTrue(result.success)
        self.assertEqual(result.audio_data, b"fake audio data")
        self.assertEqual(result.text, "labas")
        self.assertEqual(result.voice, Voice.ASH)
        self.assertEqual(result.language_code, "lt")
        self.assertIsNone(result.error)

        # Verify API was called correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("json", call_args.kwargs)
        payload = call_args.kwargs["json"]
        # Explicit legacy models keep using the speech endpoint.
        self.assertEqual(payload["model"], "gpt-4o-mini-tts")
        self.assertEqual(DEFAULT_MODEL, "gpt-realtime-2.1-mini")
        self.assertEqual(payload["input"], "labas")
        self.assertEqual(payload["voice"], "ash")
        self.assertIn("instructions", payload)

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled", return_value=None)
    @patch("clients.audio.openai_tts.requests.post")
    @patch("clients.audio.openai_tts.load_key")
    def test_generate_audio_api_error(
        self, mock_load_key: MagicMock, mock_post: MagicMock, mock_guard: MagicMock
    ) -> None:
        """Test handling of API errors."""
        mock_load_key.return_value = self.mock_api_key

        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()
        result = client.generate_audio(
            text="labas", voice=Voice.ASH, language_code="lt", model="gpt-4o-mini-tts"
        )

        # Verify error handling
        self.assertFalse(result.success)
        self.assertEqual(result.audio_data, b"")
        self.assertIsNotNone(result.error)
        assert result.error is not None
        self.assertIn("429", result.error)

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled", return_value=None)
    @patch("clients.audio.openai_tts.requests.post")
    @patch("clients.audio.openai_tts.load_key")
    def test_generate_audio_with_speed(
        self, mock_load_key: MagicMock, mock_post: MagicMock, mock_guard: MagicMock
    ) -> None:
        """Test audio generation with custom speed."""
        mock_load_key.return_value = self.mock_api_key

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()
        result = client.generate_audio(
            text="labas", voice=Voice.NOVA, language_code="lt", speed=0.75, model="gpt-4o-mini-tts"
        )

        # Verify speed parameter was included
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["speed"], 0.75)

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled", return_value=None)
    @patch("clients.audio.openai_tts.requests.post")
    @patch("clients.audio.openai_tts.load_key")
    def test_language_specific_instructions(
        self, mock_load_key: MagicMock, mock_post: MagicMock, mock_guard: MagicMock
    ) -> None:
        """Test that language-specific instructions are used."""
        mock_load_key.return_value = self.mock_api_key

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()

        # Test Lithuanian
        result = client.generate_audio(text="labas", language_code="lt", model="gpt-4o-mini-tts")
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertIn("Lithuanian", payload["instructions"])

        # Test Chinese
        mock_post.reset_mock()
        result = client.generate_audio(text="你好", language_code="zh", model="gpt-4o-mini-tts")
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertIn("Chinese", payload["instructions"])

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled", return_value=None)
    @patch("clients.audio.openai_tts.requests.post")
    @patch("clients.audio.openai_tts.load_key")
    def test_audio_format_parameter(
        self, mock_load_key: MagicMock, mock_post: MagicMock, mock_guard: MagicMock
    ) -> None:
        """Test different audio format options."""
        mock_load_key.return_value = self.mock_api_key

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"fake audio data"
        mock_post.return_value = mock_response

        client = OpenAITTSClient()

        # Test MP3 format (default)
        result = client.generate_audio(
            text="test", audio_format=AudioFormat.MP3, model="gpt-4o-mini-tts"
        )
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], "mp3")

        # Test WAV format
        mock_post.reset_mock()
        result = client.generate_audio(
            text="test", audio_format=AudioFormat.WAV, model="gpt-4o-mini-tts"
        )
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        self.assertEqual(payload["response_format"], "wav")

    def test_voice_enum_values(self) -> None:
        """Test that Voice enum has correct values."""
        self.assertEqual(Voice.ASH.value, "ash")
        self.assertEqual(Voice.ALLOY.value, "alloy")
        self.assertEqual(Voice.NOVA.value, "nova")
        self.assertEqual(Voice.ONYX.value, "onyx")

    def test_audio_format_enum_values(self) -> None:
        """Test that AudioFormat enum has correct values."""
        self.assertEqual(AudioFormat.MP3.value, "mp3")
        self.assertEqual(AudioFormat.WAV.value, "wav")
        self.assertEqual(AudioFormat.OPUS.value, "opus")


class TestAudioGenerationResult(unittest.TestCase):
    """Test AudioGenerationResult dataclass."""

    def test_successful_result(self) -> None:
        """Test creating a successful result."""
        result = AudioGenerationResult(
            audio_data=b"test data",
            text="test text",
            voice=Voice.ASH,
            language_code="lt",
            model="gpt-4o-mini-tts",
            duration_ms=1500.0,
            success=True,
            error=None,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.audio_data, b"test data")
        self.assertEqual(result.text, "test text")
        self.assertEqual(result.voice, Voice.ASH)
        self.assertIsNone(result.error)

    def test_error_result(self) -> None:
        """Test creating an error result."""
        result = AudioGenerationResult(
            audio_data=b"",
            text="test text",
            voice=Voice.ASH,
            language_code="lt",
            model="gpt-4o-mini-tts",
            duration_ms=0,
            success=False,
            error="API error",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.audio_data, b"")
        self.assertEqual(result.error, "API error")


if __name__ == "__main__":
    unittest.main()


class TestRealtimeTTS(unittest.TestCase):
    """Exercise streamed GA events without credentials or outbound calls."""

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled")
    @patch("websocket.create_connection")
    def test_stream_and_wav(self, mock_connect: MagicMock, mock_guard: MagicMock) -> None:
        import base64
        import io
        import json
        import wave

        pcm = _pcm(_tone(50))
        connection = mock_connect.return_value
        connection.recv.side_effect = [
            json.dumps({"type": "session.created"}),
            json.dumps({"type": "session.updated"}),
            json.dumps(
                {"type": "response.output_audio.delta", "delta": base64.b64encode(pcm).decode()}
            ),
            json.dumps({"type": "response.done", "response": {"status": "completed"}}),
        ]
        result = OpenAITTSClient(api_key="fake").generate_audio(
            "labas",
            voice=Voice.ASH,
            audio_format=AudioFormat.WAV,
            character_description="A calm speaker",
        )
        self.assertTrue(result.success, result.error)
        with wave.open(io.BytesIO(result.audio_data), "rb") as wav_file:
            self.assertEqual(wav_file.getframerate(), 24000)
            self.assertEqual(wav_file.readframes(_ms(50)), pcm)
        events = [json.loads(call.args[0]) for call in connection.send.call_args_list]
        session = events[0]["session"]
        self.assertEqual(session["audio"]["output"]["voice"], "ash")
        self.assertIn("native Lithuanian speaker", session["instructions"])
        self.assertIn("A calm speaker", session["instructions"])
        self.assertNotIn("labas", session["instructions"])
        self.assertNotIn("instructions", events[1]["response"])
        (message,) = events[1]["response"]["input"]
        self.assertEqual(message["role"], "user")
        self.assertEqual(message["content"][0]["text"], "Next word: labas")
        self.assertIn(DEFAULT_MODEL, mock_connect.call_args.args[0])
        connection.close.assert_called_once()

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled")
    @patch("websocket.create_connection")
    def test_failed_streams(self, mock_connect: MagicMock, mock_guard: MagicMock) -> None:
        import json

        for terminal in [
            {"type": "error", "error": {"message": "bad request"}},
            {"type": "response.done", "response": {"status": "incomplete"}},
            {"type": "response.done", "response": {"status": "completed"}},
        ]:
            with self.subTest(terminal=terminal):
                connection = mock_connect.return_value
                connection.reset_mock()
                connection.recv.side_effect = [json.dumps(terminal)]
                result = OpenAITTSClient(api_key="fake").generate_audio("labas")
                self.assertFalse(result.success)
                self.assertEqual(result.audio_data, b"")
                connection.close.assert_called_once()

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled")
    @patch("websocket.create_connection")
    def test_unsupported_voice(self, mock_connect: MagicMock, mock_guard: MagicMock) -> None:
        result = OpenAITTSClient(api_key="fake").generate_audio("labas", voice=Voice.NOVA)
        self.assertFalse(result.success)
        mock_connect.assert_not_called()

    @patch("websocket.create_connection")
    def test_kill_switch(self, mock_connect: MagicMock) -> None:
        from clients.lib import LLMCallsDisabledError

        with self.assertRaises(LLMCallsDisabledError):
            OpenAITTSClient(api_key="fake").generate_audio("labas")
        mock_connect.assert_not_called()

    @patch("clients.audio.openai_tts.subprocess.run")
    def test_transcode_speed(self, mock_run: MagicMock) -> None:
        from clients.audio.openai_tts import _encode_pcm

        mock_run.return_value.stdout = b"mp3"
        self.assertEqual(_encode_pcm(b"\x00\x00", AudioFormat.MP3, 0.25, 60), b"mp3")
        command = mock_run.call_args.args[0]
        self.assertIn("atempo=0.5,atempo=0.5", command)
        self.assertIn("libmp3lame", command)
        self.assertEqual(command[command.index("-b:a") + 1], "128k")
        self.assertEqual(mock_run.call_args.kwargs["input"], b"\x00\x00")

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled")
    @patch("websocket.create_connection")
    def test_realtime_output_is_trimmed(
        self, mock_connect: MagicMock, mock_guard: MagicMock
    ) -> None:
        import base64
        import json

        pcm = _pcm(_tone(300) + _quiet(2000))
        mock_connect.return_value.recv.side_effect = [
            json.dumps({"type": "session.updated"}),
            json.dumps(
                {"type": "response.output_audio.delta", "delta": base64.b64encode(pcm).decode()}
            ),
            json.dumps({"type": "response.done", "response": {"status": "completed"}}),
        ]
        result = OpenAITTSClient(api_key="fake").generate_audio(
            "vanduo", voice=Voice.SHIMMER, audio_format=AudioFormat.PCM
        )
        self.assertTrue(result.success, result.error)
        self.assertEqual(len(result.audio_data), len(_pcm(_tone(300) + _quiet(100))))

    @patch("clients.audio.openai_tts.clients.lib.assert_llm_calls_enabled")
    @patch("websocket.create_connection")
    def test_completed_but_silent_response_rejected(
        self, mock_connect: MagicMock, mock_guard: MagicMock
    ) -> None:
        import base64
        import json

        mock_connect.return_value.recv.side_effect = [
            json.dumps({"type": "session.updated"}),
            json.dumps(
                {
                    "type": "response.output_audio.delta",
                    "delta": base64.b64encode(_pcm(_quiet(4100))).decode(),
                }
            ),
            json.dumps({"type": "response.done", "response": {"status": "completed"}}),
        ]
        result = OpenAITTSClient(api_key="fake").generate_audio("pan")
        self.assertFalse(result.success)
        self.assertEqual(result.audio_data, b"")
        self.assertIn("insufficient audible audio", result.error or "")
        mock_connect.return_value.close.assert_called_once()


def _ms(ms: int) -> int:
    """Sample count for ms of 24 kHz audio."""
    return 24000 * ms // 1000


def _tone(ms: int) -> list[int]:
    """A loud square wave, well above the silence threshold."""
    return [8000 if i % 40 < 20 else -8000 for i in range(_ms(ms))]


def _quiet(ms: int, level: int = 30) -> list[int]:
    """Faint noise at about -61 dBFS, below the -50 dB threshold but not zero."""
    return [level if i % 2 else -level for i in range(_ms(ms))]


def _pcm(samples: list[int]) -> bytes:
    import array

    data = array.array("h", samples)
    if sys.byteorder == "big":
        data.byteswap()
    return data.tobytes()


class TestAudibleAudio(unittest.TestCase):
    def test_duration_excludes_quiet_gaps_and_counts_partial_frame(self) -> None:
        from clients.audio.openai_tts import audible_pcm_duration_ms

        self.assertEqual(audible_pcm_duration_ms(_pcm(_tone(20) + _quiet(100) + _tone(25))), 45)

    def test_minimum_boundaries(self) -> None:
        from clients.audio.openai_tts import validate_pcm_audio

        for text, minimum_ms in [("bread", 50), ("I", 30), ("pan", 30), ("a b", 50)]:
            with self.subTest(text=text):
                validate_pcm_audio(_pcm(_tone(minimum_ms)), text)
                with self.assertRaisesRegex(ValueError, "insufficient audible audio"):
                    validate_pcm_audio(_pcm(_tone(minimum_ms - 10)), text)
                with self.assertRaises(ValueError):
                    validate_pcm_audio(_pcm(_quiet(4100)), text)


class TestTrimPcmSilence(unittest.TestCase):
    """Edge trimming keeps at most 100 ms of silence at each end."""

    def test_long_edges_trimmed_to_limit(self) -> None:
        from clients.audio.openai_tts import trim_pcm_silence

        trimmed = trim_pcm_silence(_pcm(_quiet(500) + _tone(300) + _quiet(3300)))
        self.assertEqual(trimmed, _pcm(_quiet(100) + _tone(300) + _quiet(100)))

    def test_short_edges_kept_without_padding(self) -> None:
        from clients.audio.openai_tts import trim_pcm_silence

        pcm = _pcm(_quiet(40) + _tone(300) + _quiet(60))
        self.assertEqual(trim_pcm_silence(pcm), pcm)

    def test_all_quiet_returned_unchanged(self) -> None:
        from clients.audio.openai_tts import trim_pcm_silence

        pcm = _pcm(_quiet(1000))
        self.assertEqual(trim_pcm_silence(pcm), pcm)
