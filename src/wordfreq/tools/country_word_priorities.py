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

TIER_1_LEVEL = 3  # Home country + immediate neighbors/cultural significance
TIER_2_LEVEL = 8  # Major world powers + culturally relevant countries
TIER_3_LEVEL = 13  # Secondary importance countries
TIER_4_LEVEL = 18  # Remaining countries (lowest priority)


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
    # -------------------------------------------------------------------------
    "lt": {
        TIER_1_LEVEL: [
            "Lithuania",  # Home country
            "Latvia",  # Baltic neighbor
            "Estonia",  # Baltic neighbor
            "Poland",  # Major neighbor, historical ties
            "Russia",  # Major neighbor
            "Germany",  # Major economic partner
        ],
        TIER_2_LEVEL: [
            "England",  # Major emigration destination
            "France",  # Major European power
            "Spain",  # Emigration destination
            "Italy",  # European cultural significance
            "America",  # Global superpower
            "Sweden",  # Nordic neighbor
            "Norway",  # Nordic neighbor
            "Finland",  # Nordic neighbor
        ],
        TIER_3_LEVEL: [
            "Japan",
            "China",
            "India",
            "Brazil",
            "Australia",
            "Canada",
        ],
        # TIER_4: Any remaining countries not listed
    },
    # -------------------------------------------------------------------------
    # CHINESE (zh) - East Asian focus, major trading partners
    # -------------------------------------------------------------------------
    "zh": {
        TIER_1_LEVEL: [
            "China",  # Home country
            "Japan",  # Major neighbor, economic ties
            "America",  # Major trade partner, global power
            "Russia",  # Major neighbor
            "India",  # Neighbor
        ],
        TIER_2_LEVEL: [
            "Germany",  # Major trade partner
            "France",  # Major European power
            "England",  # Major English-speaking country
            "Australia",  # Regional, Chinese diaspora
            "Canada",  # Chinese diaspora
            "Brazil",  # BRICS partner
        ],
        TIER_3_LEVEL: [
            "Italy",
            "Spain",
            "Poland",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",  # Low relevance for Chinese learners
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # FRENCH (fr) - European focus, Francophone world
    # -------------------------------------------------------------------------
    "fr": {
        TIER_1_LEVEL: [
            "France",  # Home country
            "Germany",  # Major neighbor
            "England",  # Historic rival, neighbor
            "Spain",  # Neighbor
            "Italy",  # Neighbor
            "America",  # Global superpower
        ],
        TIER_2_LEVEL: [
            "Canada",  # Francophone
            "Poland",  # European ties
            "Russia",  # Major power
            "China",  # Major power
            "Japan",  # Cultural interest
            "Brazil",  # Largest Portuguese-speaking, ties
        ],
        TIER_3_LEVEL: [
            "India",
            "Australia",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # SPANISH (es) - Latin American context, European ties
    # -------------------------------------------------------------------------
    "es": {
        TIER_1_LEVEL: [
            "Spain",  # Home country (or cultural origin)
            "America",  # Major influence, neighbor for Latin America
            "France",  # Neighbor
            "Italy",  # Cultural ties
            "Germany",  # Major European power
            "England",  # Global influence
        ],
        TIER_2_LEVEL: [
            "Brazil",  # Latin American neighbor
            "Canada",  # North American
            "China",  # Major trade partner
            "Japan",  # Economic ties
            "Poland",
            "Russia",
        ],
        TIER_3_LEVEL: [
            "India",
            "Australia",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # GERMAN (de) - Central European focus
    # -------------------------------------------------------------------------
    "de": {
        TIER_1_LEVEL: [
            "Germany",  # Home country
            "France",  # Major neighbor
            "Poland",  # Neighbor
            "Italy",  # Cultural ties, neighbor
            "England",  # Major European power
            "America",  # Global superpower
        ],
        TIER_2_LEVEL: [
            "Spain",  # European ties
            "Russia",  # Major power
            "China",  # Trade partner
            "Japan",  # Economic ties
            "Sweden",  # Nordic
            "Norway",
        ],
        TIER_3_LEVEL: [
            "Finland",
            "India",
            "Australia",
            "Canada",
            "Brazil",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # ITALIAN (it) - Mediterranean and European focus
    # -------------------------------------------------------------------------
    "it": {
        TIER_1_LEVEL: [
            "Italy",  # Home country
            "France",  # Neighbor
            "Germany",  # Major European power
            "Spain",  # Mediterranean neighbor
            "England",  # Major power
            "America",  # Global superpower
        ],
        TIER_2_LEVEL: [
            "Poland",
            "Russia",
            "China",
            "Japan",
            "Brazil",  # Italian diaspora
            "Canada",
        ],
        TIER_3_LEVEL: [
            "India",
            "Australia",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # PORTUGUESE (pt) - Lusophone world, Brazilian focus
    # -------------------------------------------------------------------------
    "pt": {
        TIER_1_LEVEL: [
            "Brazil",  # Largest Portuguese-speaking country
            "America",  # Regional influence
            "Spain",  # Neighbor (Portugal)
            "France",  # European ties
            "England",  # Historic ally (Portugal)
            "Germany",  # Major European power
        ],
        TIER_2_LEVEL: [
            "Italy",
            "Japan",  # Brazilian diaspora
            "China",  # Trade
            "Canada",
            "Australia",
            "Poland",
        ],
        TIER_3_LEVEL: [
            "India",
            "Russia",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # DUTCH (nl) - European and colonial history focus
    # -------------------------------------------------------------------------
    "nl": {
        TIER_1_LEVEL: [
            "Germany",  # Major neighbor
            "France",  # Neighbor
            "England",  # Neighbor across the sea
            "Spain",  # Historic ties
            "America",  # Global power
            "Italy",  # European ties
        ],
        TIER_2_LEVEL: [
            "Poland",
            "Russia",
            "China",
            "Japan",
            "Australia",
            "Brazil",
        ],
        TIER_3_LEVEL: [
            "India",
            "Canada",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # SWEDISH (sv) - Nordic and European focus
    # -------------------------------------------------------------------------
    "sv": {
        TIER_1_LEVEL: [
            "Sweden",  # Home country
            "Norway",  # Nordic neighbor
            "Finland",  # Nordic neighbor
            "Germany",  # Major European power
            "England",  # Major power
            "America",  # Global superpower
        ],
        TIER_2_LEVEL: [
            "France",
            "Spain",
            "Italy",
            "Poland",
            "Russia",
            "China",
        ],
        TIER_3_LEVEL: [
            "Japan",
            "India",
            "Australia",
            "Canada",
            "Brazil",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # VIETNAMESE (vi) - Southeast Asian and French colonial ties
    # -------------------------------------------------------------------------
    "vi": {
        TIER_1_LEVEL: [
            "China",  # Major neighbor, cultural influence
            "America",  # Historic ties
            "Japan",  # Regional power
            "France",  # Colonial history
            "Russia",  # Historic ties
            "Australia",  # Regional
        ],
        TIER_2_LEVEL: [
            "Germany",
            "England",
            "India",
            "Canada",
            "Spain",
            "Italy",
        ],
        TIER_3_LEVEL: [
            "Brazil",
            "Poland",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # JAPANESE (ja) - East Asian focus
    # -------------------------------------------------------------------------
    "ja": {
        TIER_1_LEVEL: [
            "Japan",  # Home country
            "America",  # Major ally
            "China",  # Major neighbor
            "Russia",  # Neighbor
            "Germany",  # Historic ties
            "England",  # Major power
        ],
        TIER_2_LEVEL: [
            "France",
            "Australia",
            "India",
            "Brazil",  # Japanese diaspora
            "Canada",
            "Italy",
        ],
        TIER_3_LEVEL: [
            "Spain",
            "Poland",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # KOREAN (ko) - East Asian focus
    # -------------------------------------------------------------------------
    "ko": {
        TIER_1_LEVEL: [
            "China",  # Major neighbor
            "Japan",  # Major neighbor
            "America",  # Major ally
            "Russia",  # Neighbor
            "Germany",  # Economic ties
            "Australia",  # Trade, diaspora
        ],
        TIER_2_LEVEL: [
            "England",
            "France",
            "India",
            "Canada",
            "Brazil",
            "Italy",
        ],
        TIER_3_LEVEL: [
            "Spain",
            "Poland",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
    },
    # -------------------------------------------------------------------------
    # SWAHILI (sw) - East African focus
    # -------------------------------------------------------------------------
    "sw": {
        TIER_1_LEVEL: [
            "China",  # Major investor/partner
            "India",  # Historic trade ties
            "England",  # Colonial history
            "America",  # Global power
            "Germany",  # Colonial history (Tanzania)
            "France",
        ],
        TIER_2_LEVEL: [
            "Japan",
            "Russia",
            "Brazil",
            "Australia",
            "Canada",
            "Italy",
        ],
        TIER_3_LEVEL: [
            "Spain",
            "Poland",
            "Sweden",
            "Norway",
            "Finland",
        ],
        TIER_4_LEVEL: [
            "Lithuania",
            "Latvia",
            "Estonia",
        ],
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
    return [TIER_1_LEVEL, TIER_2_LEVEL, TIER_3_LEVEL, TIER_4_LEVEL]


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
    print(f"  Tier 1 (home/neighbors): Level {TIER_1_LEVEL}")
    print(f"  Tier 2 (major powers): Level {TIER_2_LEVEL}")
    print(f"  Tier 3 (secondary): Level {TIER_3_LEVEL}")
    print(f"  Tier 4 (lowest priority): Level {TIER_4_LEVEL}")
