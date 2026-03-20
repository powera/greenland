"""Content filter action — flag references to sensitive content categories."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "content_filter"


class ContentFilterAction(ActionBase):
    name = "content_filter"
    display_name = "Content Filter"
    description = "Flag references to violence, firearms, narcotics, alcohol/tobacco, sex, gambling, nuclear weapons, and religion"
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
                "has_flagged_content": {
                    "type": "boolean",
                    "description": "Whether any filtered content categories were found",
                },
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": [
                                    "violence",
                                    "firearms",
                                    "narcotics",
                                    "alcohol_tobacco",
                                    "sexual_content",
                                    "gambling",
                                    "nuclear_weapons",
                                    "religion",
                                ],
                                "description": "The content category",
                            },
                            "present": {
                                "type": "boolean",
                                "description": "Whether this category is present in the text",
                            },
                            "severity": {
                                "type": "string",
                                "enum": ["none", "mild", "moderate", "strong", "extreme"],
                                "description": "Severity of the reference",
                            },
                            "instances": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "passage": {
                                            "type": "string",
                                            "description": "The passage containing the reference",
                                        },
                                        "explanation": {
                                            "type": "string",
                                            "description": "Why this is flagged",
                                        },
                                    },
                                    "required": ["passage", "explanation"],
                                },
                                "description": "Specific instances found",
                            },
                        },
                        "required": ["category", "present", "severity", "instances"],
                    },
                    "description": "Results for each content category",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overall content assessment",
                },
            },
            "required": ["has_flagged_content", "categories", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/content_filter.html"


register(ContentFilterAction())
