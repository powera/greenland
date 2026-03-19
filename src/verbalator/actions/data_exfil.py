"""Data exfiltration/infiltration vector detection action."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "data_exfil"


class DataExfilAction(ActionBase):
    name = "data_exfil"
    display_name = "Data Exfil/Infiltration"
    description = "Detect URLs, links, and other data exfiltration or infiltration vectors"
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
                "has_vectors": {
                    "type": "boolean",
                    "description": "Whether any exfiltration or infiltration vectors were found",
                },
                "vectors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "passage": {
                                "type": "string",
                                "description": "The passage containing the vector",
                            },
                            "vector_type": {
                                "type": "string",
                                "enum": [
                                    "direct_url",
                                    "obfuscated_url",
                                    "email_address",
                                    "domain_reference",
                                    "ip_address",
                                    "file_path",
                                    "command_injection",
                                    "encoded_data",
                                    "qr_code_reference",
                                    "social_engineering",
                                    "indirect_reference",
                                    "other",
                                ],
                                "description": "Type of exfiltration/infiltration vector",
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["exfiltration", "infiltration", "both", "unclear"],
                                "description": "Whether this vector sends data out or brings data/instructions in",
                            },
                            "severity": {
                                "type": "string",
                                "enum": ["informational", "low", "moderate", "high", "critical"],
                                "description": "Severity of the vector",
                            },
                            "explanation": {
                                "type": "string",
                                "description": "How this vector could be used for data exfiltration or infiltration",
                            },
                            "is_obfuscated": {
                                "type": "boolean",
                                "description": "Whether the vector appears to be deliberately hidden or encoded",
                            },
                        },
                        "required": [
                            "passage",
                            "vector_type",
                            "direction",
                            "severity",
                            "explanation",
                            "is_obfuscated",
                        ],
                    },
                    "description": "Exfiltration/infiltration vectors found",
                },
                "summary": {
                    "type": "string",
                    "description": "Brief assessment of data exfiltration/infiltration risk",
                },
            },
            "required": ["has_vectors", "vectors", "summary"],
            "additionalProperties": False,
        }

    def get_template_name(self) -> str:
        return "verbalator/results/data_exfil.html"


register(DataExfilAction())
