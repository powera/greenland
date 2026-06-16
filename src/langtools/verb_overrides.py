"""Helpers for applying database-backed verb form overrides."""

from __future__ import annotations

from typing import Dict, Mapping

from langtools.form_registry import FORM_SPECS
from sqlalchemy.orm import Session
from storage.crud.grammar_fact import get_verb_form_overrides


def get_required_verb_form_keys(language_code: str) -> set[str]:
    """Return form keys required by the language's verb form registry."""
    spec = FORM_SPECS.get((language_code, "verb"))
    if spec is None:
        return set()
    return set(spec.form_mapping)


def apply_verb_form_overrides(
    forms: Mapping[str, str] | None, overrides: Mapping[str, str]
) -> Dict[str, str] | None:
    """Apply exact form overrides to a generated form mapping."""
    if not forms and not overrides:
        return None
    merged: Dict[str, str] = dict(forms or {})
    merged.update({form_key: value for form_key, value in overrides.items() if value})
    return merged


def get_complete_verb_form_overrides(
    session: Session, lemma_id: int, language_code: str
) -> Dict[str, str] | None:
    """Return overrides only if they cover all registry-required verb forms."""
    overrides = get_verb_form_overrides(session, lemma_id, language_code)
    required_keys = get_required_verb_form_keys(language_code)
    if required_keys and required_keys.issubset(overrides):
        return {form_key: overrides[form_key] for form_key in required_keys}
    return None
