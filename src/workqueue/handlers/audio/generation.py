"""Capability handlers for audio generation tasks."""

from __future__ import annotations

from typing import Any, List, Optional

from workqueue.handlers.vieversys import handle_generate_audio, handle_generate_sentence_audio


def do_generate_lemma_audio(
    session: Any,
    lemma_id: int,
    language_code: str,
    voices: Optional[List[str]] = None,
    tts_engine: str = "openai",
    use_ipa: bool = False,
    **_: Any,
) -> str:
    """Generate audio for a lemma."""
    payload = {
        "lemma_id": lemma_id,
        "language_code": language_code,
        "voices": voices or ["ash", "alloy", "nova"],
        "tts_engine": tts_engine,
        "use_ipa": use_ipa,
    }
    return handle_generate_audio(session, payload)


def do_generate_sentence_audio(
    session: Any,
    sentence_id: int,
    language_code: str,
    voices: Optional[List[str]] = None,
    tts_engine: str = "openai",
    use_ipa: bool = False,
    **_: Any,
) -> str:
    """Generate audio for a sentence."""
    payload = {
        "sentence_id": sentence_id,
        "language_code": language_code,
        "voices": voices or ["ash", "alloy", "nova"],
        "tts_engine": tts_engine,
        "use_ipa": use_ipa,
    }
    return handle_generate_sentence_audio(session, payload)


def handle_audio_generate_lemma(session: Any, payload: dict[str, Any]) -> str:
    """Workqueue wrapper for lemma audio generation."""
    return do_generate_lemma_audio(session=session, **payload)


def handle_audio_generate_sentence(session: Any, payload: dict[str, Any]) -> str:
    """Workqueue wrapper for sentence audio generation."""
    return do_generate_sentence_audio(session=session, **payload)
