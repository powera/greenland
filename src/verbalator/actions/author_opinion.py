"""Author opinion detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "author_opinion"


class AuthorOpinionAction(ActionBase):
    name = "author_opinion"
    display_name = "Author Opinions"
    description = "Detect the author's personal opinions, preferences, and subjective judgments"
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
                "has_opinions": {
                    "type": "boolean",
                    "description": "Whether the author's personal opinions are present",
                },
                "opinions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The passage containing the opinion",
                            },
                            "opinion_type": {
                                "type": "string",
                                "enum": [
                                    "personal_preference",
                                    "value_judgment",
                                    "political_stance",
                                    "brand_preference",
                                    "aesthetic_judgment",
                                    "moral_judgment",
                                    "prediction",
                                    "recommendation",
                                ],
                                "description": "The type of opinion expressed",
                            },
                            "target": {
                                "type": "string",
                                "description": "What or who the opinion is about",
                            },
                            "sentiment": {
                                "type": "string",
                                "enum": [
                                    "strongly_negative",
                                    "negative",
                                    "mixed",
                                    "positive",
                                    "strongly_positive",
                                ],
                                "description": "The sentiment of the opinion",
                            },
                            "explicitness": {
                                "type": "string",
                                "enum": ["explicit", "implied", "hedged"],
                                "description": "How directly the opinion is stated",
                            },
                        },
                        "required": [
                            "passage",
                            "opinion_type",
                            "target",
                            "sentiment",
                            "explicitness",
                        ],
                    },
                    "description": "Author opinions found in the text",
                },
                "objectivity_rating": {
                    "type": "string",
                    "enum": [
                        "objective",
                        "mostly_objective",
                        "mixed",
                        "mostly_subjective",
                        "subjective",
                    ],
                    "description": "Overall objectivity of the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of author opinions present in the text",
                },
            },
            "required": ["has_opinions", "opinions", "objectivity_rating", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/author_opinion.html"


register(AuthorOpinionAction())
