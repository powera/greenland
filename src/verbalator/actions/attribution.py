"""Quotation attribution analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "attribution"


class AttributionAction(ActionBase):
    name = "attribution"
    display_name = "Quotation Attribution"
    description = "Identify quotations and whether they need attribution"
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
                "has_quotations": {
                    "type": "boolean",
                    "description": "Whether the text contains quotations or quoted speech",
                },
                "quotations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quoted_text": {
                                "type": "string",
                                "description": "The quoted or paraphrased passage",
                            },
                            "is_attributed": {
                                "type": "boolean",
                                "description": "Whether the quotation is attributed to a source",
                            },
                            "attributed_to": {
                                "type": "string",
                                "description": "Who or what the quote is attributed to, or empty if unattributed",
                            },
                            "quotation_type": {
                                "type": "string",
                                "enum": [
                                    "direct_quote",
                                    "paraphrase",
                                    "proverb",
                                    "idiom",
                                    "dialogue",
                                    "reported_speech",
                                    "allusion",
                                ],
                                "description": "The type of quotation or reference",
                            },
                            "needs_attribution": {
                                "type": "boolean",
                                "description": "Whether this quotation should have attribution but lacks it",
                            },
                            "suggested_source": {
                                "type": "string",
                                "description": "Possible source if recognizable (e.g. a well-known quote), or empty",
                            },
                        },
                        "required": [
                            "quoted_text",
                            "is_attributed",
                            "attributed_to",
                            "quotation_type",
                            "needs_attribution",
                            "suggested_source",
                        ],
                    },
                    "description": "List of quotations found in the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief summary of the attribution status of the text",
                },
            },
            "required": ["has_quotations", "quotations", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/attribution.html"


register(AttributionAction())
