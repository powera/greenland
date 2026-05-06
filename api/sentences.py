"""Typed wrappers for Barsukas sentence routes."""

from dataclasses import dataclass

from api._http import HttpResult, send_request
from api._mirror import mirrored_route


@dataclass(frozen=True)
class ListSentencesRequest:
    page: int = 1
    search: str = ""
    pattern_type: str = ""
    minimum_level: str = ""
    has_translation: str = ""
    exclude_rejected: str = "no"
    exclude_verified: str = "no"


@dataclass(frozen=True)
class SentencesResponse:
    result: HttpResult


@mirrored_route("/sentences/", "GET")
def list_sentences(request_data: ListSentencesRequest) -> SentencesResponse:
    """Delegate to Barsukas `GET /sentences/` list route."""
    return SentencesResponse(
        result=send_request(
            "GET",
            "/sentences/",
            params={
                "page": request_data.page,
                "search": request_data.search,
                "pattern_type": request_data.pattern_type,
                "minimum_level": request_data.minimum_level,
                "has_translation": request_data.has_translation,
                "exclude_rejected": request_data.exclude_rejected,
                "exclude_verified": request_data.exclude_verified,
            },
        )
    )
