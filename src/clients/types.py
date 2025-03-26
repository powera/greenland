from dataclasses import dataclass
from typing import Dict, Any

from telemetry import LLMUsage

@dataclass
class Response:
    """Container for response data."""
    response_text: str
    structured_data: Dict[str, Any]
    usage: LLMUsage
