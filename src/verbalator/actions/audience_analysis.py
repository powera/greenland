"""Audience analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "audience_analysis"


class AudienceAnalysisAction(ActionBase):
    name = "audience_analysis"
    display_name = "Audience Analysis"
    description = "Identify the intended audience of the text"
    color_group = "yellow"
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
                "primary_audience": {
                    "type": "string",
                    "description": "The most likely intended audience (e.g. general public, specialists, children, policymakers)",
                },
                "age_range": {
                    "type": "string",
                    "description": "Estimated target age range (e.g. children, young adult, adult, all ages)",
                },
                "expertise_level": {
                    "type": "string",
                    "enum": [
                        "no_background",
                        "general_awareness",
                        "educated_layperson",
                        "practitioner",
                        "expert",
                    ],
                    "description": "Level of expertise assumed in the reader",
                },
                "indicators": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "indicator": {
                                "type": "string",
                                "description": "A feature of the text that signals the audience",
                            },
                            "passage": {
                                "type": "string",
                                "description": "Example passage demonstrating this indicator",
                            },
                        },
                        "required": ["indicator", "passage"],
                    },
                    "description": "Textual clues that reveal the intended audience",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of the intended audience",
                },
            },
            "required": [
                "primary_audience",
                "age_range",
                "expertise_level",
                "indicators",
                "summary",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/audience_analysis.html"


register(AudienceAnalysisAction())
