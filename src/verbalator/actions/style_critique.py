"""Style critique action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "style_critique"


class StyleCritiqueAction(ActionBase):
    name = "style_critique"
    display_name = "Style Critique"
    description = (
        "Critique the author's stylistic choices: word choice, sentence structure, clarity, voice"
    )
    color_group = "red"
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
                "observations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "enum": [
                                    "word_choice",
                                    "sentence_structure",
                                    "clarity",
                                    "redundancy",
                                    "cliche",
                                    "voice",
                                    "tone_consistency",
                                    "paragraph_structure",
                                    "transitions",
                                    "conciseness",
                                    "other",
                                ],
                                "description": "The stylistic category",
                            },
                            "passage": {
                                "type": "string",
                                "description": "The passage exhibiting this stylistic choice",
                            },
                            "assessment": {
                                "type": "string",
                                "enum": [
                                    "effective",
                                    "adequate",
                                    "weak",
                                    "problematic",
                                ],
                                "description": "How well the stylistic choice works",
                            },
                            "comment": {
                                "type": "string",
                                "description": "Specific critique or praise of this choice",
                            },
                            "suggestion": {
                                "type": "string",
                                "description": "A suggested improvement, or empty if the choice is effective",
                            },
                        },
                        "required": [
                            "category",
                            "passage",
                            "assessment",
                            "comment",
                            "suggestion",
                        ],
                    },
                    "description": "Individual stylistic observations",
                },
                "overall_quality": {
                    "type": "string",
                    "enum": [
                        "excellent",
                        "good",
                        "adequate",
                        "needs_work",
                        "poor",
                    ],
                    "description": "Overall assessment of the writing style",
                },
                "strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key stylistic strengths of the text",
                },
                "weaknesses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key stylistic weaknesses of the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overall style critique",
                },
            },
            "required": [
                "observations",
                "overall_quality",
                "strengths",
                "weaknesses",
                "summary",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/style_critique.html"


register(StyleCritiqueAction())
