"""CRUD operations for VariantForm model.

Variant forms are alternate spellings of the same lexeme ("grey" for "gray").
See storage.models.variant_form for why these live outside derivative_forms.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from storage.crud.word_token import add_word_token
from storage.models.schema import Lemma, WordToken
from storage.models.variant_form import VARIANT_KIND_SPELLING, VariantForm

logger = logging.getLogger(__name__)


def add_variant_form(
    session: Session,
    lemma: Lemma,
    variant_form_text: str,
    language_code: str,
    variant_key: str,
    grammatical_form: str,
    variant_kind: str = VARIANT_KIND_SPELLING,
    is_base_form: bool = False,
    word_token: Optional[WordToken] = None,
    link_word_token: bool = True,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
) -> VariantForm:
    """Add (or update) one grammatical form of a variant paradigm.

    Idempotent on the unique key (lemma, language, kind, key, grammatical_form):
    calling it again with different text updates the existing row rather than
    raising, which keeps re-running a backfill safe.

    Args:
        session: Database session
        lemma: The lemma this is a variant of (e.g. the "gray" lemma)
        variant_form_text: Text of this form (e.g. "greyer")
        language_code: Language code (e.g. "en")
        variant_key: Which variant this belongs to, conventionally the
            variant's own base form (e.g. "grey")
        grammatical_form: Grammatical slot (e.g. "adjective/en_comparative")
        variant_kind: Kind of variant; defaults to "spelling"
        is_base_form: True for the variant's own base form
        word_token: Optional pre-resolved WordToken for frequency data
        link_word_token: When True and no word_token is given, look up or
            create one for single-word forms.  Multi-word forms are skipped.
        ipa_pronunciation: Optional IPA for this form
        phonetic_pronunciation: Optional simplified pronunciation
        verified: Whether this form has been verified
        notes: Optional free-text notes

    Returns:
        VariantForm: The created or updated row
    """
    existing = (
        session.query(VariantForm)
        .filter(
            VariantForm.lemma_id == lemma.id,
            VariantForm.language_code == language_code,
            VariantForm.variant_kind == variant_kind,
            VariantForm.variant_key == variant_key,
            VariantForm.grammatical_form == grammatical_form,
        )
        .first()
    )

    resolved_token = word_token
    if resolved_token is None and link_word_token and " " not in variant_form_text.strip():
        resolved_token = add_word_token(session, variant_form_text, language_code)

    if existing is not None:
        existing.variant_form_text = variant_form_text
        existing.is_base_form = is_base_form
        if resolved_token is not None:
            existing.word_token_id = resolved_token.id
        if ipa_pronunciation is not None:
            existing.ipa_pronunciation = ipa_pronunciation
        if phonetic_pronunciation is not None:
            existing.phonetic_pronunciation = phonetic_pronunciation
        if notes is not None:
            existing.notes = notes
        existing.verified = verified
        session.flush()
        return existing

    variant_form = VariantForm(
        lemma_id=lemma.id,
        language_code=language_code,
        variant_kind=variant_kind,
        variant_key=variant_key,
        grammatical_form=grammatical_form,
        variant_form_text=variant_form_text,
        word_token_id=resolved_token.id if resolved_token is not None else None,
        is_base_form=is_base_form,
        ipa_pronunciation=ipa_pronunciation,
        phonetic_pronunciation=phonetic_pronunciation,
        verified=verified,
        notes=notes,
    )
    session.add(variant_form)
    session.flush()
    return variant_form


def get_variant_forms_for_lemma(
    session: Session,
    lemma: Lemma,
    language_code: Optional[str] = None,
    variant_kind: Optional[str] = None,
) -> List[VariantForm]:
    """Get all variant forms for a lemma, optionally filtered by language/kind."""
    query = session.query(VariantForm).filter(VariantForm.lemma_id == lemma.id)

    if language_code:
        query = query.filter(VariantForm.language_code == language_code)
    if variant_kind:
        query = query.filter(VariantForm.variant_kind == variant_kind)

    result: List[VariantForm] = query.order_by(
        VariantForm.variant_key, VariantForm.grammatical_form
    ).all()
    return result


def get_variant_paradigms_for_lemma(
    session: Session,
    lemma: Lemma,
    language_code: Optional[str] = None,
) -> Dict[str, List[VariantForm]]:
    """Group a lemma's variant forms into paradigms keyed by variant_key.

    Returns:
        Mapping of variant_key -> its forms, e.g. {"grey": [grey, greyer, greyest]}
    """
    paradigms: Dict[str, List[VariantForm]] = {}
    for form in get_variant_forms_for_lemma(session, lemma, language_code=language_code):
        paradigms.setdefault(form.variant_key, []).append(form)
    return paradigms


def find_lemmas_by_variant_text(
    session: Session,
    text_value: str,
    language_code: str = "en",
) -> List[Lemma]:
    """Find lemmas having a variant form matching this text (case-insensitive).

    This is the reverse lookup behind "which lemma is 'grey'?", and the entry
    point for duplicate detection: a wordlist offering "grey" should resolve to
    the existing "gray" lemma rather than being staged as a new word.

    Returns a list because a surface form can in principle be a variant of more
    than one lemma (homographs).
    """
    normalized = text_value.strip().lower()
    if not normalized:
        return []

    result: List[Lemma] = (
        session.query(Lemma)
        .join(VariantForm, VariantForm.lemma_id == Lemma.id)
        .filter(
            VariantForm.language_code == language_code,
            func.lower(VariantForm.variant_form_text) == normalized,
        )
        .distinct()
        .all()
    )
    return result


def get_all_variant_texts(session: Session, language_code: str = "en") -> Dict[str, str]:
    """Map every variant surface form to its lemma's text, for bulk checks.

    Used by wordlist coverage, which needs to test thousands of candidate words
    against the database without a query per word.

    Returns:
        Mapping of lowercased variant text -> lowercased lemma text
    """
    rows = (
        session.query(VariantForm.variant_form_text, Lemma.lemma_text)
        .join(Lemma, VariantForm.lemma_id == Lemma.id)
        .filter(VariantForm.language_code == language_code)
        .all()
    )
    return {variant_text.lower(): lemma_text.lower() for variant_text, lemma_text in rows}


def delete_variant(
    session: Session,
    lemma: Lemma,
    variant_key: str,
    language_code: str = "en",
    variant_kind: str = VARIANT_KIND_SPELLING,
) -> int:
    """Delete an entire variant paradigm for a lemma.

    Returns:
        Number of rows deleted
    """
    deleted: int = (
        session.query(VariantForm)
        .filter(
            VariantForm.lemma_id == lemma.id,
            VariantForm.language_code == language_code,
            VariantForm.variant_kind == variant_kind,
            VariantForm.variant_key == variant_key,
        )
        .delete(synchronize_session=False)
    )
    session.flush()
    return deleted
