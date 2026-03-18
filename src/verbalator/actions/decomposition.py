"""Sentence decomposition action — DB-connected word-by-word breakdown."""

from typing import Any, Dict, Optional, Tuple

import util.prompt_loader
from verbalator.action_base import ActionBase
from verbalator.action_registry import register

_PROMPT_CATEGORY = "verbalator"
_PROMPT_TYPE = "decomposition"


class DecompositionAction(ActionBase):
    name = "decomposition"
    display_name = "Sentence Decomposition"
    description = "Word-by-word morphological breakdown with lemma matching"
    color_group = "green"
    needs_context = False
    needs_target_language = True

    def build_prompt(
        self,
        text: str,
        context: Optional[str] = None,
        target_language: Optional[str] = None,
        session: Optional[Any] = None,
    ) -> Tuple[str, str]:
        target_language = target_language or "en"

        # Build candidate lemmas section if DB session is available
        candidate_lemmas_section = self._build_candidate_section(
            text, target_language, session
        )

        system_context = util.prompt_loader.get_context(
            _PROMPT_CATEGORY, _PROMPT_TYPE
        )
        prompt = util.prompt_loader.get_prompt(
            _PROMPT_CATEGORY, _PROMPT_TYPE
        ).format(
            source_language=target_language,
            source_text=text,
            target_language=target_language,
            candidate_lemmas_section=candidate_lemmas_section,
        )
        return system_context, prompt

    def _build_candidate_section(
        self,
        text: str,
        target_language: str,
        session: Optional[Any],
    ) -> str:
        """Build the candidate lemmas section for the prompt.

        When a DB session is available, searches for matching lemmas using
        derivative forms. Otherwise returns an empty section.
        """
        if session is None:
            return "Candidate lemmas: (no database connection available)"

        try:
            from storage.models.schema import DerivativeForm, Lemma
            from storage.translation_helpers import get_translation

            # Find derivative forms matching words in the text
            words = text.split()
            candidate_lines = []
            seen_lemma_ids: set[int] = set()

            for word in words:
                clean_word = word.strip(".,;:!?\"'()-—")
                if not clean_word:
                    continue

                from sqlalchemy import func

                matching_forms = (
                    session.query(DerivativeForm)
                    .filter(
                        DerivativeForm.language_code == target_language,
                        func.lower(DerivativeForm.derivative_form_text)
                        == clean_word.lower(),
                    )
                    .limit(10)
                    .all()
                )

                for df in matching_forms:
                    if df.lemma_id in seen_lemma_ids:
                        continue
                    seen_lemma_ids.add(df.lemma_id)

                    lemma = (
                        session.query(Lemma)
                        .filter(Lemma.id == df.lemma_id)
                        .first()
                    )
                    if not lemma:
                        continue

                    guid = lemma.guid or ""
                    english = lemma.english_word or ""
                    disambiguation = lemma.disambiguation or ""
                    pos = lemma.word_role or ""

                    # Get translation in target language
                    trans = get_translation(session, lemma, target_language)
                    trans_str = f" | {target_language}={trans}" if trans else ""

                    candidate_lines.append(
                        f"- {guid} - {english} ({disambiguation}) | "
                        f"POS: {pos}{trans_str}"
                    )

            if candidate_lines:
                return (
                    "Candidate lemmas (use lemma_guid when a content word "
                    "maps to one):\n" + "\n".join(candidate_lines)
                )
        except Exception:
            pass

        return "Candidate lemmas: (none available)"

    def build_schema(self, **kwargs: Any) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "languages": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "language_code": {"type": "string"},
                            "translation": {"type": "string"},
                            "word_count": {"type": "integer"},
                            "words": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "position": {"type": "integer"},
                                        "role": {"type": "string"},
                                        "english_gloss": {"type": "string"},
                                        "surface_form": {"type": "string"},
                                        "grammatical_form": {"type": "string"},
                                        "lemma_guid": {"type": "string"},
                                        "lemma": {"type": "string"},
                                    },
                                    "required": [
                                        "position",
                                        "role",
                                        "english_gloss",
                                        "surface_form",
                                        "grammatical_form",
                                        "lemma_guid",
                                        "lemma",
                                    ],
                                },
                            },
                        },
                        "required": [
                            "language_code",
                            "translation",
                            "word_count",
                            "words",
                        ],
                    },
                }
            },
            "required": ["languages"],
        }

    def get_template_name(self) -> str:
        return "verbalator/results/decomposition.html"


register(DecompositionAction())
