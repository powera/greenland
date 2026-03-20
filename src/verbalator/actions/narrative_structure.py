"""Narrative structure analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "narrative_structure"


class NarrativeStructureAction(ActionBase):
    name = "narrative_structure"
    display_name = "Narrative Structure"
    description = (
        "Analyze whether the text is a single narrative, vignettes, listicle, argument, etc."
    )
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
                "structure_type": {
                    "type": "string",
                    "enum": [
                        "single_narrative",
                        "multiple_vignettes",
                        "listicle",
                        "argument",
                        "dialogue",
                        "instructional",
                        "mixed",
                    ],
                    "description": "The overall structural type of the text",
                },
                "segment_count": {
                    "type": "integer",
                    "description": "Number of distinct segments or sections in the text",
                },
                "segments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "segment_label": {
                                "type": "string",
                                "description": "A short label for this segment",
                            },
                            "segment_type": {
                                "type": "string",
                                "enum": [
                                    "narrative",
                                    "exposition",
                                    "argument",
                                    "anecdote",
                                    "list",
                                    "dialogue",
                                    "instruction",
                                    "transition",
                                ],
                                "description": "The type of this segment",
                            },
                            "passage": {
                                "type": "string",
                                "description": "Opening words of this segment for identification",
                            },
                        },
                        "required": ["segment_label", "segment_type", "passage"],
                    },
                    "description": "The segments that make up the text",
                },
                "coherence": {
                    "type": "string",
                    "enum": ["tight", "moderate", "loose", "disconnected"],
                    "description": "How tightly the segments connect to each other",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of the narrative structure",
                },
            },
            "required": [
                "structure_type",
                "segment_count",
                "segments",
                "coherence",
                "summary",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/narrative_structure.html"


register(NarrativeStructureAction())
