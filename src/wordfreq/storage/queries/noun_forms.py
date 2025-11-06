"""Noun form query functions."""

import logging
from typing import Dict, Any, Optional

from wordfreq.storage.models.schema import DerivativeForm
from wordfreq.storage.crud.lemma import get_lemma_by_guid


logger = logging.getLogger(__name__)


def get_noun_form(session, guid: str, grammatical_form: str) -> Optional[str]:
    """
    Get a specific declined form of a noun from the database.

    Args:
        session: Database session
        guid: The noun's GUID (e.g., "N02_001" for dog)
        grammatical_form: Form like "accusative_singular", "locative_singular", etc.

    Returns:
        The declined form text, or None if not found
    """
    lemma = get_lemma_by_guid(session, guid)
    if not lemma:
        logger.warning(f"No lemma found for GUID {guid}")
        return None

    # Try both formats: "noun_lt_" and "noun/lt_"
    full_form_underscore = f"noun_lt_{grammatical_form}"
    full_form_slash = f"noun/lt_{grammatical_form}"

    form = session.query(DerivativeForm).filter(
        DerivativeForm.lemma_id == lemma.id,
        DerivativeForm.language_code == 'lt',
        (DerivativeForm.grammatical_form == full_form_underscore) |
        (DerivativeForm.grammatical_form == full_form_slash)
    ).first()

    if not form:
        logger.warning(f"No {grammatical_form} form found for {lemma.lemma_text} (GUID: {guid})")
        return None

    return form.derivative_form_text


def get_all_noun_forms(session, guid: str) -> Dict[str, str]:
    """
    Get all declined forms of a noun from the database.

    Args:
        session: Database session
        guid: The noun's GUID (e.g., "N02_001")

    Returns:
        Dictionary mapping grammatical form names to declined text
    """
    lemma = get_lemma_by_guid(session, guid)
    if not lemma:
        return {}

    # Check both formats: "noun_lt_" and "noun/lt_"
    forms = session.query(DerivativeForm).filter(
        DerivativeForm.lemma_id == lemma.id,
        DerivativeForm.language_code == 'lt',
        (DerivativeForm.grammatical_form.like('noun_lt_%') |
         DerivativeForm.grammatical_form.like('noun/lt_%'))
    ).all()

    result = {}
    for form in forms:
        # Strip the "noun_lt_" or "noun/lt_" prefix to get the short form name
        short_name = form.grammatical_form.replace('noun_lt_', '').replace('noun/lt_', '')
        result[short_name] = form.derivative_form_text

    return result


def check_noun_forms_coverage(session, guid: str) -> Dict[str, Any]:
    """
    Check which noun forms are available in the database for a given GUID.

    Args:
        session: Database session
        guid: The noun's GUID

    Returns:
        Dictionary with coverage information
    """
    lemma = get_lemma_by_guid(session, guid)
    if not lemma:
        return {
            "guid": guid,
            "found": False,
            "lemma_text": None,
            "lithuanian": None,
            "forms_count": 0,
            "missing_forms": [],
            "is_plurale_tantum": False
        }

    all_forms = get_all_noun_forms(session, guid)

    # Check if this is a plurale tantum (plural-only noun)
    # These will only have plural forms (7 forms instead of 14)
    singular_forms = [f for f in all_forms.keys() if "singular" in f]
    plural_forms = [f for f in all_forms.keys() if "plural" in f]
    is_plurale_tantum = len(singular_forms) == 0 and len(plural_forms) > 0

    if is_plurale_tantum:
        expected_forms = [
            "nominative_plural", "genitive_plural", "dative_plural",
            "accusative_plural", "instrumental_plural", "locative_plural", "vocative_plural"
        ]
    else:
        expected_forms = [
            "nominative_singular", "genitive_singular", "dative_singular",
            "accusative_singular", "instrumental_singular", "locative_singular", "vocative_singular",
            "nominative_plural", "genitive_plural", "dative_plural",
            "accusative_plural", "instrumental_plural", "locative_plural", "vocative_plural"
        ]

    missing = [f for f in expected_forms if f not in all_forms]

    return {
        "guid": guid,
        "found": True,
        "lemma_text": lemma.lemma_text,
        "lithuanian": lemma.lithuanian_translation,
        "forms_count": len(all_forms),
        "expected_count": len(expected_forms),
        "missing_forms": missing,
        "has_all_forms": len(missing) == 0,
        "is_plurale_tantum": is_plurale_tantum
    }
