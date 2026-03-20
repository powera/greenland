"""Privacy, secrecy, and cryptography discussion detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "privacy_secrecy"


class PrivacySecrecyAction(ActionBase):
    name = "privacy_secrecy"
    display_name = "Privacy & Secrecy"
    description = "Detect discussions of cryptography, privacy, secrecy, and censorship"
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
                "has_relevant_content": {
                    "type": "boolean",
                    "description": "Whether discussions of privacy, secrecy, cryptography, or censorship were found",
                },
                "topics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {
                                "type": "string",
                                "enum": [
                                    "cryptography",
                                    "encryption",
                                    "privacy",
                                    "surveillance",
                                    "secrecy",
                                    "censorship",
                                    "anonymity",
                                    "data_protection",
                                    "whistleblowing",
                                    "classified_information",
                                    "other",
                                ],
                                "description": "The topic category",
                            },
                            "passage": {
                                "type": "string",
                                "description": "The passage discussing this topic",
                            },
                            "framing": {
                                "type": "string",
                                "enum": [
                                    "neutral",
                                    "advocacy",
                                    "cautionary",
                                    "instructional",
                                    "critical",
                                ],
                                "description": "How the topic is framed in the text",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "Why this passage is relevant",
                            },
                        },
                        "required": ["topic", "passage", "framing", "explanation"],
                    },
                    "description": "Relevant topics found in the text",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of privacy/secrecy/cryptography content in the text",
                },
            },
            "required": ["has_relevant_content", "topics", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/privacy_secrecy.html"


register(PrivacySecrecyAction())
