"""Adversarial content and prompt injection detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "adversarial_content"


class AdversarialContentAction(ActionBase):
    name = "adversarial_content"
    display_name = "Adversarial Content"
    description = "Detect prompt injection, instruction overrides, and adversarial manipulation"
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
                "has_adversarial_content": {
                    "type": "boolean",
                    "description": "Whether adversarial or injection content was found",
                },
                "instances": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The passage containing adversarial content",
                            },
                            "technique": {
                                "type": "string",
                                "enum": [
                                    "instruction_override",
                                    "role_play_manipulation",
                                    "delimiter_abuse",
                                    "context_switching",
                                    "system_prompt_extraction",
                                    "jailbreak_attempt",
                                    "hidden_instruction",
                                    "encoding_evasion",
                                    "other",
                                ],
                                "description": "The adversarial technique used",
                            },
                            "severity": {
                                "type": "string",
                                "enum": [
                                    "informational",
                                    "low",
                                    "moderate",
                                    "high",
                                    "critical",
                                ],
                                "description": "Severity of the adversarial content",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "How this content attempts to manipulate or override instructions",
                            },
                        },
                        "required": [
                            "passage",
                            "technique",
                            "severity",
                            "explanation",
                        ],
                    },
                    "description": "Adversarial content instances found",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief assessment of adversarial content risk",
                },
            },
            "required": ["has_adversarial_content", "instances", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/adversarial_content.html"


register(AdversarialContentAction())
