"""Typed wrappers for Barsukas JSON lemma API endpoints."""

from dataclasses import dataclass

from api._http import HttpResult, send_request
from api._mirror import mirrored_route


@dataclass(frozen=True)
class SearchLemmasRequest:
    query: str
    pos_type: str = ""
    difficulty: str = ""
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True)
class GetLemmaRequest:
    guid: str


@dataclass(frozen=True)
class LemmasResponse:
    result: HttpResult


@mirrored_route("/api/v1/search", "GET")
def search_lemmas(request_data: SearchLemmasRequest) -> LemmasResponse:
    return LemmasResponse(
        result=send_request(
            "GET",
            "/api/v1/search",
            params={
                "q": request_data.query,
                "pos_type": request_data.pos_type,
                "difficulty": request_data.difficulty,
                "limit": request_data.limit,
                "offset": request_data.offset,
            },
        )
    )


@mirrored_route("/api/v1/lemma/<guid>", "GET")
def get_lemma(request_data: GetLemmaRequest) -> LemmasResponse:
    return LemmasResponse(result=send_request("GET", f"/api/v1/lemma/{request_data.guid}"))
