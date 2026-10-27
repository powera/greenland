"""Batch-scoped snapshots for the mechanical builders' read-only inputs."""

from dataclasses import dataclass, field
from typing import Optional, cast

from sqlalchemy.orm import Session


@dataclass
class MechanicalInputs:
    facts: dict[tuple[int, str, str], Optional[str]] = field(default_factory=dict)
    translations: dict[tuple[int, str], str] = field(default_factory=dict)
    forms: dict[tuple[int, str], dict[str, str]] = field(default_factory=dict)

    @classmethod
    def load(cls, session: Session, lemma_ids: list[int]) -> "MechanicalInputs":
        from storage.models.grammar_fact import GrammarFact
        from storage.models.schema import DerivativeForm, LemmaTranslation

        snapshot = cls()
        for fact_row in session.query(
            GrammarFact.lemma_id,
            GrammarFact.language_code,
            GrammarFact.fact_type,
            GrammarFact.fact_value,
        ).filter(GrammarFact.lemma_id.in_(lemma_ids)):
            snapshot.facts[fact_row.lemma_id, fact_row.language_code, fact_row.fact_type] = (
                fact_row.fact_value
            )
        for translation_row in session.query(
            LemmaTranslation.lemma_id,
            LemmaTranslation.language_code,
            LemmaTranslation.translation,
        ).filter(LemmaTranslation.lemma_id.in_(lemma_ids)):
            snapshot.translations[translation_row.lemma_id, translation_row.language_code] = (
                translation_row.translation
            )
        for form_row in (
            session.query(
                DerivativeForm.lemma_id,
                DerivativeForm.language_code,
                DerivativeForm.grammatical_form,
                DerivativeForm.derivative_form_text,
            )
            .filter(DerivativeForm.lemma_id.in_(lemma_ids))
            .order_by(DerivativeForm.id)
        ):
            snapshot.forms.setdefault((form_row.lemma_id, form_row.language_code), {}).setdefault(
                form_row.grammatical_form, form_row.derivative_form_text
            )
        return snapshot

    def fact_value(self, lemma_id: int, language_code: str, fact_type: str) -> Optional[str]:
        from storage.crud.grammar_fact import _inherited_fact_language

        value = self.facts.get((lemma_id, language_code, fact_type))
        if value:
            return value
        parent = _inherited_fact_language(language_code, fact_type)
        return self.fact_value(lemma_id, parent, fact_type) if parent else value


def current_inputs(session: Session) -> Optional[MechanicalInputs]:
    """Snapshots are installed only while a generator batch is being planned."""
    return cast(Optional[MechanicalInputs], session.info.get("mechanical_inputs"))
