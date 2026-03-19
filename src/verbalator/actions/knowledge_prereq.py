"""Knowledge prerequisite analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "knowledge_prereq"


class KnowledgePrereqAction(ActionBase):
    name = "knowledge_prereq"
    display_name = "Knowledge Prerequisites"
    description = "Identify domain knowledge needed to understand the text (biology, physics, etc.)"
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
                "domains": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "domain": {
                                "type": "string",
                                "description": "The knowledge domain (e.g. biology, physics, history, law, economics)",
                            },
                            "level": {
                                "type": "string",
                                "enum": [
                                    "none",
                                    "general_awareness",
                                    "introductory",
                                    "intermediate",
                                    "advanced",
                                    "specialist",
                                ],
                                "description": "Level of domain knowledge required",
                            },
                            "concepts": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "concept": {
                                            "type": "string",
                                            "description": "The specific concept or term requiring domain knowledge",
                                        },
                                        "passage": {
                                            "type": "string",
                                            "description": "Where in the text this concept appears",
                                        },
                                        "explanation": {
                                            "type": "string",
                                            "description": "What knowledge is needed to understand it",
                                        },
                                    },
                                    "required": ["concept", "passage", "explanation"],
                                },
                                "description": "Specific concepts requiring this domain knowledge",
                            },
                        },
                        "required": ["domain", "level", "concepts"],
                    },
                    "description": "Knowledge domains required, ordered by importance",
                },
                "overall_level": {
                    "type": "string",
                    "enum": [
                        "general_audience",
                        "educated_layperson",
                        "undergraduate",
                        "graduate",
                        "expert",
                    ],
                    "description": "Overall knowledge level assumed by the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of the knowledge prerequisites",
                },
            },
            "required": ["domains", "overall_level", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/knowledge_prereq.html"


register(KnowledgePrereqAction())
