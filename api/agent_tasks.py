from __future__ import annotations

from typing import Any, Dict, List, TypedDict, cast

from api._http import post_json
from api._mirror import mirrored_route


class CheckData(TypedDict):
    status: str
    issues: List[Any]
    confidence_summary: Dict[str, Any]


class CheckResponse(TypedDict):
    data: CheckData
    metadata: Dict[str, Any]


@mirrored_route("/api/v1/agents/lemma/<guid>/add-missing-translations", "POST")
def queue_add_missing_translations(
    guid: str,
    *,
    model: str,
    batch: bool = False,
    batch_window_minutes: int = 10,
) -> CheckResponse:
    return cast(
        CheckResponse,
        post_json(
            f"/api/v1/agents/lemma/{guid}/add-missing-translations",
            {
                "model": model,
                "batch": batch,
                "batch_window_minutes": batch_window_minutes,
            },
        ),
    )


@mirrored_route("/api/v1/agents/lemma/<guid>/generate-pronunciations", "POST")
def queue_generate_pronunciations(
    guid: str,
    *,
    model: str,
    lang_code: str = "en",
    batch: bool = False,
    batch_window_minutes: int = 10,
) -> CheckResponse:
    return cast(
        CheckResponse,
        post_json(
            f"/api/v1/agents/lemma/{guid}/generate-pronunciations",
            {
                "model": model,
                "lang_code": lang_code,
                "batch": batch,
                "batch_window_minutes": batch_window_minutes,
            },
        ),
    )


@mirrored_route("/api/v1/agents/lemma/<guid>/generate-forms", "POST")
def queue_generate_forms(
    guid: str,
    *,
    model: str,
    lang_code: str = "lt",
    batch: bool = False,
    batch_window_minutes: int = 10,
) -> CheckResponse:
    return cast(
        CheckResponse,
        post_json(
            f"/api/v1/agents/lemma/{guid}/generate-forms",
            {
                "model": model,
                "lang_code": lang_code,
                "batch": batch,
                "batch_window_minutes": batch_window_minutes,
            },
        ),
    )


@mirrored_route("/api/v1/agents/lemma/<guid>/generate-synonyms", "POST")
def queue_generate_synonyms(
    guid: str,
    *,
    model: str,
    lang_code: str = "en",
    batch: bool = False,
    batch_window_minutes: int = 10,
) -> CheckResponse:
    return cast(
        CheckResponse,
        post_json(
            f"/api/v1/agents/lemma/{guid}/generate-synonyms",
            {
                "model": model,
                "lang_code": lang_code,
                "batch": batch,
                "batch_window_minutes": batch_window_minutes,
            },
        ),
    )


@mirrored_route("/api/v1/agents/lemma/<guid>/check-definition", "POST")
def check_definition(guid: str, *, model: str) -> CheckResponse:
    return cast(
        CheckResponse, post_json(f"/api/v1/agents/lemma/{guid}/check-definition", {"model": model})
    )


@mirrored_route("/api/v1/agents/lemma/<guid>/check-disambiguation", "POST")
def check_disambiguation(guid: str, *, model: str) -> CheckResponse:
    return cast(
        CheckResponse,
        post_json(f"/api/v1/agents/lemma/{guid}/check-disambiguation", {"model": model}),
    )


@mirrored_route("/api/v1/agents/lemma/<guid>/check-translations", "POST")
def check_translations(guid: str, *, model: str) -> CheckResponse:
    return cast(
        CheckResponse,
        post_json(f"/api/v1/agents/lemma/{guid}/check-translations", {"model": model}),
    )


@mirrored_route("/api/v1/agents/lemma/<guid>/check-pronunciations", "POST")
def check_pronunciations(guid: str, *, model: str) -> CheckResponse:
    return cast(
        CheckResponse,
        post_json(f"/api/v1/agents/lemma/{guid}/check-pronunciations", {"model": model}),
    )


@mirrored_route("/api/v1/tasks/<task_id>", "GET")
def get_task(task_id: int) -> Dict[str, Any]:
    """Get queued/running/completed task status and result fields."""
    from api._http import get_json

    return cast(Dict[str, Any], get_json(f"/api/v1/tasks/{task_id}"))
