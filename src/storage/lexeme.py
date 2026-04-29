"""Sense-aware (Lexeme) access facade over DerivativeForm.

A Lexeme represents one meaning sense of a word in one language: the pairing of
a Lemma (the conceptual sense) with its language-specific surface forms
(base form, inflections, synonyms, abbreviations, expanded forms) drawn from
the DerivativeForm table.

This module composes existing CRUD calls in storage/crud/derivative_form.py;
it does not introduce a new SQLAlchemy model. The partial unique index
``ix_derivative_forms_synonym_unique_per_lang`` on ``derivative_forms``
guarantees that a synonym-class surface form in a given language attaches to
at most one Lemma, which is what makes ``get_lexeme_for_synonym`` well-defined.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from storage.models.schema import (
    SYNONYM_GRAMMATICAL_FORMS,
    DerivativeForm,
    Lemma,
)


def _all_forms_for_lemma_id(session: Session, lemma_id: int) -> List[DerivativeForm]:
    return session.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma_id).all()


@dataclass(frozen=True)
class Lexeme:
    """One meaning sense of a word in one language.

    Identity is ``(lemma.id, language_code)``. ``forms`` holds every
    DerivativeForm row tying that Lemma to that language.
    """

    lemma: Lemma
    language_code: str
    forms: List[DerivativeForm] = field(default_factory=list)

    @property
    def base_form(self) -> Optional[DerivativeForm]:
        """The first DerivativeForm flagged ``is_base_form`` for this lexeme, if any."""
        for form in self.forms:
            if form.is_base_form:
                return form
        return None

    @property
    def synonyms(self) -> List[DerivativeForm]:
        """Synonym-class forms (any of SYNONYM_GRAMMATICAL_FORMS)."""
        return [f for f in self.forms if f.grammatical_form in SYNONYM_GRAMMATICAL_FORMS]

    @property
    def inflections(self) -> List[DerivativeForm]:
        """Forms that are neither synonyms nor abbreviations/expanded forms."""
        non_inflection = SYNONYM_GRAMMATICAL_FORMS | {"abbreviation", "expanded_form"}
        return [f for f in self.forms if f.grammatical_form not in non_inflection]


def _build_lexeme(session: Session, lemma: Lemma, language_code: str) -> Optional[Lexeme]:
    """Assemble a Lexeme from a Lemma + language. Returns None if no forms exist."""
    all_forms = _all_forms_for_lemma_id(session, lemma.id)
    forms = [f for f in all_forms if f.language_code == language_code]
    if not forms:
        return None
    return Lexeme(lemma=lemma, language_code=language_code, forms=forms)


def get_lexeme(session: Session, lemma_id: int, language_code: str) -> Optional[Lexeme]:
    """Return the Lexeme for ``(lemma_id, language_code)``, or None."""
    lemma = session.query(Lemma).filter(Lemma.id == lemma_id).first()
    if lemma is None:
        return None
    return _build_lexeme(session, lemma, language_code)


def get_lexeme_for_synonym(
    session: Session, form_text: str, language_code: str
) -> Optional[Lexeme]:
    """Return the unique Lexeme that owns ``form_text`` as a synonym-class form.

    Relies on the partial unique index over synonym grammatical forms so that
    at most one Lemma can claim a given synonym surface string in a language.
    Returns None if no synonym row matches.
    """
    row = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.derivative_form_text == form_text,
            DerivativeForm.language_code == language_code,
            DerivativeForm.grammatical_form.in_(tuple(SYNONYM_GRAMMATICAL_FORMS)),
        )
        .first()
    )
    if row is None:
        return None
    return get_lexeme(session, row.lemma_id, language_code)


def get_candidate_lexemes_for_form(
    session: Session, form_text: str, language_code: str
) -> List[Lexeme]:
    """Return every Lexeme that contains ``form_text`` in ``language_code``.

    May return more than one for legitimate homograph lemmas (e.g. "bank" the
    river edge vs. "bank" the financial institution both have a base form
    "bank").
    """
    rows = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.derivative_form_text == form_text,
            DerivativeForm.language_code == language_code,
        )
        .all()
    )
    seen: Dict[Tuple[int, str], Lexeme] = {}
    for row in rows:
        key = (row.lemma_id, language_code)
        if key in seen:
            continue
        lexeme = get_lexeme(session, row.lemma_id, language_code)
        if lexeme is not None:
            seen[key] = lexeme
    return list(seen.values())


def list_lexemes_for_lemma(session: Session, lemma_id: int) -> List[Lexeme]:
    """Return one Lexeme per language the lemma has DerivativeForms in."""
    lemma = session.query(Lemma).filter(Lemma.id == lemma_id).first()
    if lemma is None:
        return []
    all_forms = _all_forms_for_lemma_id(session, lemma_id)
    by_language: Dict[str, List[DerivativeForm]] = {}
    for form in all_forms:
        by_language.setdefault(form.language_code, []).append(form)
    return [
        Lexeme(lemma=lemma, language_code=lang, forms=forms) for lang, forms in by_language.items()
    ]
