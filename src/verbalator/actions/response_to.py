"""Response-to analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "response_to"


class ResponseToAction(ActionBase):
    name = "response_to"
    display_name = "Response-To"
    description = "Analyze whether text is responding to given context"
    color_group = "blue"
    needs_context = True
    needs_target_language = False

    def build_prompt(
        self,
        text: str,
        context: Optional[str] = None,
        target_language: Optional[str] = None,
        session: Optional[Any] = None,
    ) -> Tuple[str, str]:
        system_context = util.prompt_loader.get_context(
            _PROMPT_CATEGORY, _PROMPT_TYPE
        )
        prompt = util.prompt_loader.get_prompt(
            _PROMPT_CATEGORY, _PROMPT_TYPE
        ).format(
            text=text,
            context=context or "(no context provided)",
        )
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "is_response": {
                    "type": "boolean",
                    "description": "Whether the text is a response to the context",
                },
                "responding_to_summary": {
                    "type": "string",
                    "description": "Summary of what the text is responding to",
                },
                "relationship_type": {
                    "type": "string",
                    "description": "Type of relationship (reply, rebuttal, elaboration, agreement, etc.)",
                },
                "key_references": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "reference": {
                                "type": "string",
                                "description": "The reference or callback in the text",
                            },
                            "refers_to": {
                                "type": "string",
                                "description": "What part of the context it refers to",
                            },
                        },
                        "required": ["reference", "refers_to"],
                    },
                    "description": "Key references from the text back to the context",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["very_low", "low", "medium", "high", "very_high"],
                    "description": "Confidence level in the analysis",
                },
            },
            "required": [
                "is_response",
                "responding_to_summary",
                "relationship_type",
                "key_references",
                "confidence",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/response_to.html"


register(ResponseToAction())
