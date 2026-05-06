"""Typed wrappers for Barsukas audio routes."""

from dataclasses import dataclass

from api._http import HttpResult, send_request


@dataclass(frozen=True)
class ListAudioFilesRequest:
    page: int = 1
    status: str = ""
    language_code: str = ""
    voice_name: str = ""


@dataclass(frozen=True)
class AudioResponse:
    result: HttpResult


def list_audio_files(request_data: ListAudioFilesRequest) -> AudioResponse:
    """Delegate to Barsukas `GET /audio/list` route."""
    return AudioResponse(
        result=send_request(
            "GET",
            "/audio/list",
            params={
                "page": request_data.page,
                "status": request_data.status,
                "language_code": request_data.language_code,
                "voice_name": request_data.voice_name,
            },
        )
    )
