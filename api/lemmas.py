"""Typed wrappers for Barsukas lemma routes."""

from dataclasses import dataclass

from api._http import HttpResult, send_request


@dataclass(frozen=True)
class ListLemmasRequest:
    page: int = 1
    search: str = ""
    pos_type: str = ""
    pos_subtype: str = ""
    difficulty: str = ""


@dataclass(frozen=True)
class LemmasResponse:
    result: HttpResult


def list_lemmas(request_data: ListLemmasRequest) -> LemmasResponse:
    """Delegate to Barsukas `GET /lemmas/` list route."""
    return LemmasResponse(
        result=send_request(
            "GET",
            "/lemmas/",
            params={
                "page": request_data.page,
                "search": request_data.search,
                "pos_type": request_data.pos_type,
                "pos_subtype": request_data.pos_subtype,
                "difficulty": request_data.difficulty,
            },
        )
    )
