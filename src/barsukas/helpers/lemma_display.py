"""Lemma display and UI helper functions for Barsukas."""

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from storage.queries.lemma import get_difficulty_stats

LemmaPronunciationRow = Dict[str, Optional[str]]


def group_derivative_forms(derivative_forms: Any) -> Tuple[Dict, Dict, Dict, List[str]]:
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
    forms_by_language: Dict = {}
    synonyms_by_language: Dict = {}
    alternative_forms_by_language: Dict = {}

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
        is_synonym = form.grammatical_form in [
            "synonym",
            "synonym_near",
            "synonym_regional",
            "synonym_register",
            "synonym_related",
            "synonym_spelling",
            "synonym_synecdoche",
        ]

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

    return (
        forms_by_language,
        synonyms_by_language,
        alternative_forms_by_language,
        all_synonym_languages,
    )


def group_populated_pronunciations(derivative_forms: Any) -> Dict[str, List[Any]]:
    """Group forms that already have IPA or phonetic data by language."""
    pronunciations_by_language: Dict[str, List[Any]] = {}

    for form in derivative_forms:
        has_ipa = bool((form.ipa_pronunciation or "").strip())
        has_phonetic = bool((form.phonetic_pronunciation or "").strip())
        if not (has_ipa or has_phonetic):
            continue

        language_code = form.language_code
        if language_code not in pronunciations_by_language:
            pronunciations_by_language[language_code] = []
        pronunciations_by_language[language_code].append(form)

    return pronunciations_by_language


def get_pronunciation_languages(
    derivative_forms: Sequence[Any],
    translations: Mapping[str, Optional[str]],
) -> List[str]:
    """Return languages eligible for pronunciation generation on the lemma page.

    This includes languages that already have derivative forms as well as
    languages where only a lemma/base translation exists. That allows Barsukas
    to offer pronunciation generation for lemma-only entries.
    """
    eligible_languages: Set[str] = {
        form.language_code for form in derivative_forms if getattr(form, "language_code", None)
    }

    for language_code, translation_text in translations.items():
        if (translation_text or "").strip():
            eligible_languages.add(language_code)

    return sorted(eligible_languages)


def build_lemma_pronunciation_rows(
    derivative_forms: Sequence[Any],
    translations: Mapping[str, Optional[str]],
    translation_pronunciations: Mapping[str, Tuple[Optional[str], Optional[str]]],
) -> Dict[str, LemmaPronunciationRow]:
    """Build per-language lemma/base pronunciation rows for the lemma page.

    Translation-level pronunciations take priority when present, but the helper
    falls back to an existing base-form derivative so English lemma/base IPA is
    still visible even though English does not use ``LemmaTranslation`` rows for
    pronunciation storage.
    """
    base_forms_by_language: Dict[str, Any] = {}
    for form in derivative_forms:
        if form.is_base_form and form.language_code not in base_forms_by_language:
            base_forms_by_language[form.language_code] = form

    all_languages = sorted(set(translations.keys()) | set(base_forms_by_language.keys()))
    pronunciation_rows: Dict[str, LemmaPronunciationRow] = {}

    for language_code in all_languages:
        translation_ipa, translation_phonetic = translation_pronunciations.get(
            language_code, (None, None)
        )
        base_form = base_forms_by_language.get(language_code)
        base_ipa = getattr(base_form, "ipa_pronunciation", None) if base_form else None
        base_phonetic = getattr(base_form, "phonetic_pronunciation", None) if base_form else None

        ipa_value = translation_ipa or base_ipa
        phonetic_value = translation_phonetic or base_phonetic
        if not (ipa_value or phonetic_value):
            continue

        display_text = translations.get(language_code) or getattr(
            base_form, "derivative_form_text", None
        )
        pronunciation_rows[language_code] = {
            "text": display_text,
            "ipa": ipa_value,
            "phonetic": phonetic_value,
            "grammatical_form": getattr(base_form, "grammatical_form", "lemma_translation"),
            "source": (
                "lemma_translation" if translation_ipa or translation_phonetic else "base_form"
            ),
        }

    return pronunciation_rows


def build_language_coverage_rows(
    language_names: Mapping[str, str],
    translations: Mapping[str, Optional[str]],
    forms_by_language: Mapping[str, Sequence[Any]],
    pronunciation_forms_by_language: Mapping[str, Sequence[Any]],
    lemma_pronunciation_rows: Mapping[str, LemmaPronunciationRow],
    audio_files: Sequence[Any],
    default_languages: Sequence[str],
) -> List[Dict[str, Any]]:
    """Build the per-language coverage summary shown on the lemma overview page.

    Default (high-priority) languages are always listed so absences are visible;
    secondary languages appear only when they actually have forms, pronunciation,
    or audio data.
    """
    audio_total_by_language: Dict[str, int] = {}
    audio_approved_by_language: Dict[str, int] = {}
    for audio in audio_files:
        language_code = audio.language_code
        audio_total_by_language[language_code] = audio_total_by_language.get(language_code, 0) + 1
        if audio.status in ("approved", "approved_with_issues"):
            audio_approved_by_language[language_code] = (
                audio_approved_by_language.get(language_code, 0) + 1
            )

    ordered_languages: List[str] = [
        lang_code for lang_code in default_languages if lang_code in language_names
    ]
    extra_languages = sorted(
        (
            set(forms_by_language)
            | set(pronunciation_forms_by_language)
            | set(lemma_pronunciation_rows)
            | set(audio_total_by_language)
        )
        - set(ordered_languages)
    )
    ordered_languages.extend(
        lang_code for lang_code in extra_languages if lang_code in language_names
    )

    coverage_rows: List[Dict[str, Any]] = []
    for lang_code in ordered_languages:
        coverage_rows.append(
            {
                "lang_code": lang_code,
                "lang_name": language_names[lang_code],
                "has_translation": bool((translations.get(lang_code) or "").strip()),
                "forms_count": len(forms_by_language.get(lang_code, [])),
                "pronunciation_count": len(pronunciation_forms_by_language.get(lang_code, [])),
                "has_lemma_pronunciation": lang_code in lemma_pronunciation_rows,
                "audio_total": audio_total_by_language.get(lang_code, 0),
                "audio_approved": audio_approved_by_language.get(lang_code, 0),
            }
        )
    return coverage_rows


# Re-export for backwards compatibility and convenience
# Routes can import from here for UI-related helpers
__all__ = [
    "build_language_coverage_rows",
    "build_lemma_pronunciation_rows",
    "get_difficulty_stats",
    "get_pronunciation_languages",
    "group_derivative_forms",
    "group_populated_pronunciations",
]
