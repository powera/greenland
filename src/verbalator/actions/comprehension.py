"""Comprehension difficulty tagging action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "comprehension"


class ComprehensionAction(ActionBase):
    name = "comprehension"
    display_name = "Comprehension Difficulty"
    description = "Tag words likely to be queried for comprehension difficulty"
    color_group = "orange"
    needs_context = True
    needs_target_language = True

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
            target_language=target_language or "en",
        )
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "Language of the text",
                },
                "words": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "word": {
                                "type": "string",
                                "description": "The word or phrase as it appears in the text",
                            },
                            "difficulty": {
                                "type": "string",
                                "enum": ["easy", "moderate", "hard", "very_hard"],
                                "description": "Comprehension difficulty level",
                            },
                            "reasons": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Why this word is difficult to understand",
                            },
                            "simplified_explanation": {
                                "type": "string",
                                "description": "A simpler explanation of the word's meaning in context",
                            },
                        },
                        "required": [
                            "word",
                            "difficulty",
                            "reasons",
                            "simplified_explanation",
                        ],
                    },
                    "description": "Words tagged for comprehension difficulty",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of comprehension challenges in the text",
                },
            },
            "required": ["language", "words", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/comprehension.html"


register(ComprehensionAction())
