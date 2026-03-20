"""Rhetorical purpose analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "rhetorical_purpose"


class RhetoricalPurposeAction(ActionBase):
    name = "rhetorical_purpose"
    display_name = "Rhetorical Purpose"
    description = (
        "Identify what the text is trying to accomplish (persuade, inform, entertain, instruct)"
    )
    color_group = "yellow"
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
                "primary_purpose": {
                    "type": "string",
                    "enum": [
                        "persuade",
                        "inform",
                        "entertain",
                        "instruct",
                        "provoke",
                        "document",
                        "reflect",
                    ],
                    "description": "The dominant rhetorical purpose of the text",
                },
                "secondary_purposes": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "persuade",
                            "inform",
                            "entertain",
                            "instruct",
                            "provoke",
                            "document",
                            "reflect",
                        ],
                    },
                    "description": "Additional purposes present in the text",
                },
                "techniques": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "technique": {
                                "type": "string",
                                "description": "The rhetorical technique used (e.g. appeal to authority, analogy, repetition)",
                            },
                            "passage": {
                                "type": "string",
                                "description": "Example passage using this technique",
                            },
                            "effect": {
                                "type": "string",
                                "description": "What this technique accomplishes",
                            },
                        },
                        "required": ["technique", "passage", "effect"],
                    },
                    "description": "Rhetorical techniques identified in the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of the rhetorical purpose and techniques",
                },
            },
            "required": [
                "primary_purpose",
                "secondary_purposes",
                "techniques",
                "summary",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/rhetorical_purpose.html"


register(RhetoricalPurposeAction())
