from typing import Any, Dict
from pathlib import Path

import pytest

from agents.vieversys import _mark_failed_voices


def _results() -> Dict[str, Any]:
    return {"success": True, "lemma_guid": "N07_003", "voices": []}


def test_any_failed_voice_fails_the_item() -> None:
    results = _results()
    voice_results = [
        {"voice": "erinome", "success": True},
        {"voice": "iapetus", "success": False, "error": "Gemini TTS API error 429"},
    ]

    _mark_failed_voices(results, voice_results)

    assert results["success"] is False
    assert results["error"] == "Audio generation failed for voice(s): iapetus"


def test_skipped_and_generated_voices_leave_success() -> None:
    results = _results()
    voice_results = [
        {"voice": "erinome", "success": True, "skipped": True},
        {"voice": "iapetus", "success": True},
    ]

    _mark_failed_voices(results, voice_results)

    assert results["success"] is True
    assert "error" not in results


def test_upload_defaults_and_local_opt_out() -> None:
    from agents.vieversys import get_argument_parser

    parser = get_argument_parser()
    assert parser.parse_args([]).upload_s3 is True
    assert parser.parse_args(["--no-upload-s3"]).upload_s3 is False


def test_test_mode_never_initializes_uploader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import patch
    from agents.vieversys import VieversysAgent
    from storage.backend.config import DataSourceConfig

    monkeypatch.setenv("GREENLAND_TEST_MODE", "1")
    with patch("agents.vieversys.S3AudioUploader") as uploader:
        agent = VieversysAgent(DataSourceConfig(), output_dir=str(tmp_path))
    uploader.assert_not_called()
    assert agent.upload_s3 is False


def test_default_upload_initialization_failure_is_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import patch
    from agents.vieversys import VieversysAgent
    from storage.backend.config import DataSourceConfig

    monkeypatch.delenv("GREENLAND_TEST_MODE", raising=False)
    with patch("agents.vieversys.S3AudioUploader", side_effect=RuntimeError("unavailable")):
        with pytest.raises(RuntimeError, match="unavailable"):
            VieversysAgent(DataSourceConfig(), output_dir=str(tmp_path))


def test_staging_failure_is_reported_and_local_result_retained(tmp_path: Path) -> None:
    from unittest.mock import Mock, patch
    from agents.vieversys import VieversysAgent
    from clients.audio.gpt_voices import GptVoice
    from clients.audio.types import AudioGenerationResult, Voice
    from storage.backend.config import DataSourceConfig
    from storage.models.schema import Lemma

    agent = VieversysAgent(DataSourceConfig(), output_dir=str(tmp_path), upload_s3=False)
    agent.upload_s3 = True
    agent.s3_uploader = Mock()
    lemma = Lemma(guid="N06_001", lemma_text="bread", pos_type="noun")
    generated = AudioGenerationResult(
        audio_data=b"test-audio",
        text="pan",
        voice=Voice.CORAL,
        language_code="es-419",
        model="test",
        duration_ms=100,
    )
    with (
        patch.object(agent, "get_translation_text", return_value="pan"),
        patch("agents.vieversys.generate_audio", return_value=generated),
        patch.object(agent, "_upload_to_staging_path", return_value=(False, "", "")),
        patch.object(agent, "_create_review_record") as record,
    ):
        result = agent.generate_audio_for_lemma(Mock(), lemma, "es-419", [GptVoice.GPT_ES_F1])
    assert result["success"] is False
    assert result["voices"][0]["error"] == "S3 staging upload failed"
    assert Path(result["voices"][0]["file_path"]).read_bytes() == b"test-audio"
    record.assert_called_once()


def test_transcript_mismatch_is_recorded_as_needs_replacement(tmp_path: Path) -> None:
    import json
    from unittest.mock import Mock, patch
    from agents.vieversys import VieversysAgent
    from clients.audio.gpt_voices import GptVoice
    from clients.audio.types import AudioGenerationResult, Voice
    from storage.backend.config import DataSourceConfig
    from storage.models.schema import AudioQualityReview, Lemma

    agent = VieversysAgent(DataSourceConfig(), output_dir=str(tmp_path), upload_s3=False)
    agent.auto_approve = True
    lemma = Lemma(id=7, guid="N07_003", lemma_text="hospital", pos_type="noun")
    generated = AudioGenerationResult(
        audio_data=b"test-audio",
        text="ligoninė",
        voice=Voice.MARIN,
        language_code="lt",
        model="test",
        duration_ms=100,
        transcript="li-go-NI-ne",
        transcript_matches=False,
    )
    session = Mock()
    with (
        patch.object(agent, "get_translation_text", return_value="ligoninė"),
        patch("agents.vieversys.generate_audio", return_value=generated),
        patch("agents.vieversys.find_existing_review", return_value=None),
    ):
        result = agent.generate_audio_for_lemma(session, lemma, "lt", [GptVoice.GPT_LT_F1])

    assert result["voices"][0]["transcript_mismatch"] == "li-go-NI-ne"
    (review,) = [call.args[0] for call in session.add.call_args_list]
    assert isinstance(review, AudioQualityReview)
    # Even under --auto-approve a mismatched take is never served.
    assert review.status == "needs_replacement"
    assert review.accepted_at is None
    assert json.loads(review.quality_issues or "") == ["transcript_mismatch"]
    assert review.notes == "Realtime transcript: 'li-go-NI-ne'"
