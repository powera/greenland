"""HTTP facade for audio endpoints.

Lemma audio availability is currently a sub-resource of ``/api/v1/lemma/<guid>``
in the Barsukas API, so this module re-exports :func:`api.lemmas.get_audio`
and exists as the natural home for future standalone audio endpoints.

Mirrors ``src/barsukas/routes/api.py``. Any change to a route signature or
response shape there must be reflected here in the same commit.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict, cast

from api._http import get_json
from api._mirror import mirrored_route
from api.constants import API_V1_PREFIX
from api.lemmas import get_audio


class VoiceEntry(TypedDict):
    voice_name: str
    display_voice: str
    backend: str
    language_code: str
    gender: Optional[str]
    sample_url: Optional[str]


class VoicesResponse(TypedDict):
    data: List[VoiceEntry]
    metadata: Dict[str, Any]


@mirrored_route("/api/v1/audio/voices", "GET")
def list_voices(*, language: Optional[str] = None) -> VoicesResponse:
    """List available voices for one language or all languages.

    The ``backend`` field on each entry identifies the TTS engine
    ("openai", "polly", "azure", "google", "espeak"). OpenAI-backed voices
    are served by the ``vieversys`` agent (gpt-4o-mini-tts); see
    :func:`api.llm_agents.generate_audio`.
    """
    return cast(VoicesResponse, get_json(f"{API_V1_PREFIX}/audio/voices", {"language": language}))


__all__ = ["get_audio", "list_voices"]
