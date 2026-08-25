"""CRUD operations for DerivativeForm model."""

import logging
from typing import Dict, List, Optional

from sqlalchemy import ColumnElement, and_, not_, or_, true
from sqlalchemy.orm import Session

from storage.crud.operation_log import (
    DERIVATIVE_FORM_CREATE,
    DERIVATIVE_FORM_DELETE,
    DERIVATIVE_FORM_UPDATE,
    FieldChange,
    log_entity_operation,
    log_field_changes,
)
from storage.crud.word_token import add_word_token
from storage.models.schema import DerivativeForm, Lemma, WordToken

logger = logging.getLogger(__name__)

COMMON_SURFACED_GRAMMATICAL_FORMS: set[str] = {
    "lemma",
    "infinitive",
    "singular",
    "plural",
    "positive",
    "present",
    "past",
    "past_tense",
    "third_person_singular_present",
    "third_person_plural_present",
}


def needs_pronunciation_update_filter() -> ColumnElement[bool]:
    """Return a reusable filter for forms missing IPA or phonetic pronunciation.

    Treats both NULL and empty-string values as missing so callers can use one
    consistent definition everywhere Papuga looks for incomplete pronunciation
    data.
    """

    return or_(
        DerivativeForm.ipa_pronunciation.is_(None),
        DerivativeForm.ipa_pronunciation == "",
        DerivativeForm.phonetic_pronunciation.is_(None),
        DerivativeForm.phonetic_pronunciation == "",
    )


def pronunciation_required_filter(include_optional_forms: bool = False) -> ColumnElement[bool]:
    """Return filter for forms that should receive pronunciation generation by default.

    Conservative defaults:
    - Always include base forms.
    - Include commonly surfaced inflections.
    - Skip English periphrastic futures (``*_future``) unless explicitly requested.
    """

    if include_optional_forms:
        return true()

    common_form_filter = DerivativeForm.grammatical_form.in_(COMMON_SURFACED_GRAMMATICAL_FORMS)
    skip_english_future_filter = not_(
        and_(
            DerivativeForm.language_code == "en",
            DerivativeForm.grammatical_form.like("%_future"),
        )
    )
    return and_(
        or_(DerivativeForm.is_base_form.is_(True), common_form_filter),
        skip_english_future_filter,
    )


def add_derivative_form(
    session: Session,
    lemma: Lemma,
    derivative_form_text: str,
    language_code: str,
    grammatical_form: str,
    word_token: Optional[WordToken] = None,
    is_base_form: bool = False,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    verified: bool = False,
    notes: Optional[str] = None,
    source: Optional[str] = None,
) -> DerivativeForm:
    """Add a derivative form for a lemma in a specific language.

    ``source`` names who is making the change, for the operation log; None
    skips logging. A derivative form has no GUID of its own, so the entry is
    keyed to the owning lemma's GUID with the form's identity in the fact.
    Re-adding an identical form returns the existing row and logs nothing.
    """
    try:
        # Check if this derivative form already exists
        existing = (
            session.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == language_code,
                DerivativeForm.grammatical_form == grammatical_form,
                DerivativeForm.derivative_form_text == derivative_form_text,
            )
            .first()
        )

        if existing:
            result: DerivativeForm = existing
            return result

        # Validate that word_token language matches if provided
        if word_token and word_token.language_code != language_code:
            raise ValueError(
                f"WordToken language_code '{word_token.language_code}' does not match derivative form language_code '{language_code}'"
            )

        derivative_form = DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text=derivative_form_text,
            word_token_id=word_token.id if word_token else None,
            language_code=language_code,
            grammatical_form=grammatical_form,
            is_base_form=is_base_form,
            ipa_pronunciation=ipa_pronunciation,
            phonetic_pronunciation=phonetic_pronunciation,
            verified=verified,
            notes=notes,
        )

        session.add(derivative_form)
        session.flush()

        if source is not None:
            log_entity_operation(
                session,
                source=source,
                operation_type=DERIVATIVE_FORM_CREATE,
                entity_guid=lemma.guid,
                fact={
                    "language_code": language_code,
                    "grammatical_form": grammatical_form,
                    "text": derivative_form_text,
                    "is_base_form": is_base_form,
                },
                lemma_id=lemma.id,
                derivative_form_id=derivative_form.id,
            )
        return derivative_form
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding derivative form: {e}")
        raise


def update_derivative_form(
    session: Session,
    derivative_form_id: int,
    derivative_form_text: Optional[str] = None,
    grammatical_form: Optional[str] = None,
    is_base_form: Optional[bool] = None,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None,
    source: Optional[str] = None,
) -> bool:
    """Update derivative form information.

    ``source`` names who is making the edit, for the operation log; None skips
    logging, as does an update where no field actually changes.
    """
    derivative_form = (
        session.query(DerivativeForm).filter(DerivativeForm.id == derivative_form_id).first()
    )
    if not derivative_form:
        return False

    # Captured before the assignments so the log records the real diff. Only
    # supplied fields are candidates, matching the assignments below, so "not
    # passed" never reads as "cleared".
    changes = [
        FieldChange(field, getattr(derivative_form, field), new_value)
        for field, new_value in (
            ("derivative_form_text", derivative_form_text),
            ("grammatical_form", grammatical_form),
            ("is_base_form", is_base_form),
            ("ipa_pronunciation", ipa_pronunciation),
            ("phonetic_pronunciation", phonetic_pronunciation),
            ("verified", verified),
            ("notes", notes),
        )
        if new_value is not None
    ]
    lemma_guid = derivative_form.lemma.guid if derivative_form.lemma else None
    lemma_id = derivative_form.lemma_id
    language_code = derivative_form.language_code

    if derivative_form_text is not None:
        derivative_form.derivative_form_text = derivative_form_text
    if grammatical_form is not None:
        derivative_form.grammatical_form = grammatical_form
    if is_base_form is not None:
        derivative_form.is_base_form = is_base_form
    if ipa_pronunciation is not None:
        derivative_form.ipa_pronunciation = ipa_pronunciation
    if phonetic_pronunciation is not None:
        derivative_form.phonetic_pronunciation = phonetic_pronunciation
    if verified is not None:
        derivative_form.verified = verified
    if notes is not None:
        derivative_form.notes = notes

    log_field_changes(
        session,
        source=source,
        operation_type=DERIVATIVE_FORM_UPDATE,
        entity_guid=lemma_guid,
        changes=changes,
        extra={"language_code": language_code},
        lemma_id=lemma_id,
    )
    session.commit()
    return True


def delete_derivative_form(
    session: Session, derivative_form_id: int, source: Optional[str] = None
) -> bool:
    """
    Delete a specific derivative form.

    Args:
        session: Database session
        derivative_form_id: ID of the derivative form to delete
        source: Who is deleting this, for the operation log. None skips
            logging.

    Returns:
        Success flag
    """
    try:
        derivative_form = (
            session.query(DerivativeForm).filter(DerivativeForm.id == derivative_form_id).first()
        )
        if derivative_form:
            # Logged before the delete, while the row is still there to
            # describe. The entry outlives it, which is the point.
            if source is not None:
                log_entity_operation(
                    session,
                    source=source,
                    operation_type=DERIVATIVE_FORM_DELETE,
                    entity_guid=(derivative_form.lemma.guid if derivative_form.lemma else None),
                    fact={
                        "language_code": derivative_form.language_code,
                        "grammatical_form": derivative_form.grammatical_form,
                        "text": derivative_form.derivative_form_text,
                    },
                    lemma_id=derivative_form.lemma_id,
                )
            session.delete(derivative_form)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting derivative form ID {derivative_form_id}: {e}")
        return False


def delete_derivative_forms_for_token(session: Session, word_token_id: int) -> bool:
    """
    Delete all derivative forms for a word token.

    Args:
        session: Database session
        word_token_id: ID of the word token to delete derivative forms for

    Returns:
        Success flag
    """
    try:
        # Query all derivative forms for the word token
        derivative_forms = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.word_token_id == word_token_id)
            .all()
        )

        # Delete each derivative form (cascade will handle example sentences)
        for derivative_form in derivative_forms:
            session.delete(derivative_form)

        # Commit the transaction
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting derivative forms for word token ID {word_token_id}: {e}")
        return False


def get_all_derivative_forms_for_token(
    session: Session, token_text: str, language_code: str
) -> List[DerivativeForm]:
    """Get all derivative forms for a word token."""
    from storage.crud.word_token import get_word_token_by_text

    word_token = get_word_token_by_text(session, token_text, language_code)
    if not word_token:
        return []
    result: list[DerivativeForm] = word_token.derivative_forms
    return result


def get_all_derivative_forms_for_lemma(
    session: Session, lemma_text: str, pos_type: Optional[str] = None
) -> List[DerivativeForm]:
    """Get all derivative forms for a lemma."""
    query = session.query(DerivativeForm).join(Lemma).filter(Lemma.lemma_text == lemma_text)

    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)

    forms: list[DerivativeForm] = query.all()
    return forms


def get_base_forms_for_lemma(
    session: Session, lemma_text: str, pos_type: Optional[str] = None
) -> List[DerivativeForm]:
    """Get base forms for a lemma."""
    query = (
        session.query(DerivativeForm)
        .join(Lemma)
        .filter(Lemma.lemma_text == lemma_text)
        .filter(DerivativeForm.is_base_form == True)
    )

    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)

    result: list[DerivativeForm] = query.all()
    return result


def get_derivative_forms_without_pronunciation(
    session: Session, limit: int = 100
) -> List[DerivativeForm]:
    """Get derivative forms that need pronunciation information."""
    result: list[DerivativeForm] = (
        session.query(DerivativeForm).filter(needs_pronunciation_update_filter()).limit(limit).all()
    )
    return result


def get_derivative_forms_by_grammatical_form(
    session: Session, grammatical_form: str, limit: int = 100
) -> List[DerivativeForm]:
    """Get derivative forms by specific grammatical form."""
    result: list[DerivativeForm] = (
        session.query(DerivativeForm)
        .filter(DerivativeForm.grammatical_form == grammatical_form)
        .limit(limit)
        .all()
    )
    return result


def get_base_forms_only(session: Session, limit: int = 100) -> List[DerivativeForm]:
    """Get only base forms (infinitives, singulars, etc.)."""
    result: list[DerivativeForm] = (
        session.query(DerivativeForm).filter(DerivativeForm.is_base_form == True).limit(limit).all()
    )
    return result


def add_noun_derivative_form(
    session: Session,
    lemma: Lemma,
    form_text: str,
    grammatical_form: str,
    language_code: str = "lt",
    is_base_form: bool = False,
    verified: bool = False,
    notes: Optional[str] = None,
) -> Optional[DerivativeForm]:
    """
    Add a derivative form for a noun (e.g., plural form).

    Args:
        session: Database session
        lemma: The lemma this form belongs to
        form_text: The actual form text (e.g., "vilkai")
        grammatical_form: The grammatical form type (e.g., "plural_nominative")
        language_code: Language code (default: "lt")
        is_base_form: Whether this is a base form (default: False)
        verified: Whether this form is verified (default: False)
        notes: Optional notes

    Returns:
        DerivativeForm object or None if creation failed
    """
    try:
        # Get or create word token
        word_token = add_word_token(session, form_text, language_code)

        # Check if this derivative form already exists
        existing_form = (
            session.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.derivative_form_text == form_text,
                DerivativeForm.language_code == language_code,
                DerivativeForm.grammatical_form == grammatical_form,
            )
            .first()
        )

        if existing_form:
            logger.debug(f"Derivative form already exists: {form_text} ({grammatical_form})")
            result: DerivativeForm = existing_form
            return result

        # Create new derivative form
        derivative_form = DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text=form_text,
            word_token_id=word_token.id,
            language_code=language_code,
            grammatical_form=grammatical_form,
            is_base_form=is_base_form,
            verified=verified,
            notes=notes,
        )

        session.add(derivative_form)
        session.commit()

        logger.info(
            f"Added noun derivative form: {form_text} ({grammatical_form}) for lemma {lemma.lemma_text}"
        )
        return derivative_form

    except Exception as e:
        session.rollback()
        logger.error(f"Failed to add noun derivative form {form_text}: {e}")
        return None


def get_noun_derivative_forms(session: Session, lemma_id: int) -> List[DerivativeForm]:
    """
    Get all noun derivative forms for a lemma.

    Args:
        session: Database session
        lemma_id: Lemma ID to get forms for

    Returns:
        List of DerivativeForm objects
    """
    result: list[DerivativeForm] = (
        session.query(DerivativeForm)
        .filter(DerivativeForm.lemma_id == lemma_id, DerivativeForm.language_code == "lt")
        .all()
    )
    return result


def has_specific_noun_forms(
    session: Session, lemma_id: int, required_forms: List[str]
) -> Dict[str, bool]:
    """
    Check if specific noun forms exist for a lemma.

    Args:
        session: Database session
        lemma_id: Lemma ID to check
        required_forms: List of grammatical form names to check for

    Returns:
        Dictionary mapping form names to whether they exist
    """
    existing_forms = (
        session.query(DerivativeForm.grammatical_form)
        .filter(
            DerivativeForm.lemma_id == lemma_id,
            DerivativeForm.language_code == "lt",
            DerivativeForm.grammatical_form.in_(required_forms),
        )
        .all()
    )

    existing_form_names = {form[0] for form in existing_forms}

    return {form: form in existing_form_names for form in required_forms}


def get_grammatical_forms_for_token(
    session: Session, token_text: str, language_code: str
) -> List[str]:
    """Get all grammatical forms available for a specific token."""
    from storage.crud.word_token import get_word_token_by_text

    word_token = get_word_token_by_text(session, token_text, language_code)
    if not word_token:
        return []

    forms = (
        session.query(DerivativeForm.grammatical_form)
        .filter(DerivativeForm.word_token_id == word_token.id)
        .distinct()
        .all()
    )

    return [form[0] for form in forms]


def add_alternative_form(
    session: Session,
    lemma: Lemma,
    alternative_text: str,
    language_code: str,
    alternative_type: str,
    explanation: str,
    word_token: Optional[WordToken] = None,
) -> DerivativeForm:
    """
    Add an alternative form for a lemma.

    .. deprecated::
        This is the pre-``variant_forms`` mechanism and writes
        ``grammatical_form`` values (``alternative_variant``,
        ``alternative_informal``, ...) that nothing reads any more.  The live
        database holds **zero** such rows.  Do not call it in new code:

        * an alternate *spelling* ("grey" for "gray") is a
          :class:`~storage.models.variant_form.VariantForm`; it carries a full
          paradigm, which a single derivative row cannot represent.  Use
          ``words.synonyms.store_spelling_variants``.
        * a different *lexeme* ("bike" for "bicycle") is a synonym-class
          derivative form; use ``add_derivative_form`` with one of
          :data:`~storage.models.schema.SYNONYM_GRAMMATICAL_FORMS`,
          ``abbreviation`` or ``expanded_form``.

        Kept only until the remaining callers are migrated; slated for removal
        once they are.

    Args:
        session: Database session
        lemma: The lemma this is an alternative for
        alternative_text: The alternative text (e.g., "bike")
        language_code: Language code (e.g., "en", "lt")
        alternative_type: Type of alternative ("informal", "abbreviation", "formal", "variant", "technical")
        explanation: Human-readable explanation (e.g., "Informal term for bicycle")
        word_token: Optional WordToken for frequency data

    Returns:
        DerivativeForm: The created alternative form
    """
    grammatical_form = f"alternative_{alternative_type}"

    return add_derivative_form(
        session=session,
        lemma=lemma,
        derivative_form_text=alternative_text,
        language_code=language_code,
        grammatical_form=grammatical_form,
        word_token=word_token,
        is_base_form=False,
        notes=explanation,
    )


def get_alternative_forms_for_lemma(
    session: Session, lemma: Lemma, language_code: Optional[str] = None
) -> List[DerivativeForm]:
    """
    Get all alternative forms for a lemma (abbreviations, expanded forms, and alternate spellings).
    This excludes synonyms, which are a separate category.

    The ``abbreviation`` and ``expanded_form`` half of this is current.  The
    ``alternate_spelling`` / ``alternative_form`` half is **deprecated** and
    matches nothing: alternate spellings moved to ``variant_forms`` (see
    :mod:`storage.models.variant_form`) and no such rows remain.  A caller that
    wants spellings should read ``variant_forms`` via
    ``storage.crud.variant_form``; those legacy values are slated for removal.

    Args:
        session: Database session
        lemma: The lemma to get alternatives for
        language_code: Optional language filter

    Returns:
        List[DerivativeForm]: List of alternative forms
    """
    # Alternative forms include: abbreviation, expanded_form, alternate_spelling
    # Also handle legacy 'alternative_form' values for backward compatibility
    query = (
        session.query(DerivativeForm)
        .filter(DerivativeForm.lemma_id == lemma.id)
        .filter(
            DerivativeForm.grammatical_form.in_(
                [
                    "abbreviation",
                    "expanded_form",
                    "alternate_spelling",
                    "alternative_form",  # Legacy value
                ]
            )
        )
    )

    if language_code:
        query = query.filter(DerivativeForm.language_code == language_code)

    result: list[DerivativeForm] = query.all()
    return result


def add_complete_word_entry(
    session: Session,
    token: str,
    lemma_text: str,
    definition_text: str,
    pos_type: str,
    grammatical_form: str,
    pos_subtype: Optional[str] = None,
    is_base_form: bool = False,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    difficulty_level: Optional[int] = None,
    frequency_rank: Optional[int] = None,
    tags: Optional[List[str]] = None,
    translations: Optional[object] = None,  # Can be TranslationSet or None
    chinese_translation: Optional[str] = None,
    french_translation: Optional[str] = None,
    spanish_translation: Optional[str] = None,
    korean_translation: Optional[str] = None,
    swahili_translation: Optional[str] = None,
    lithuanian_translation: Optional[str] = None,
    vietnamese_translation: Optional[str] = None,
    confidence: float = 0.0,
    verified: bool = False,
    notes: Optional[str] = None,
    auto_generate_guid: bool = True,
    sense_prominence: Optional[str] = None,
) -> DerivativeForm:
    """
    Convenience function to add a complete word entry (token + lemma + derivative form).
    This replaces the old add_definition function for most use cases.

    Note: Lemmas are always English ('en').

    Args:
        translations: Optional TranslationSet object. If provided, individual translation
                     parameters are ignored.
        sense_prominence: How common this sense is for its surface form; passed
                     through to the lemma. None keeps the schema default.
    """
    from storage.crud.lemma import add_lemma
    from storage.crud.word_token import add_word_token

    language_code = "en"

    # Extract translations from TranslationSet if provided
    if translations is not None:
        from storage.models.translations import TranslationSet

        if isinstance(translations, TranslationSet):
            chinese_translation = translations.chinese.text if translations.chinese else None
            french_translation = translations.french.text if translations.french else None
            spanish_translation = translations.spanish.text if translations.spanish else None
            korean_translation = translations.korean.text if translations.korean else None
            swahili_translation = translations.swahili.text if translations.swahili else None
            lithuanian_translation = (
                translations.lithuanian.text if translations.lithuanian else None
            )
            vietnamese_translation = (
                translations.vietnamese.text if translations.vietnamese else None
            )

    # Add or get word token
    word_token = add_word_token(session, token, language_code)

    # Add or get lemma
    lemma = add_lemma(
        session=session,
        lemma_text=lemma_text,
        definition_text=definition_text,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        difficulty_level=difficulty_level,
        frequency_rank=frequency_rank,
        tags=tags,
        chinese_translation=chinese_translation,
        french_translation=french_translation,
        spanish_translation=spanish_translation,
        korean_translation=korean_translation,
        swahili_translation=swahili_translation,
        lithuanian_translation=lithuanian_translation,
        vietnamese_translation=vietnamese_translation,
        confidence=confidence,
        verified=verified,
        notes=notes,
        auto_generate_guid=auto_generate_guid,
        sense_prominence=sense_prominence,
    )

    # Add derivative form
    derivative_form = add_derivative_form(
        session=session,
        lemma=lemma,
        derivative_form_text=token,  # For single-word forms, derivative_form_text is the same as token
        language_code=language_code,
        grammatical_form=grammatical_form,
        word_token=word_token,
        is_base_form=is_base_form,
        ipa_pronunciation=ipa_pronunciation,
        phonetic_pronunciation=phonetic_pronunciation,
        verified=verified,
        notes=notes,
    )

    return derivative_form
