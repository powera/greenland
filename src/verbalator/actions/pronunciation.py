"""Pronunciation difficulty tagging action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "pronunciation"


class PronunciationAction(ActionBase):
    name = "pronunciation"
    display_name = "Pronunciation Difficulty"
    description = "Tag words likely to be queried for pronunciation difficulty"
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
                "language": {
                    "type": "string",
                    "description": "Language of the text",
                },
                "words": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "word": {
                                "type": "string",
                                "description": "The word as it appears in the text",
                            },
                            "difficulty": {
                                "type": "string",
                                "enum": ["easy", "moderate", "hard", "very_hard"],
                                "description": "Pronunciation difficulty level",
                            },
                            "reasons": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Why this word is difficult to pronounce",
                            },
                            "ipa": {
                                "type": "string",
                                "description": "IPA transcription if known",
                            },
                        },
                        "required": ["word", "difficulty", "reasons", "ipa"],
                    },
                    "description": "Words tagged for pronunciation difficulty",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of pronunciation challenges in the text",
                },
            },
            "required": ["language", "words", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/pronunciation.html"


register(PronunciationAction())
