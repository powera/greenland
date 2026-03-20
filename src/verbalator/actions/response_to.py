"""Contextual analysis action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "context_analysis"


class ContextAnalysisAction(ActionBase):
    name = "context_analysis"
    display_name = "Context Analysis"
    description = "Analyze the text's relationship to provided context and its implicit situational assumptions"
    color_group = "blue"
    needs_context = True
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
            context=context or "(no context provided)",
        )
        return system_context, prompt

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "is_response": {
                    "type": "boolean",
                    "description": "Whether the text appears to be a response to the provided context",
                },
                "relationship_to_context": {
                    "type": "string",
                    "enum": [
                        "direct_reply",
                        "rebuttal",
                        "elaboration",
                        "agreement",
                        "continuation",
                        "tangential",
                        "unrelated",
                        "unclear",
                    ],
                    "description": "How the text relates to the provided context",
                },
                "context_references": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The passage in the text that references the context",
                            },
                            "refers_to": {
                                "type": "string",
                                "description": "What part of the context it refers to",
                            },
                        },
                        "required": ["passage", "refers_to"],
                    },
                    "description": "Explicit references from the text back to the provided context",
                },
                "assumed_knowledge": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "assumption": {
                                "type": "string",
                                "description": "Something the text assumes the reader already knows",
                            },
                            "evidence": {
                                "type": "string",
                                "description": "The passage that reveals this assumption",
                            },
                            "found_in_context": {
                                "type": "boolean",
                                "description": "Whether this assumed knowledge is present in the provided context",
                            },
                        },
                        "required": ["assumption", "evidence", "found_in_context"],
                    },
                    "description": "Knowledge the text assumes the reader has, based on what is stated vs. left implicit",
                },
                "situational_clues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "clue": {
                                "type": "string",
                                "description": "A passage that reveals something about the situation",
                            },
                            "implies": {
                                "type": "string",
                                "description": "What this clue suggests about the surrounding situation",
                            },
                        },
                        "required": ["clue", "implies"],
                    },
                    "description": "Clues about the broader situation (conversation, event, medium) the text exists in",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["very_low", "low", "medium", "high", "very_high"],
                    "description": "Confidence level in the analysis",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief overview of the text's contextual situation",
                },
            },
            "required": [
                "is_response",
                "relationship_to_context",
                "context_references",
                "assumed_knowledge",
                "situational_clues",
                "confidence",
                "summary",
            ],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/context_analysis.html"


register(ContextAnalysisAction())
