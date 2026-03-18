"""Base class for verbalator actions."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple


class ActionBase(ABC):
    """Abstract base class for verbalator actions.

    Each action is a "function for words" that takes text input and returns
    structured JSON results via an LLM call.
    """

    name: str  # e.g. "sentence_decomposition"
    display_name: str  # e.g. "Sentence Decomposition"
    description: str  # Short description
    color_group: str  # e.g. "blue", "green" — for UI grouping
    needs_context: bool = False  # True if action needs more than just the text
    needs_target_language: bool = False  # True if action needs a target language

    @abstractmethod
    def build_prompt(
        self,
        text: str,
        context: Optional[str] = None,
        target_language: Optional[str] = None,
        session: Optional[Any] = None,
    ) -> Tuple[str, str]:
        """Build (context_str, prompt_str) for the LLM call.

        Args:
            text: The input text to analyze.
            context: Optional surrounding context (for needs_context actions).
            target_language: Optional target language code.
            session: Optional DB session (for DB-connected actions).

        Returns:
            Tuple of (system_context, user_prompt).
        """

    @abstractmethod
    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        """Build the JSON schema for structured LLM output.

        Returns:
            JSON schema dict describing the expected response structure.
        """

    @abstractmethod
    def get_template_name(self) -> str:
        """Return the Jinja2 template path for rendering results.

        Returns:
            Template path relative to templates dir,
            e.g. "verbalator/results/decomposition.html".
        """

    def to_dict(self) -> Dict[str, Any]:
        """Serialize action metadata for the frontend."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "color_group": self.color_group,
            "needs_context": self.needs_context,
            "needs_target_language": self.needs_target_language,
        }
