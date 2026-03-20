"""Jargon and slang detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "jargon_slang"


class JargonSlangAction(ActionBase):
    name = "jargon_slang"
    display_name = "Jargon & Slang"
    description = "Identify jargon, slang, colloquialisms, and informal language"
    color_group = "orange"
    needs_context = False
    needs_target_language = True

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
            target_language=target_language or "en",
        )
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "has_jargon_or_slang": {
                    "type": "boolean",
                    "description": "Whether jargon or slang was found in the text",
                },
                "terms": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "term": {
                                "type": "string",
                                "description": "The jargon or slang term as it appears in the text",
                            },
                            "term_type": {
                                "type": "string",
                                "enum": [
                                    "technical_jargon",
                                    "industry_jargon",
                                    "slang",
                                    "colloquialism",
                                    "acronym",
                                    "neologism",
                                    "dialect",
                                ],
                                "description": "The type of informal or specialized language",
                            },
                            "domain": {
                                "type": "string",
                                "description": "The field or subculture this term belongs to (e.g. medical, legal, internet, youth slang)",
                            },
                            "standard_equivalent": {
                                "type": "string",
                                "description": "A standard or formal equivalent of the term",
                            },
                            "accessibility": {
                                "type": "string",
                                "enum": [
                                    "widely_understood",
                                    "somewhat_known",
                                    "specialist",
                                    "obscure",
                                ],
                                "description": "How widely the term would be understood by a general audience",
                            },
                        },
                        "required": [
                            "term",
                            "term_type",
                            "domain",
                            "standard_equivalent",
                            "accessibility",
                        ],
                    },
                    "description": "Jargon and slang terms found in the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of jargon and slang usage in the text",
                },
            },
            "required": ["has_jargon_or_slang", "terms", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/jargon_slang.html"


register(JargonSlangAction())
