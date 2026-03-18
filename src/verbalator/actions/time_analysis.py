"""Temporal analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "time_analysis"


class TimeAnalysisAction(ActionBase):
    name = "time_analysis"
    display_name = "Time Analysis"
    description = "Estimate when the text was written or when described events occurred"
    color_group = "blue"
    needs_context = False
    needs_target_language = False

    def build_prompt(
        self,
        text: str,
        context: Optional[str] = None,
        target_language: Optional[str] = None,
        session: Optional[Any] = None,
    ) -> Tuple[str, str]:
        system_context = util.prompt_loader.get_context(
            _PROMPT_CATEGORY, _PROMPT_TYPE
        )
        prompt = util.prompt_loader.get_prompt(
            _PROMPT_CATEGORY, _PROMPT_TYPE
        ).format(text=text)
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "estimated_era": {
                    "type": "string",
                    "description": "Broad era description (e.g. 'Victorian era', 'Early 20th century')",
                },
                "date_range_start": {
                    "type": "string",
                    "description": "Estimated earliest date (ISO format or descriptive)",
                },
                "date_range_end": {
                    "type": "string",
                    "description": "Estimated latest date (ISO format or descriptive)",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["very_low", "low", "medium", "high", "very_high"],
                    "description": "Confidence level in the temporal estimate",
                },
                "temporal_clues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "clue": {
                                "type": "string",
                                "description": "The temporal clue found in the text",
                            },
                            "implication": {
                                "type": "string",
                                "description": "What this clue suggests about the time period",
                            },
                        },
                        "required": ["clue", "implication"],
                    },
                    "description": "Temporal clues found in the text",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Overall reasoning for the temporal estimate",
                },
            },
            "required": [
                "estimated_era",
                "date_range_start",
                "date_range_end",
                "confidence",
                "temporal_clues",
                "reasoning",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/time_analysis.html"


register(TimeAnalysisAction())
