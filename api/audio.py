"""Typed wrappers for Barsukas JSON audio API endpoints."""

from dataclasses import dataclass

from api._http import HttpResult, send_request
from api._mirror import mirrored_route


@dataclass(frozen=True)
class GetLemmaAudioRequest:
    guid: str
    language: str = ""


@dataclass(frozen=True)
class AudioResponse:
    result: HttpResult


@mirrored_route("/api/v1/lemma/<guid>/audio", "GET")
def get_lemma_audio(request_data: GetLemmaAudioRequest) -> AudioResponse:
    return AudioResponse(
        result=send_request(
            "GET",
            f"/api/v1/lemma/{request_data.guid}/audio",
            params={"language": request_data.language},
        )
    )
