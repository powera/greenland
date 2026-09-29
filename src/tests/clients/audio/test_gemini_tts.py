#!/usr/bin/env python3
"""Tests for the Gemini 3.8 TTS client using mocked HTTP responses."""

import base64
from unittest.mock import MagicMock, Mock, patch

from clients.audio.gemini_tts import (
    GEMINI_38_FLASH_LITE_TTS,
    GEMINI_38_FLASH_TTS,
    MAX_RATE_LIMIT_RETRIES,
    GeminiTTSClient,
    GeminiTtsVoice,
)
from clients.audio.types import AudioFormat


def test_model_language_support() -> None:
    assert GeminiTtsVoice.get_voices_for_language("lt", GEMINI_38_FLASH_TTS)
    assert not GeminiTtsVoice.get_voices_for_language("lt", GEMINI_38_FLASH_LITE_TTS)
    assert GeminiTtsVoice.get_voices_for_language("es-mx", GEMINI_38_FLASH_TTS)
    assert GeminiTtsVoice.get_voices_for_language("zh", GEMINI_38_FLASH_LITE_TTS)


def test_engine_qualified_voice_round_trip() -> None:
    storage_name = GeminiTtsVoice.KORE.storage_name
    assert storage_name == "kore"
    assert GeminiTtsVoice.from_identifier(storage_name) is GeminiTtsVoice.KORE


@patch("clients.audio.gemini_tts.load_key", return_value="fake-gemini-key")
def test_default_key_is_gemini_not_google(mock_load_key: MagicMock) -> None:
    client = GeminiTTSClient()
    mock_load_key.assert_called_once_with("gemini", required=False)
    assert client.api_key == "fake-gemini-key"


def _audio_response(audio_bytes: bytes) -> Mock:
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "completed",
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "audio",
                        "data": base64.b64encode(audio_bytes).decode("ascii"),
                        "mime_type": "audio/wav",
                    }
                ],
            }
        ],
    }
    return mock_response


def _rate_limited_response() -> Mock:
    mock_response = Mock()
    mock_response.status_code = 429
    mock_response.text = (
        '{"error":{"message":"Rate limit exceeded for model gemini-3.8-flash-tts '
        '(limit: 10 requests per minute on Tier 1). Please retry in 53s."}}'
    )
    return mock_response


@patch("clients.audio.gemini_tts._transcode_wav", return_value=b"mock mp3 audio")
@patch("clients.audio.gemini_tts.clients.lib.assert_llm_calls_enabled")
@patch("clients.audio.gemini_tts.requests.post")
def test_generate_audio_success(
    mock_post: MagicMock, mock_guard: MagicMock, mock_transcode: MagicMock
) -> None:
    mock_post.return_value = _audio_response(b"mock wav audio")

    client = GeminiTTSClient(api_key="test-key")
    result = client.generate_audio(
        text="Hola",
        voice=GeminiTtsVoice.KORE,
        language_code="es-mx",
        model=GEMINI_38_FLASH_TTS,
        audio_format=AudioFormat.MP3,
    )

    assert result.success
    assert result.audio_data == b"mock mp3 audio"
    assert mock_transcode.call_args.args[0] == b"mock wav audio"
    assert result.model == GEMINI_38_FLASH_TTS
    mock_guard.assert_called_once_with("gemini-tts")
    request_payload = mock_post.call_args.kwargs["json"]
    assert request_payload["response_format"] == {
        "type": "audio",
        "mime_type": "audio/wav",
    }
    assert request_payload["generation_config"]["speech_config"] == [{"voice": "Kore"}]
    annotation = request_payload["input"][0]["content"][0]["annotations"][0]
    assert "Mexican" in annotation["style"]
    assert request_payload["store"] is False


@patch("clients.audio.gemini_tts._transcode_wav")
@patch("clients.audio.gemini_tts.clients.lib.assert_llm_calls_enabled")
@patch("clients.audio.gemini_tts.requests.post")
def test_wav_output_is_not_transcoded(
    mock_post: MagicMock, mock_guard: MagicMock, mock_transcode: MagicMock
) -> None:
    mock_post.return_value = _audio_response(b"mock wav audio")

    client = GeminiTTSClient(api_key="test-key")
    result = client.generate_audio(text="Hola", audio_format=AudioFormat.WAV)

    assert result.success
    assert result.audio_data == b"mock wav audio"
    mock_transcode.assert_not_called()


@patch("clients.audio.gemini_tts.subprocess.run")
@patch("clients.audio.gemini_tts.clients.lib.assert_llm_calls_enabled")
@patch("clients.audio.gemini_tts.requests.post")
def test_failed_transcode_is_an_error_result(
    mock_post: MagicMock, mock_guard: MagicMock, mock_run: MagicMock
) -> None:
    mock_post.return_value = _audio_response(b"mock wav audio")
    mock_run.return_value = Mock(returncode=1, stdout=b"", stderr=b"Invalid data found")

    client = GeminiTTSClient(api_key="test-key")
    result = client.generate_audio(text="Hola", audio_format=AudioFormat.MP3)

    assert not result.success
    assert "Invalid data found" in (result.error or "")


@patch("clients.audio.gemini_tts.time.sleep")
@patch("clients.audio.gemini_tts._transcode_wav", return_value=b"mock mp3 audio")
@patch("clients.audio.gemini_tts.clients.lib.assert_llm_calls_enabled")
@patch("clients.audio.gemini_tts.requests.post")
def test_rate_limit_waits_the_requested_time_then_retries(
    mock_post: MagicMock,
    mock_guard: MagicMock,
    mock_transcode: MagicMock,
    mock_sleep: MagicMock,
) -> None:
    mock_post.side_effect = [_rate_limited_response(), _audio_response(b"mock wav audio")]

    client = GeminiTTSClient(api_key="test-key")
    result = client.generate_audio(text="Hola")

    assert result.success
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(54.0)


@patch("clients.audio.gemini_tts.time.sleep")
@patch("clients.audio.gemini_tts.clients.lib.assert_llm_calls_enabled")
@patch("clients.audio.gemini_tts.requests.post")
def test_rate_limit_gives_up_after_max_retries(
    mock_post: MagicMock, mock_guard: MagicMock, mock_sleep: MagicMock
) -> None:
    mock_post.return_value = _rate_limited_response()

    client = GeminiTTSClient(api_key="test-key")
    result = client.generate_audio(text="Hola")

    assert not result.success
    assert "429" in (result.error or "")
    assert mock_post.call_count == MAX_RATE_LIMIT_RETRIES + 1


def test_flash_lite_rejects_lithuanian_without_request() -> None:
    client = GeminiTTSClient(api_key="test-key")
    with patch("clients.audio.gemini_tts.requests.post") as mock_post:
        result = client.generate_audio(
            text="Labas",
            language_code="lt",
            model=GEMINI_38_FLASH_LITE_TTS,
        )

    assert not result.success
    assert "does not support" in (result.error or "")
    mock_post.assert_not_called()
