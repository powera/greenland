"""Infer grammatical number and gender from generated forms."""

from typing import Dict, List, Optional, Tuple

from words.forms.config import FormGenerationConfig


def detect_number_type_from_forms(forms_dict: Dict[str, str], config: FormGenerationConfig) -> str:
    """
    Detect if a noun is plurale tantum, singulare tantum, or regular.

    Args:
        forms_dict: Dictionary of form names to form texts
        config: Configuration with form mappings

    Returns:
        One of: 'plurale_tantum', 'singulare_tantum', or 'regular'
    """
    # Only detect for nouns and adjectives, not verbs
    if config.pos_type not in ["noun", "adjective"]:
        return "regular"

    # Identify which forms are singular vs plural based on form names
    singular_forms = [name for name in forms_dict.keys() if "singular" in name.lower()]
    plural_forms = [name for name in forms_dict.keys() if "plural" in name.lower()]

    # Check if we have non-empty forms
    def has_non_empty_form(form_name: str) -> bool:
        form_text = forms_dict.get(form_name)
        return bool(form_text and isinstance(form_text, str) and form_text.strip())

    has_singular = any(has_non_empty_form(f) for f in singular_forms)
    has_plural = any(has_non_empty_form(f) for f in plural_forms)

    if has_plural and not has_singular:
        return "plurale_tantum"
    elif has_singular and not has_plural:
        return "singulare_tantum"
    else:
        return "regular"


def extract_gender_from_forms(
    forms_dict: Dict[str, str], config: FormGenerationConfig
) -> Optional[str]:
    """
    Extract grammatical gender from form data.

    Two strategies are used:
    1. Form key inspection: For forms with gendered keys (e.g., singular_m,
       singular_f), infer gender by checking which gender forms are populated.
    2. Article detection: For noun forms whose keys are ungendered (e.g.,
       singular/plural), infer gender from the article in the singular form
       text (e.g., "il gatto" → masculine, "het huis" → neuter).

    Args:
        forms_dict: Dictionary of form names to form texts
        config: Configuration with form mappings

    Returns:
        One of: 'masculine', 'feminine', 'neuter', or None if cannot be determined
    """
    # Only extract for nouns and adjectives
    if config.pos_type not in ["noun", "adjective"]:
        return None

    # Strategy 1: Check for gender markers in form key names
    masculine_forms = [name for name in forms_dict.keys() if "_m" in name.lower()]
    feminine_forms = [name for name in forms_dict.keys() if "_f" in name.lower()]
    neuter_forms = [name for name in forms_dict.keys() if "_n" in name.lower()]

    # Count non-empty forms for each gender
    def has_non_empty_form(form_name: str) -> bool:
        form_text = forms_dict.get(form_name)
        return bool(form_text and isinstance(form_text, str) and form_text.strip())

    has_masculine = any(has_non_empty_form(f) for f in masculine_forms)
    has_feminine = any(has_non_empty_form(f) for f in feminine_forms)
    has_neuter = any(has_non_empty_form(f) for f in neuter_forms)

    # If only one gender has forms, that's the word's gender
    gender_count = sum([has_masculine, has_feminine, has_neuter])

    if gender_count == 1:
        if has_masculine:
            return "masculine"
        elif has_feminine:
            return "feminine"
        elif has_neuter:
            return "neuter"

    # Strategy 2: Detect gender from articles in the singular form text.
    # This works for noun forms where keys are just "singular"/"plural"
    # (or case-based like "nominative_singular") and the LLM includes the
    # article in the form text.
    if config.pos_type == "noun":
        gender = _detect_gender_from_article(forms_dict, config.language_code)
        if gender:
            return gender
        if config.language_code == "lt":
            gender = _detect_lithuanian_gender_from_nominative(forms_dict)
            if gender:
                return gender

    # If no gender could be determined, return None
    return None


def _detect_lithuanian_gender_from_nominative(forms_dict: Dict[str, str]) -> Optional[str]:
    """Infer Lithuanian noun gender from nominative singular ending."""
    nominative = forms_dict.get("nominative_singular")
    if not nominative or not isinstance(nominative, str):
        return None
    normalized_nominative = nominative.strip().lower()
    if not normalized_nominative:
        return None

    masculine_suffixes = ("as", "is", "ys", "us", "ius")
    feminine_suffixes = ("a", "ė")

    if normalized_nominative.endswith(masculine_suffixes):
        return "masculine"
    if normalized_nominative.endswith(feminine_suffixes):
        return "feminine"
    return None


_ARTICLE_GENDER_MAP: Dict[str, List[Tuple[str, Optional[str]]]] = {
    "it": [
        ("lo ", "masculine"),
        ("il ", "masculine"),
        ("l'", "masculine"),  # ambiguous, but masculine more common; see below
        ("la ", "feminine"),
        ("gli ", "masculine"),  # plural masculine, useful as fallback
        ("le ", "feminine"),  # plural feminine
        ("i ", "masculine"),  # plural masculine
    ],
    "nl": [
        ("het ", "neuter"),
        ("de ", "common"),
    ],
    # No fr/es entries: their translations are stored without articles, and
    # their noun gender comes from lape (words.grammar_fact_tasks).
    "pt": [
        ("o ", "masculine"),
        ("a ", "feminine"),
        ("os ", "masculine"),  # plural masculine
        ("as ", "feminine"),  # plural feminine
    ],
    "de": [
        ("der ", "masculine"),
        ("die ", "feminine"),  # also plural, but singular first
        ("das ", "neuter"),
    ],
}


def _detect_gender_from_article(forms_dict: Dict[str, str], language_code: str) -> Optional[str]:
    """Infer gender from the article prefixing a singular noun form.

    The LLM prompts ask for forms with articles (e.g. "il gatto", "het huis").
    We look at the singular form text (trying several key names) and match the
    leading article against a per-language table.

    Returns 'masculine', 'feminine', 'neuter', 'common', or None.
    """
    if language_code not in _ARTICLE_GENDER_MAP:
        return None

    # Try to find a singular form to inspect
    singular_keys = [
        "singular",
        "nominative_singular",
    ]
    singular_text: Optional[str] = None
    for key in singular_keys:
        candidate = forms_dict.get(key)
        if candidate and isinstance(candidate, str) and candidate.strip():
            singular_text = candidate.strip().lower()
            break

    if not singular_text:
        return None

    for article, gender in _ARTICLE_GENDER_MAP[language_code]:
        if singular_text.startswith(article):
            return gender

    # Italian l' is ambiguous; try the plural to disambiguate
    if language_code == "it" and singular_text.startswith("l'"):
        plural_text = forms_dict.get("plural")
        if plural_text and isinstance(plural_text, str):
            plural_lower = plural_text.strip().lower()
            if plural_lower.startswith("gli ") or plural_lower.startswith("i "):
                return "masculine"
            elif plural_lower.startswith("le "):
                return "feminine"

    return None
