"""Numeric precision and sourcing analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "numeric_precision"


class NumericPrecisionAction(ActionBase):
    name = "numeric_precision"
    display_name = "Numeric Precision"
    description = "Flag numbers with excessive precision and check authority/sourcing"
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
                "has_numeric_issues": {
                    "type": "boolean",
                    "description": "Whether any numbers with precision or sourcing issues were found",
                },
                "numbers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The passage containing the number",
                            },
                            "number": {
                                "type": "string",
                                "description": "The number as it appears in the text",
                            },
                            "excessive_precision": {
                                "type": "boolean",
                                "description": "Whether the number has more precision than is warranted",
                            },
                            "precision_concern": {
                                "type": "string",
                                "description": "Why the precision is excessive, or empty if appropriate",
                            },
                            "suggested_rounding": {
                                "type": "string",
                                "description": "A more appropriate level of precision, or empty if fine",
                            },
                            "is_sourced": {
                                "type": "boolean",
                                "description": "Whether the number is attributed to a source",
                            },
                            "stated_source": {
                                "type": "string",
                                "description": "The source cited in the text, or empty if unsourced",
                            },
                            "source_assessment": {
                                "type": "string",
                                "enum": [
                                    "well_sourced",
                                    "partially_sourced",
                                    "unsourced",
                                    "unverifiable",
                                    "likely_fabricated",
                                ],
                                "description": "Assessment of the sourcing quality",
                            },
                            "suggested_source_type": {
                                "type": "string",
                                "description": "What kind of authority could back this figure (e.g. census data, peer-reviewed study)",
                            },
                        },
                        "required": [
                            "passage",
                            "number",
                            "excessive_precision",
                            "precision_concern",
                            "suggested_rounding",
                            "is_sourced",
                            "stated_source",
                            "source_assessment",
                            "suggested_source_type",
                        ],
                    },
                    "description": "Numbers found in the text with precision and sourcing analysis",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of numeric precision and sourcing quality",
                },
            },
            "required": ["has_numeric_issues", "numbers", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/numeric_precision.html"


register(NumericPrecisionAction())
