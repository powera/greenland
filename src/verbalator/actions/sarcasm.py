"""Sarcasm detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "sarcasm"


class SarcasmAction(ActionBase):
    name = "sarcasm"
    display_name = "Sarcasm Detection"
    description = "Detect sarcasm, irony, and overconfident tone"
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
                "contains_sarcasm": {
                    "type": "boolean",
                    "description": "Whether the text contains sarcasm or irony",
                },
                "overall_tone": {
                    "type": "string",
                    "description": "Overall tone of the text (e.g. sincere, sarcastic, ironic, deadpan, hyperbolic)",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["very_low", "low", "medium", "high", "very_high"],
                    "description": "Confidence in the sarcasm assessment",
                },
                "instances": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The sarcastic or ironic passage",
                            },
                            "sarcasm_type": {
                                "type": "string",
                                "enum": [
                                    "verbal_irony",
                                    "situational_irony",
                                    "hyperbole",
                                    "understatement",
                                    "deadpan",
                                    "rhetorical_question",
                                    "mock_sincerity",
                                ],
                                "description": "The type of sarcasm or irony used",
                            },
                            "literal_meaning": {
                                "type": "string",
                                "description": "What the words literally say",
                            },
                            "intended_meaning": {
                                "type": "string",
                                "description": "What the author likely means",
                            },
                            "clues": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Linguistic or contextual clues that signal sarcasm",
                            },
                        },
                        "required": [
                            "passage",
                            "sarcasm_type",
                            "literal_meaning",
                            "intended_meaning",
                            "clues",
                        ],
                    },
                    "description": "Individual sarcastic passages found in the text",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Overall reasoning about the tone and any sarcasm detected",
                },
            },
            "required": [
                "contains_sarcasm",
                "overall_tone",
                "confidence",
                "instances",
                "reasoning",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/sarcasm.html"


register(SarcasmAction())
