"""Sensitive political topics detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "sensitive_politics"


class SensitivePoliticsAction(ActionBase):
    name = "sensitive_politics"
    display_name = "Sensitive Political Topics"
    description = "Identify politically sensitive content that may need editorial review"
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
                "has_sensitive_content": {
                    "type": "boolean",
                    "description": "Whether politically sensitive topics were found",
                },
                "topics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "description": "The sensitive political topic",
                            },
                            "sensitivity": {
                                "type": "string",
                                "enum": ["low", "moderate", "high", "very_high"],
                                "description": "How sensitive this topic is likely to be",
                            },
                            "passage": {
                                "type": "string",
                                "description": "The relevant passage from the text",
                            },
                            "concern": {
                                "type": "string",
                                "description": "Why this topic may be sensitive",
                            },
                            "regions_affected": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Regions or audiences where this is most sensitive",
                            },
                        },
                        "required": [
                            "topic",
                            "sensitivity",
                            "passage",
                            "concern",
                            "regions_affected",
                        ],
                    },
                    "description": "Sensitive topics found",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overall assessment of political sensitivity",
                },
            },
            "required": ["has_sensitive_content", "topics", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/sensitive_politics.html"


register(SensitivePoliticsAction())
