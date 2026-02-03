#!/usr/bin/env python3
"""
Configuration for family relation word handling by target language.

This module defines which family relation terms each language uses and which
should be excluded (set to null/-1 difficulty) because they don't map cleanly
to the target language.

Example:
- Chinese has specific terms for older/younger brother but no generic "brother"
- English has "cousin" (gender-neutral) while Romance languages have "primo/prima"
- Some languages distinguish maternal/paternal grandparents, others don't

Words can be:
1. Included: The term maps naturally to the target language
2. Excluded (null): The term doesn't exist or is awkward in the target language
   - These get difficulty_level=-1 override
"""

from typing import Dict, List, Optional, Set

# =============================================================================
# FAMILY RELATION CATEGORIES
# =============================================================================
# Family relations are grouped by semantic category.
# Each category contains concept_labels that may or may not apply to each language.

# Nuclear family - immediate parents and children
NUCLEAR_FAMILY = [
    "family",
    "mother",
    "father",
    "brother",
    "sister",
    "son",
    "daughter",
]

# Age-distinguished siblings (used in Chinese, Korean, Vietnamese, etc.)
AGE_DISTINGUISHED_SIBLINGS = [
    "older brother",
    "younger brother",
    "older sister",
    "younger sister",
]

# Extended family - grandparents and grandchildren
GRANDPARENTS_GENERAL = [
    "grandfather",
    "grandmother",
]

# Maternal/paternal distinguished grandparents (Chinese, Korean, etc.)
GRANDPARENTS_DISTINGUISHED = [
    "maternal grandfather",
    "paternal grandfather",
    "maternal grandmother",
    "paternal grandmother",
]

GRANDCHILDREN = [
    "grandson",
    "granddaughter",
]

# Aunts/uncles - general and distinguished
AUNTS_UNCLES_GENERAL = [
    "uncle",
    "aunt",
]

AUNTS_UNCLES_DISTINGUISHED = [
    "maternal uncle",
    "paternal uncle",
    "maternal aunt",
    "paternal aunt",
]

# Nieces/nephews
NIECES_NEPHEWS = [
    "nephew",
    "niece",
]

# Cousins - general and gendered
COUSINS_GENERAL = [
    "cousin",
]

COUSINS_GENDERED = [
    "cousin (male)",
    "cousin (female)",
]

# Spouse and partner
SPOUSE_TERMS = [
    "spouse",
    "husband",
    "wife",
    "partner",
]

# Romantic relationships (non-married)
ROMANTIC_TERMS = [
    "boyfriend",
    "girlfriend",
    "fianc\u00e9",
    "fianc\u00e9e",
]

# In-laws
IN_LAWS = [
    "father-in-law",
    "mother-in-law",
    "son-in-law",
    "daughter-in-law",
    "brother-in-law",
    "sister-in-law",
]

# Step-family
STEP_FAMILY = [
    "stepfather",
    "stepmother",
    "stepson",
    "stepdaughter",
]

# All standard family relation concept_labels
ALL_FAMILY_RELATIONS: List[str] = (
    NUCLEAR_FAMILY
    + AGE_DISTINGUISHED_SIBLINGS
    + GRANDPARENTS_GENERAL
    + GRANDPARENTS_DISTINGUISHED
    + GRANDCHILDREN
    + AUNTS_UNCLES_GENERAL
    + AUNTS_UNCLES_DISTINGUISHED
    + NIECES_NEPHEWS
    + COUSINS_GENERAL
    + COUSINS_GENDERED
    + SPOUSE_TERMS
    + ROMANTIC_TERMS
    + IN_LAWS
    + STEP_FAMILY
)


# =============================================================================
# LANGUAGE EXCLUSION CONFIGURATION
# =============================================================================
# For each language, specify which family relation terms should be EXCLUDED
# (i.e., set to difficulty_level=-1 because they're awkward or don't exist).
#
# Key: target language code
# Value: set of concept_labels to exclude for that language
#
# Terms NOT in the exclusion set are considered valid for the language.

EXCLUDED_TERMS: Dict[str, Set[str]] = {
    # -------------------------------------------------------------------------
    # ENGLISH (en) - Uses most general terms, gender-neutral cousin
    # -------------------------------------------------------------------------
    "en": {
        # English doesn't typically use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # English doesn't distinguish maternal/paternal grandparents commonly
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        # English doesn't distinguish maternal/paternal aunts/uncles
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # English uses gender-neutral "cousin" not gendered forms
        "cousin (male)",
        "cousin (female)",
    },
    # -------------------------------------------------------------------------
    # CHINESE (zh) - Uses age-distinguished and maternal/paternal terms
    # -------------------------------------------------------------------------
    "zh": {
        # Chinese doesn't use generic "brother"/"sister" - only age-specific
        "brother",
        "sister",
        # Chinese doesn't use generic grandparent terms commonly
        "grandfather",
        "grandmother",
        # Chinese doesn't use generic aunt/uncle - uses specific terms
        "uncle",
        "aunt",
        # Chinese uses gendered cousin terms in formal contexts
        "cousin",
        # Generic "spouse" less common than specific terms
        "spouse",
        # "partner" is a modern/Western concept, less natural
        "partner",
    },
    # -------------------------------------------------------------------------
    # KOREAN (ko) - Uses age-distinguished siblings
    # -------------------------------------------------------------------------
    "ko": {
        # Korean uses age-distinguished sibling terms
        "brother",
        "sister",
        # Korean uses gendered cousin terms
        "cousin",
    },
    # -------------------------------------------------------------------------
    # VIETNAMESE (vi) - Uses age-distinguished siblings
    # -------------------------------------------------------------------------
    "vi": {
        # Vietnamese uses age-distinguished sibling terms
        "brother",
        "sister",
        # Vietnamese uses gendered cousin terms
        "cousin",
    },
    # -------------------------------------------------------------------------
    # JAPANESE (ja) - Uses some age-distinguished terms
    # -------------------------------------------------------------------------
    "ja": {
        # Japanese distinguishes older/younger siblings naturally
        # but also has general terms, so only exclude age-distinguished
        # Actually Japanese has both, so fewer exclusions
        "cousin (male)",
        "cousin (female)",
    },
    # -------------------------------------------------------------------------
    # SPANISH (es) - Romance language with gendered cousins
    # -------------------------------------------------------------------------
    "es": {
        # Spanish doesn't use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # Spanish doesn't distinguish maternal/paternal
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # Spanish uses gendered cousin terms (primo/prima)
        "cousin",
    },
    # -------------------------------------------------------------------------
    # FRENCH (fr) - Romance language with gendered cousins
    # -------------------------------------------------------------------------
    "fr": {
        # French doesn't use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # French doesn't distinguish maternal/paternal
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # French uses gendered cousin terms
        "cousin",
    },
    # -------------------------------------------------------------------------
    # GERMAN (de) - Germanic language with gendered cousins
    # -------------------------------------------------------------------------
    "de": {
        # German doesn't use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # German doesn't distinguish maternal/paternal
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # German uses gendered cousin terms (Cousin/Cousine)
        "cousin",
    },
    # -------------------------------------------------------------------------
    # ITALIAN (it) - Romance language with gendered cousins
    # -------------------------------------------------------------------------
    "it": {
        # Italian doesn't use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # Italian doesn't distinguish maternal/paternal
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # Italian uses gendered cousin terms (cugino/cugina)
        "cousin",
    },
    # -------------------------------------------------------------------------
    # PORTUGUESE (pt) - Romance language with gendered cousins
    # -------------------------------------------------------------------------
    "pt": {
        # Portuguese doesn't use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # Portuguese doesn't distinguish maternal/paternal
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # Portuguese uses gendered cousin terms
        "cousin",
    },
    # -------------------------------------------------------------------------
    # DUTCH (nl) - Germanic language
    # -------------------------------------------------------------------------
    "nl": {
        # Dutch doesn't use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # Dutch doesn't distinguish maternal/paternal
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # Dutch uses gendered cousin terms (neef/nicht for cousin)
        "cousin",
    },
    # -------------------------------------------------------------------------
    # SWEDISH (sv) - Nordic language
    # -------------------------------------------------------------------------
    "sv": {
        # Swedish doesn't use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # Swedish doesn't distinguish maternal/paternal (commonly)
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # Swedish uses gendered cousin terms
        "cousin",
    },
    # -------------------------------------------------------------------------
    # LITHUANIAN (lt) - Baltic language
    # -------------------------------------------------------------------------
    "lt": {
        # Lithuanian doesn't use age-distinguished siblings
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # Lithuanian doesn't distinguish maternal/paternal
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # Lithuanian uses gendered cousin terms (pusbrolis/pussesere)
        "cousin",
    },
    # -------------------------------------------------------------------------
    # SWAHILI (sw) - Bantu language
    # -------------------------------------------------------------------------
    "sw": {
        # Swahili doesn't use age-distinguished siblings in the same way
        "older brother",
        "younger brother",
        "older sister",
        "younger sister",
        # Swahili doesn't distinguish maternal/paternal as strongly
        "maternal grandfather",
        "paternal grandfather",
        "maternal grandmother",
        "paternal grandmother",
        "maternal uncle",
        "paternal uncle",
        "maternal aunt",
        "paternal aunt",
        # Swahili uses gender-neutral cousin
        "cousin (male)",
        "cousin (female)",
    },
}

# Default exclusions for languages not explicitly configured
DEFAULT_EXCLUDED_TERMS: Set[str] = {
    # By default, exclude specialized terms that require linguistic analysis
    "older brother",
    "younger brother",
    "older sister",
    "younger sister",
    "maternal grandfather",
    "paternal grandfather",
    "maternal grandmother",
    "paternal grandmother",
    "maternal uncle",
    "paternal uncle",
    "maternal aunt",
    "paternal aunt",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_excluded_terms_for_language(lang_code: str) -> Set[str]:
    """
    Get the set of family relation terms to exclude for a language.

    Args:
        lang_code: Language code (e.g., "zh", "en")

    Returns:
        Set of concept_labels that should be excluded (set to -1 difficulty)
    """
    return EXCLUDED_TERMS.get(lang_code, DEFAULT_EXCLUDED_TERMS)


def get_included_terms_for_language(lang_code: str) -> Set[str]:
    """
    Get the set of family relation terms to include for a language.

    Args:
        lang_code: Language code (e.g., "zh", "en")

    Returns:
        Set of concept_labels that should be included (have normal difficulty)
    """
    excluded = get_excluded_terms_for_language(lang_code)
    return set(ALL_FAMILY_RELATIONS) - excluded


def is_term_excluded_for_language(concept_label: str, lang_code: str) -> bool:
    """
    Check if a specific term should be excluded for a language.

    Args:
        concept_label: The family relation concept_label (e.g., "brother")
        lang_code: Language code (e.g., "zh")

    Returns:
        True if the term should be excluded (difficulty=-1), False otherwise
    """
    return concept_label in get_excluded_terms_for_language(lang_code)


def get_supported_languages() -> List[str]:
    """Get list of languages with explicit family relation configuration."""
    return list(EXCLUDED_TERMS.keys())


def validate_configuration() -> List[str]:
    """
    Validate the configuration for common issues.

    Returns:
        List of warning/error messages (empty if valid)
    """
    issues: List[str] = []

    all_terms_set = set(ALL_FAMILY_RELATIONS)

    for lang_code, excluded in EXCLUDED_TERMS.items():
        for term in excluded:
            if term not in all_terms_set:
                issues.append(
                    f"[{lang_code}] Unknown term in exclusions: '{term}' "
                    f"(not in ALL_FAMILY_RELATIONS)"
                )

    return issues


if __name__ == "__main__":
    # Quick validation when run directly
    print("Family Relation Priorities Configuration")
    print("=" * 50)
    print(f"Total family relation terms: {len(ALL_FAMILY_RELATIONS)}")
    print(f"Supported languages: {len(get_supported_languages())}")
    print(f"Languages: {', '.join(get_supported_languages())}")
    print()

    issues = validate_configuration()
    if issues:
        print("Configuration Issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("Configuration is valid!")

    print()
    print("Exclusions by language:")
    for lang in sorted(get_supported_languages()):
        excluded = get_excluded_terms_for_language(lang)
        included = get_included_terms_for_language(lang)
        print(f"  {lang}: {len(included)} included, {len(excluded)} excluded")
