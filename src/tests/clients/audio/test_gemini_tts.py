#!/usr/bin/env python3
"""Tests for the Gemini 3.8 TTS client using mocked HTTP responses."""

import base64
from unittest.mock import MagicMock, Mock, patch

from clients.audio.gemini_tts import (
    GEMINI_38_FLASH_LITE_TTS,
    GEMINI_38_FLASH_TTS,
    GeminiTTSClient,
    GeminiTtsVoice,
)
from clients.audio.types import AudioFormat


def test_model_language_support() -> None:
    assert GeminiTtsVoice.get_voices_for_language("lt", GEMINI_38_FLASH_TTS)
    assert not GeminiTtsVoice.get_voices_for_language("lt", GEMINI_38_FLASH_LITE_TTS)
    assert GeminiTtsVoice.get_voices_for_language("es-mx", GEMINI_38_FLASH_TTS)
    assert GeminiTtsVoice.get_voices_for_language("zh", GEMINI_38_FLASH_LITE_TTS)


def test_model_qualified_voice_round_trip() -> None:
    storage_name = GeminiTtsVoice.KORE.storage_name(GEMINI_38_FLASH_TTS)
    assert storage_name == "gemini-3.8-flash-tts-kore"
    assert GeminiTtsVoice.from_identifier(storage_name) is GeminiTtsVoice.KORE


@patch("clients.audio.gemini_tts.clients.lib.assert_llm_calls_enabled")
@patch("clients.audio.gemini_tts.requests.post")
def test_generate_audio_success(mock_post: MagicMock, mock_guard: MagicMock) -> None:
    audio_bytes = b"mock mp3 audio"
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
                        "mime_type": "audio/mp3",
                    }
                ],
            }
        ],
    }
    mock_post.return_value = mock_response

    client = GeminiTTSClient(api_key="test-key")
    result = client.generate_audio(
        text="Hola",
        voice=GeminiTtsVoice.KORE,
        language_code="es-mx",
        model=GEMINI_38_FLASH_TTS,
        audio_format=AudioFormat.MP3,
    )

    assert result.success
    assert result.audio_data == audio_bytes
    assert result.model == GEMINI_38_FLASH_TTS
    mock_guard.assert_called_once_with("gemini-tts")
    request_payload = mock_post.call_args.kwargs["json"]
    assert request_payload["response_format"] == {
        "type": "audio",
        "mime_type": "audio/mp3",
    }
    assert request_payload["generation_config"]["speech_config"] == [{"voice": "Kore"}]
    annotation = request_payload["input"][0]["content"][0]["annotations"][0]
    assert "Mexican" in annotation["style"]
    assert request_payload["store"] is False


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
