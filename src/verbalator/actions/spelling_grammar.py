"""Spelling and grammar checking action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "spelling_grammar"


class SpellingGrammarAction(ActionBase):
    name = "spelling_grammar"
    display_name = "Spelling & Grammar"
    description = "Check for spelling errors, grammatical mistakes, and punctuation issues"
    color_group = "red"
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
                "has_errors": {
                    "type": "boolean",
                    "description": "Whether spelling or grammar errors were found",
                },
                "errors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The passage containing the error",
                            },
                            "error_type": {
                                "type": "string",
                                "enum": [
                                    "spelling",
                                    "grammar",
                                    "punctuation",
                                    "capitalization",
                                    "subject_verb_agreement",
                                    "tense_consistency",
                                    "word_confusion",
                                    "missing_word",
                                    "extra_word",
                                    "other",
                                ],
                                "description": "The type of error",
                            },
                            "correction": {
                                "type": "string",
                                "description": "The suggested correction",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Why this is an error",
                            },
                        },
                        "required": [
                            "passage",
                            "error_type",
                            "correction",
                            "explanation",
                        ],
                    },
                    "description": "Errors found in the text",
                },
                "error_count": {
                    "type": "integer",
                    "description": "Total number of errors found",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of spelling and grammar quality",
                },
            },
            "required": ["has_errors", "errors", "error_count", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/spelling_grammar.html"


register(SpellingGrammarAction())
