"""Typed wrappers for Barsukas LLM agent-trigger API routes."""

from dataclasses import dataclass

from api._http import HttpResult, send_request
from api._mirror import mirrored_route


@dataclass(frozen=True)
class AgentTriggerRequest:
    guid: str
    model: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""


@dataclass(frozen=True)
class PronunciationTriggerRequest(AgentTriggerRequest):
    lang_code: str = "en"


@dataclass(frozen=True)
class AgentTriggerResponse:
    result: HttpResult


@mirrored_route("/api/llm/voras/check-translations", "POST")
def check_translations(request_data: AgentTriggerRequest) -> AgentTriggerResponse:
    """Trigger Voras translation validation for one lemma GUID."""
    return AgentTriggerResponse(
        result=send_request(
            "POST",
            "/api/llm/voras/check-translations",
            json_data={
                "guid": request_data.guid,
                "model": request_data.model,
                "openai_api_key": request_data.openai_api_key,
                "anthropic_api_key": request_data.anthropic_api_key,
                "google_api_key": request_data.google_api_key,
            },
        )
    )


@mirrored_route("/api/llm/voras/add-missing-translations", "POST")
def add_missing_translations(request_data: AgentTriggerRequest) -> AgentTriggerResponse:
    """Trigger Voras generation of missing translations for one lemma GUID."""
    return AgentTriggerResponse(
        result=send_request(
            "POST",
            "/api/llm/voras/add-missing-translations",
            json_data={
                "guid": request_data.guid,
                "model": request_data.model,
                "openai_api_key": request_data.openai_api_key,
                "anthropic_api_key": request_data.anthropic_api_key,
                "google_api_key": request_data.google_api_key,
            },
        )
    )


@mirrored_route("/api/llm/papuga/generate-pronunciations", "POST")
def generate_pronunciations(
    request_data: PronunciationTriggerRequest,
) -> AgentTriggerResponse:
    """Trigger Papuga pronunciation generation for one lemma GUID."""
    return AgentTriggerResponse(
        result=send_request(
            "POST",
            "/api/llm/papuga/generate-pronunciations",
            json_data={
                "guid": request_data.guid,
                "lang_code": request_data.lang_code,
                "model": request_data.model,
                "openai_api_key": request_data.openai_api_key,
                "anthropic_api_key": request_data.anthropic_api_key,
                "google_api_key": request_data.google_api_key,
            },
        )
    )
