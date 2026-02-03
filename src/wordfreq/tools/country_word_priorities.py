#!/usr/bin/env python3
"""
Configuration for country-related word difficulty levels by target language.

This module defines which countries (and related words like nationalities,
language names) should appear earlier or later depending on the target language
being learned.

Example:
- For Lithuanian learners: Poland, Germany, Russia are early (neighbors)
- For Chinese learners: Japan, Korea, USA are early (regional/trade partners)

Words are grouped into tiers that appear at specific levels, rather than
being spread across many levels. This creates batches of ~10-15 country
words appearing together every 5 or so levels.
"""

from typing import Dict, List, Optional, Set

# =============================================================================
# LEVEL GROUPINGS
# =============================================================================
# Countries are grouped at specific levels to batch them together.
# Each tier maps to a specific difficulty level.
# These levels are chosen to align with existing difficulty levels in the data:
# - Early words: 6-9
# - Mid-level words: 13-14
# - Advanced words: 18-20

TIER_1_LEVEL = 8  # Home country + immediate neighbors/cultural significance + English
TIER_2_LEVEL = 13  # Major world powers + culturally relevant countries
TIER_3_LEVEL = 18  # Remaining countries (lowest priority)


# =============================================================================
# COUNTRY PRIORITY CONFIGURATION BY TARGET LANGUAGE
# =============================================================================
# Each language defines which countries belong to which tier.
# Countries not listed use the default level from the lemma.
#
# Key: target language code (the language being learned)
# Value: dict mapping tier level -> list of country concept_labels
#
# NOTE: concept_labels must match exactly those in the country data file
# (data/release/lemmas/nouns/country/base.jsonl)

COUNTRY_PRIORITIES: Dict[str, Dict[int, List[str]]] = {
    # -------------------------------------------------------------------------
    # LITHUANIAN (lt) - Baltic focus, European neighbors
    # NOTE: English-speaking countries (England, America, Canada, Australia)
    # are always in Tier 1 since we target English speakers.
    # Countries not listed here use the default level from the lemma (14).
    # -------------------------------------------------------------------------
    "lt": {
        TIER_1_LEVEL: [
            "Lithuania",  # Home country
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "Latvia",  # Baltic neighbor
            "Estonia",  # Baltic neighbor
            "Poland",  # Major neighbor, historical ties
            "Russia",  # Major neighbor
            "Germany",  # Major economic partner
        ],
        TIER_2_LEVEL: [
            "France",  # Major European power
            "Spain",  # Emigration destination
            "Italy",  # European cultural significance
            "Sweden",  # Nordic neighbor
            "Norway",  # Nordic neighbor
            "Finland",  # Nordic neighbor
            "Japan",
            "China",
        ],
        # Tier 3: India, Brazil use default level (14)
        # Not relevant enough to prioritize for Lithuanian learners
    },
    # -------------------------------------------------------------------------
    # CHINESE (zh) - East Asian focus, major trading partners
    # NOTE: Baltic countries (Lithuania, Latvia, Estonia) are not included -
    # they use the default level. Could add Thailand, Vietnam, Korea when
    # those countries are added to the data.
    # -------------------------------------------------------------------------
    "zh": {
        TIER_1_LEVEL: [
            "China",  # Home country
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "Japan",  # Major neighbor, economic ties
            "Russia",  # Major neighbor
            "India",  # Neighbor, BRICS
        ],
        TIER_2_LEVEL: [
            "Germany",  # Major trade partner
            "France",  # Major European power
            "Brazil",  # BRICS partner
            "Italy",
            "Spain",
        ],
        # Baltic countries, Nordic countries use default level (14)
        # Not relevant for Chinese learners - would add Thailand, Vietnam, Korea instead
    },
    # -------------------------------------------------------------------------
    # FRENCH (fr) - European focus, Francophone world
    # -------------------------------------------------------------------------
    "fr": {
        TIER_1_LEVEL: [
            "France",  # Home country
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1) + Francophone
            "Australia",  # English-speaking (always Tier 1)
            "Germany",  # Major neighbor
            "Spain",  # Neighbor
            "Italy",  # Neighbor
        ],
        TIER_2_LEVEL: [
            "Poland",  # European ties
            "Russia",  # Major power
            "China",  # Major power
            "Japan",  # Cultural interest
            "Brazil",  # Ties
            "India",
        ],
        # Nordic and Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # SPANISH (es) - Latin American context, European ties
    # -------------------------------------------------------------------------
    "es": {
        TIER_1_LEVEL: [
            "Spain",  # Home country (or cultural origin)
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "France",  # Neighbor
            "Italy",  # Cultural ties
            "Germany",  # Major European power
        ],
        TIER_2_LEVEL: [
            "Brazil",  # Latin American neighbor
            "China",  # Major trade partner
            "Japan",  # Economic ties
            "Poland",
            "Russia",
            "India",
        ],
        # Nordic and Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # GERMAN (de) - Central European focus
    # -------------------------------------------------------------------------
    "de": {
        TIER_1_LEVEL: [
            "Germany",  # Home country
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "France",  # Major neighbor
            "Poland",  # Neighbor
            "Italy",  # Cultural ties, neighbor
        ],
        TIER_2_LEVEL: [
            "Spain",  # European ties
            "Russia",  # Major power
            "China",  # Trade partner
            "Japan",  # Economic ties
            "Sweden",  # Nordic
            "Norway",
            "India",
            "Brazil",
        ],
        # Baltic countries, Finland use default level (14)
    },
    # -------------------------------------------------------------------------
    # ITALIAN (it) - Mediterranean and European focus
    # -------------------------------------------------------------------------
    "it": {
        TIER_1_LEVEL: [
            "Italy",  # Home country
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "France",  # Neighbor
            "Germany",  # Major European power
            "Spain",  # Mediterranean neighbor
        ],
        TIER_2_LEVEL: [
            "Poland",
            "Russia",
            "China",
            "Japan",
            "Brazil",  # Italian diaspora
            "India",
        ],
        # Nordic and Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # PORTUGUESE (pt) - Lusophone world, Brazilian focus
    # -------------------------------------------------------------------------
    "pt": {
        TIER_1_LEVEL: [
            "Brazil",  # Largest Portuguese-speaking country
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "Spain",  # Neighbor (Portugal)
            "France",  # European ties
            "Germany",  # Major European power
        ],
        TIER_2_LEVEL: [
            "Italy",
            "Japan",  # Brazilian diaspora
            "China",  # Trade
            "Poland",
            "India",
            "Russia",
        ],
        # Nordic and Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # DUTCH (nl) - European and colonial history focus
    # -------------------------------------------------------------------------
    "nl": {
        TIER_1_LEVEL: [
            "England",  # English-speaking (always Tier 1) + neighbor
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "Germany",  # Major neighbor
            "France",  # Neighbor
            "Spain",  # Historic ties
            "Italy",  # European ties
        ],
        TIER_2_LEVEL: [
            "Poland",
            "Russia",
            "China",
            "Japan",
            "Brazil",
            "India",
        ],
        # Nordic and Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # SWEDISH (sv) - Nordic and European focus
    # -------------------------------------------------------------------------
    "sv": {
        TIER_1_LEVEL: [
            "Sweden",  # Home country
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "Norway",  # Nordic neighbor
            "Finland",  # Nordic neighbor
            "Germany",  # Major European power
        ],
        TIER_2_LEVEL: [
            "France",
            "Spain",
            "Italy",
            "Poland",
            "Russia",
            "China",
            "Japan",
            "India",
            "Brazil",
        ],
        # Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # VIETNAMESE (vi) - Southeast Asian and French colonial ties
    # NOTE: Would benefit from Thailand, Malaysia, Singapore when added to data
    # -------------------------------------------------------------------------
    "vi": {
        TIER_1_LEVEL: [
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1) + regional
            "China",  # Major neighbor, cultural influence
            "Japan",  # Regional power
            "France",  # Colonial history
            "Russia",  # Historic ties
        ],
        TIER_2_LEVEL: [
            "Germany",
            "India",
            "Spain",
            "Italy",
            "Brazil",
            "Poland",
        ],
        # Nordic and Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # JAPANESE (ja) - East Asian focus
    # NOTE: Would benefit from Korea, Taiwan when added to data
    # -------------------------------------------------------------------------
    "ja": {
        TIER_1_LEVEL: [
            "Japan",  # Home country
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1) + major ally
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "China",  # Major neighbor
            "Russia",  # Neighbor
            "Germany",  # Historic ties
        ],
        TIER_2_LEVEL: [
            "France",
            "India",
            "Brazil",  # Japanese diaspora
            "Italy",
            "Spain",
            "Poland",
        ],
        # Nordic and Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # KOREAN (ko) - East Asian focus
    # NOTE: Would benefit from having Korea (South Korea) itself in data
    # -------------------------------------------------------------------------
    "ko": {
        TIER_1_LEVEL: [
            "England",  # English-speaking (always Tier 1)
            "America",  # English-speaking (always Tier 1) + major ally
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1) + trade
            "China",  # Major neighbor
            "Japan",  # Major neighbor
            "Russia",  # Neighbor
            "Germany",  # Economic ties
        ],
        TIER_2_LEVEL: [
            "France",
            "India",
            "Brazil",
            "Italy",
            "Spain",
            "Poland",
        ],
        # Nordic and Baltic countries use default level (14)
    },
    # -------------------------------------------------------------------------
    # SWAHILI (sw) - East African focus
    # NOTE: Would benefit from South Africa, Egypt, Tanzania when added to data
    # -------------------------------------------------------------------------
    "sw": {
        TIER_1_LEVEL: [
            "England",  # English-speaking (always Tier 1) + colonial history
            "America",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "China",  # Major investor/partner
            "India",  # Historic trade ties
            "Germany",  # Colonial history (Tanzania)
            "France",
        ],
        TIER_2_LEVEL: [
            "Japan",
            "Russia",
            "Brazil",
            "Italy",
            "Spain",
            "Poland",
        ],
        # Nordic and Baltic countries use default level (14)
    },
}


# =============================================================================
# RELATED WORD CATEGORIES
# =============================================================================
# These define which word subtypes should follow the same priority rules
# as country names. Words linked to a country share its priority tier.

# Maps concept_label patterns to help find related words
# e.g., "Lithuania" -> "Lithuanian" (nationality), "Lithuanian" (language adj)
COUNTRY_TO_NATIONALITY_MAP: Dict[str, str] = {
    "Lithuania": "Lithuanian",
    "Latvia": "Latvian",
    "Estonia": "Estonian",
    "Poland": "Polish",
    "Germany": "German",
    "France": "French",
    "Spain": "Spanish",
    "Italy": "Italian",
    "Russia": "Russian",
    "England": "English",
    "America": "American",
    "Canada": "Canadian",
    "Japan": "Japanese",
    "China": "Chinese",
    "India": "Indian",  # Not in current data but for future
    "Brazil": "Brazilian",  # Not in current data but for future
    "Australia": "Australian",  # Not in current data but for future
    "Sweden": "Swedish",
    "Norway": "Norwegian",
    "Finland": "Finnish",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_country_level_for_language(country_label: str, target_language: str) -> Optional[int]:
    """
    Get the difficulty level for a country in a specific target language.

    Args:
        country_label: The concept_label of the country (e.g., "Lithuania")
        target_language: Language code of the target language (e.g., "zh")

    Returns:
        The difficulty level to use, or None if no override needed
        (use default level from lemma)
    """
    if target_language not in COUNTRY_PRIORITIES:
        return None

    priorities = COUNTRY_PRIORITIES[target_language]

    for level, countries in priorities.items():
        if country_label in countries:
            return level

    # Country not in any tier - use default (no override)
    return None


def get_all_countries_for_language(target_language: str) -> Dict[int, List[str]]:
    """
    Get all country assignments for a target language.

    Args:
        target_language: Language code

    Returns:
        Dictionary mapping level -> list of country labels
    """
    return COUNTRY_PRIORITIES.get(target_language, {})


def get_supported_languages() -> List[str]:
    """Get list of languages with country priority configuration."""
    return list(COUNTRY_PRIORITIES.keys())


def get_nationality_for_country(country_label: str) -> Optional[str]:
    """
    Get the corresponding nationality label for a country.

    Args:
        country_label: The country concept_label (e.g., "Lithuania")

    Returns:
        The nationality concept_label (e.g., "Lithuanian") or None
    """
    return COUNTRY_TO_NATIONALITY_MAP.get(country_label)


def get_all_tier_levels() -> List[int]:
    """Get all tier levels in order."""
    return [TIER_1_LEVEL, TIER_2_LEVEL, TIER_3_LEVEL]


def validate_configuration() -> List[str]:
    """
    Validate the configuration for common issues.

    Returns:
        List of warning/error messages (empty if valid)
    """
    issues: List[str] = []

    # Known countries from the data file
    known_countries = {
        "Lithuania",
        "Latvia",
        "Estonia",
        "Poland",
        "Germany",
        "France",
        "Spain",
        "Italy",
        "Russia",
        "England",
        "America",
        "Canada",
        "Japan",
        "China",
        "India",
        "Brazil",
        "Australia",
        "Sweden",
        "Norway",
        "Finland",
    }

    for lang_code, priorities in COUNTRY_PRIORITIES.items():
        mentioned_countries: Set[str] = set()

        for level, countries in priorities.items():
            for country in countries:
                if country in mentioned_countries:
                    issues.append(f"[{lang_code}] Duplicate: '{country}' appears in multiple tiers")
                mentioned_countries.add(country)

                if country not in known_countries:
                    issues.append(f"[{lang_code}] Unknown country: '{country}' (not in known list)")

    return issues


if __name__ == "__main__":
    # Quick validation when run directly
    print("Country Word Priorities Configuration")
    print("=" * 50)
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
    print("Tier Levels:")
    print(f"  Tier 1 (home/neighbors/English): Level {TIER_1_LEVEL}")
    print(f"  Tier 2 (major powers): Level {TIER_2_LEVEL}")
    print(f"  Tier 3 (remaining): Level {TIER_3_LEVEL}")
