"""Text metadata analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "metadata"


class MetadataAction(ActionBase):
    name = "metadata"
    display_name = "Text Metadata"
    description = "Analyze language, register, formality, genre, and key topics"
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
        system_context = util.prompt_loader.get_context(_PROMPT_CATEGORY, _PROMPT_TYPE)
        prompt = util.prompt_loader.get_prompt(_PROMPT_CATEGORY, _PROMPT_TYPE).format(text=text)
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "description": "Primary language of the text (e.g. English, French)",
                },
                "dialect": {
                    "type": "string",
                    "description": "Identifiable dialect or variant, or 'standard'",
                },
                "register": {
                    "type": "string",
                    "description": "Language register (formal, informal, literary, technical, colloquial, etc.)",
                },
                "formality": {
                    "type": "string",
                    "enum": [
                        "very_informal",
                        "informal",
                        "neutral",
                        "formal",
                        "very_formal",
                    ],
                    "description": "Formality level",
                },
                "estimated_length_category": {
                    "type": "string",
                    "enum": [
                        "fragment",
                        "sentence",
                        "paragraph",
                        "passage",
                        "document",
                    ],
                    "description": "Length category of the text",
                },
                "author_type": {
                    "type": "string",
                    "description": "Likely author type (individual, organization, literary, academic, etc.)",
                },
                "genre": {
                    "type": "string",
                    "description": "Text genre (fiction, non-fiction, poetry, legal, technical, conversation, etc.)",
                },
                "key_topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key topics discussed in the text",
                },
            },
            "required": [
                "language",
                "dialect",
                "register",
                "formality",
                "estimated_length_category",
                "author_type",
                "genre",
                "key_topics",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/metadata.html"


register(MetadataAction())
