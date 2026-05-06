"""Typed wrappers for Barsukas JSON translation API endpoints."""

from dataclasses import dataclass

from api._http import HttpResult, send_request
from api._mirror import mirrored_route


@dataclass(frozen=True)
class GetLemmaTranslationsRequest:
    guid: str
    language: str = ""


@dataclass(frozen=True)
class TranslationResponse:
    result: HttpResult


@mirrored_route("/api/v1/lemma/<guid>/translations", "GET")
def get_lemma_translations(request_data: GetLemmaTranslationsRequest) -> TranslationResponse:
    return TranslationResponse(
        result=send_request(
            "GET",
            f"/api/v1/lemma/{request_data.guid}/translations",
            params={"language": request_data.language},
        )
    )
