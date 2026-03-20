"""Personally Identifying Information detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "pii_detection"


class PIIDetectionAction(ActionBase):
    name = "pii_detection"
    display_name = "PII Detection"
    description = "Identify Personally Identifying Information in text"
    color_group = "violet"
    needs_context = False
    needs_target_language = False

    def build_prompt(
        self,
        text: str,
        context: Optional[str] = None,
        target_language: Optional[str] = None,
        session: Optional[Any] = None,
    ) -> Tuple[str, str]:
        system_context = util.prompt_loader.get_context(_PROMPT_CATEGORY, _PROMPT_TYPE)
        prompt = util.prompt_loader.get_prompt(_PROMPT_CATEGORY, _PROMPT_TYPE).format(
            text=text,
        )
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "has_pii": {
                    "type": "boolean",
                    "description": "Whether PII was found in the text",
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "The PII as it appears in the text",
                            },
                            "pii_type": {
                                "type": "string",
                                "enum": [
                                    "full_name",
                                    "email",
                                    "phone_number",
                                    "address",
                                    "date_of_birth",
                                    "national_id",
                                    "financial",
                                    "medical",
                                    "username",
                                    "ip_address",
                                    "other",
                                ],
                                "description": "Type of PII",
                            },
                            "confidence": {
                                "type": "string",
                                "enum": ["low", "medium", "high"],
                                "description": "Confidence that this is real PII rather than fictional",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Why this was flagged as PII",
                            },
                        },
                        "required": ["text", "pii_type", "confidence", "explanation"],
                    },
                    "description": "PII instances found",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief assessment of PII exposure in the text",
                },
            },
            "required": ["has_pii", "items", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/pii_detection.html"


register(PIIDetectionAction())
