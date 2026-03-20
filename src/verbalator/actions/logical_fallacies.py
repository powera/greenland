"""Logical fallacy and reasoning error detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "logical_fallacies"


class LogicalFallaciesAction(ActionBase):
    name = "logical_fallacies"
    display_name = "Logical Fallacies"
    description = "Detect logical fallacies, bad statistics, and reasoning errors"
    color_group = "green"
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
                "has_fallacies": {
                    "type": "boolean",
                    "description": "Whether logical fallacies or reasoning errors were found",
                },
                "fallacies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The passage containing the fallacy",
                            },
                            "fallacy_type": {
                                "type": "string",
                                "enum": [
                                    "correlation_causation",
                                    "cherry_picking",
                                    "survivorship_bias",
                                    "base_rate_neglect",
                                    "simpson_paradox",
                                    "p_hacking",
                                    "ad_hominem",
                                    "straw_man",
                                    "appeal_to_authority",
                                    "appeal_to_nature",
                                    "false_dilemma",
                                    "slippery_slope",
                                    "circular_reasoning",
                                    "hasty_generalization",
                                    "moving_goalposts",
                                    "red_herring",
                                    "tu_quoque",
                                    "equivocation",
                                    "composition_division",
                                    "gamblers_fallacy",
                                    "other",
                                ],
                                "description": "The type of fallacy or reasoning error",
                            },
                            "category": {
                                "type": "string",
                                "enum": [
                                    "statistical",
                                    "formal_logic",
                                    "informal_logic",
                                    "rhetorical",
                                ],
                                "description": "Broad category of the fallacy",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Why this reasoning is flawed",
                            },
                            "severity": {
                                "type": "string",
                                "enum": [
                                    "minor",
                                    "moderate",
                                    "major",
                                ],
                                "description": "How much the fallacy undermines the argument",
                            },
                        },
                        "required": [
                            "passage",
                            "fallacy_type",
                            "category",
                            "explanation",
                            "severity",
                        ],
                    },
                    "description": "Fallacies and reasoning errors found in the text",
                },
                "overall_reasoning_quality": {
                    "type": "string",
                    "enum": [
                        "rigorous",
                        "sound",
                        "mixed",
                        "weak",
                        "deeply_flawed",
                    ],
                    "description": "Overall quality of reasoning in the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of logical and reasoning issues",
                },
            },
            "required": [
                "has_fallacies",
                "fallacies",
                "overall_reasoning_quality",
                "summary",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/logical_fallacies.html"


register(LogicalFallaciesAction())
