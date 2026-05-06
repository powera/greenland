"""Typed wrappers for Barsukas JSON sentence API endpoints."""

from dataclasses import dataclass

from api._http import HttpResult, send_request
from api._mirror import mirrored_route


@dataclass(frozen=True)
class GetLemmaSentencesRequest:
    guid: str
    language: str = ""


@dataclass(frozen=True)
class SentencesResponse:
    result: HttpResult


@mirrored_route("/api/v1/lemma/<guid>/sentences", "GET")
def get_lemma_sentences(request_data: GetLemmaSentencesRequest) -> SentencesResponse:
    return SentencesResponse(
        result=send_request(
            "GET",
            f"/api/v1/lemma/{request_data.guid}/sentences",
            params={"language": request_data.language},
        )
    )
