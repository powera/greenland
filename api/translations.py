"""Typed wrappers for Barsukas translation routes."""

from dataclasses import dataclass

from api._http import HttpResult, send_request
from api._mirror import mirrored_route


@dataclass(frozen=True)
class UpdateTranslationRequest:
    lemma_id: int
    lang_code: str
    translation: str
    disambiguation: str = ""
    return_to: str = ""


@dataclass(frozen=True)
class TranslationResponse:
    result: HttpResult


@mirrored_route("/translations/<lemma_id>/<lang_code>", "POST")
def update_translation(request_data: UpdateTranslationRequest) -> TranslationResponse:
    """Delegate to Barsukas `POST /translations/<lemma_id>/<lang_code>` route."""
    return TranslationResponse(
        result=send_request(
            "POST",
            f"/translations/{request_data.lemma_id}/{request_data.lang_code}",
            form_data={
                "translation": request_data.translation,
                "disambiguation": request_data.disambiguation,
                "return_to": request_data.return_to,
            },
        )
    )
