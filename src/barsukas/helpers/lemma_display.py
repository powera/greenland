"""Lemma display and UI helper functions for Barsukas."""

from typing import Dict, List, Tuple
from wordfreq.storage.queries.lemma import get_difficulty_stats


def group_derivative_forms(derivative_forms) -> Tuple[Dict, Dict, Dict, List[str]]:
    """
    Group derivative forms by language and type for UI display.

    Separates forms into three categories:
    - Regular grammatical forms (conjugations, declensions, etc.)
    - Synonyms
    - Alternative forms (abbreviations, alternate spellings, etc.)

    Args:
        derivative_forms: List of DerivativeForm objects

    Returns:
        Tuple of (forms_by_language, synonyms_by_language,
                  alternative_forms_by_language, all_synonym_languages)
    """
    forms_by_language = {}
    synonyms_by_language = {}
    alternative_forms_by_language = {}

    for form in derivative_forms:
        lang_code = form.language_code

        # Separate synonyms and alternative forms
        # Alternative forms include: abbreviation, expanded_form, alternate_spelling, and legacy 'alternative_form'
        is_alternative = form.grammatical_form in [
            "abbreviation",
            "expanded_form",
            "alternate_spelling",
            "alternative_form",
        ]
        is_synonym = form.grammatical_form == "synonym"

        if is_synonym:
            if lang_code not in synonyms_by_language:
                synonyms_by_language[lang_code] = []
            synonyms_by_language[lang_code].append(form)
        elif is_alternative:
            if lang_code not in alternative_forms_by_language:
                alternative_forms_by_language[lang_code] = []
            alternative_forms_by_language[lang_code].append(form)
        else:
            # Regular grammatical forms (conjugations, declensions, etc.)
            if lang_code not in forms_by_language:
                forms_by_language[lang_code] = []
            forms_by_language[lang_code].append(form)

    # Get all languages that have synonyms or alternatives
    all_synonym_languages = sorted(
        set(list(synonyms_by_language.keys()) + list(alternative_forms_by_language.keys()))
    )

    return forms_by_language, synonyms_by_language, alternative_forms_by_language, all_synonym_languages


# Re-export for backwards compatibility and convenience
# Routes can import from here for UI-related helpers
__all__ = ["get_difficulty_stats", "group_derivative_forms"]
