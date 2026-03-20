"""Expand, compress, and join text action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "expand_compress"


class ExpandCompressAction(ActionBase):
    name = "expand_compress"
    display_name = "Expand / Compress"
    description = "Summarize, expand, or join texts with suggested modifications and transitions"
    color_group = "red"
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
            context=context or "(no additional text provided)",
        )
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["summarize", "expand", "join"],
                    "description": "The operation that best fits the input",
                },
                "modifications": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "modification_type": {
                                "type": "string",
                                "enum": [
                                    "compression",
                                    "expansion",
                                    "transition",
                                    "reorder",
                                    "merge",
                                ],
                                "description": "The type of modification",
                            },
                            "original_passage": {
                                "type": "string",
                                "description": "The original passage being modified, or empty for insertions",
                            },
                            "suggested_text": {
                                "type": "string",
                                "description": "The suggested replacement or inserted text",
                            },
                            "rationale": {
                                "type": "string",
                                "description": "Why this modification improves the text",
                            },
                        },
                        "required": [
                            "modification_type",
                            "original_passage",
                            "suggested_text",
                            "rationale",
                        ],
                    },
                    "description": "Individual suggested modifications",
                },
                "full_suggested_text": {
                    "type": "string",
                    "description": "The complete modified text with all suggestions applied",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of what was changed and why",
                },
            },
            "required": [
                "operation",
                "modifications",
                "full_suggested_text",
                "summary",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/expand_compress.html"


register(ExpandCompressAction())
