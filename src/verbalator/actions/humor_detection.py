"""Humor and joke detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "humor_detection"


class HumorDetectionAction(ActionBase):
    name = "humor_detection"
    display_name = "Humor Detection"
    description = "Detect jokes, puns, wordplay, and humorous intent"
    color_group = "xantham"
    needs_context = True
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
            context=context or "(no context provided)",
        )
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "contains_humor": {
                    "type": "boolean",
                    "description": "Whether the text contains humor or jokes",
                },
                "instances": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The humorous passage",
                            },
                            "humor_type": {
                                "type": "string",
                                "enum": [
                                    "joke",
                                    "pun",
                                    "wordplay",
                                    "absurdist",
                                    "observational",
                                    "self_deprecating",
                                    "dark_humor",
                                    "innuendo",
                                    "parody",
                                    "wit",
                                    "other",
                                ],
                                "description": "The type of humor",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Why this is funny or intended to be funny",
                            },
                            "likely_lands": {
                                "type": "boolean",
                                "description": "Whether the humor is likely to be understood and appreciated by a general audience",
                            },
                        },
                        "required": [
                            "passage",
                            "humor_type",
                            "explanation",
                            "likely_lands",
                        ],
                    },
                    "description": "Humorous passages found in the text",
                },
                "overall_tone": {
                    "type": "string",
                    "enum": [
                        "serious",
                        "mostly_serious",
                        "lighthearted",
                        "comedic",
                        "satirical",
                    ],
                    "description": "Overall humorous tone of the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of humor in the text",
                },
            },
            "required": ["contains_humor", "instances", "overall_tone", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/humor_detection.html"


register(HumorDetectionAction())
