from typing import Any, Dict

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
