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
# These anchors are spread across the expanded general curriculum.
TIER_1_LEVEL = 10  # Home country + immediate neighbors/cultural significance
TIER_2_LEVEL = 18  # Major world powers + culturally relevant countries
TIER_3_LEVEL = 145  # Remaining countries (lowest priority); old L30 after the band renumbering

# Exact stored region lemmas that are countries.  ``region`` also contains US
# states and continents. States do not receive country-priority overrides;
# continents always travel with the second country tier.
COUNTRY_NAMES: Set[str] = {
    "Argentina",
    "Australia",
    "Austria",
    "Belgium",
    "Brazil",
    "Canada",
    "Chile",
    "China",
    "Cuba",
    "Denmark",
    "Egypt",
    "England",
    "Estonia",
    "Ethiopia",
    "Finland",
    "France",
    "Germany",
    "Greece",
    "Hungary",
    "India",
    "Indonesia",
    "Iran",
    "Iraq",
    "Ireland",
    "Israel",
    "Italy",
    "Japan",
    "Latvia",
    "Lithuania",
    "Mexico",
    "Morocco",
    "Netherlands",
    "Norway",
    "Peru",
    "Philippines",
    "Poland",
    "Portugal",
    "Russia",
    "Scotland",
    "South Africa",
    "South Korea",
    "Spain",
    "Sweden",
    "Switzerland",
    "Thailand",
    "Turkey",
    "Ukraine",
    "United States",
    "Vietnam",
    "Wales",
}

CONTINENT_NAMES: Set[str] = {
    "Africa",
    "Antarctica",
    "Asia",
    "Europe",
    "North America",
    "South America",
}


# =============================================================================
# COUNTRY PRIORITY CONFIGURATION BY TARGET LANGUAGE
# =============================================================================
# Each language defines which countries belong to which tier.
# Countries not listed use TIER_3_LEVEL.
#
# Key: target language code (the language being learned)
# Value: dict mapping tier level -> list of country concept_labels
#
# NOTE: concept_labels must match exactly those in the country data file
# (data/release/lemmas/nouns/region/base.jsonl)

COUNTRY_PRIORITIES: Dict[str, Dict[int, List[str]]] = {
    # -------------------------------------------------------------------------
    # LITHUANIAN (lt) - Baltic focus, European neighbors
    # NOTE: English-speaking countries (England, America, Canada, Australia)
    # are always in Tier 1 since we target English speakers.
    # Countries not listed here use Tier 3.
    # -------------------------------------------------------------------------
    "lt": {
        TIER_1_LEVEL: [
            "Lithuania",  # Home country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
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
        # India, Brazil use Tier 3 (145)
        # Not relevant enough to prioritize for Lithuanian learners
    },
    # -------------------------------------------------------------------------
    # CHINESE (zh) - East Asian focus, major trading partners
    # -------------------------------------------------------------------------
    "zh": {
        TIER_1_LEVEL: [
            "China",  # Home country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "Japan",  # Major neighbor, economic ties
            "South Korea",  # Major neighbor, economic ties
            "Thailand",  # Southeast Asian neighbor, tourism
            "Vietnam",  # Southeast Asian neighbor
            "Russia",  # Major neighbor
            "India",  # Neighbor, BRICS
        ],
        TIER_2_LEVEL: [
            "Germany",  # Major trade partner
            "France",  # Major European power
            "Brazil",  # BRICS partner
            "South Africa",  # BRICS partner
            "Egypt",  # Belt and Road
            "Italy",
            "Spain",
        ],
        # Baltic countries, Nordic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # FRENCH (fr) - European focus, Francophone world
    # -------------------------------------------------------------------------
    "fr": {
        TIER_1_LEVEL: [
            "France",  # Home country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
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
        # Nordic and Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # SPANISH (es) - European (Peninsular) context
    # -------------------------------------------------------------------------
    # Paired with es-419 below: the two differ only in which countries lead.
    # European Spanish puts Spain and its European neighbors first; es-419
    # leads with the Latin American republics.  Keep any other change in sync
    # across both entries.
    "es": {
        TIER_1_LEVEL: [
            "Spain",  # Home country (or cultural origin)
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
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
        # Nordic and Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # LATIN AMERICAN SPANISH (es-419) - Latin American context
    # -------------------------------------------------------------------------
    # Same language as "es" above; only the country ordering differs.  The
    # Spanish-speaking republics and their regional neighbors lead, and Spain
    # moves to Tier 2 as the cultural origin rather than the home country.
    "es-419": {
        TIER_1_LEVEL: [
            "Mexico",  # Largest Spanish-speaking country
            "Argentina",  # Major regional power
            "Chile",  # Major regional power
            "United States",  # English-speaking (always Tier 1) + largest diaspora
            "England",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "Brazil",  # Regional neighbor
        ],
        TIER_2_LEVEL: [
            "Spain",  # Cultural origin, not the home country here
            "Peru",  # Regional
            "Cuba",  # Regional
            "China",  # Major trade partner
            "Japan",  # Economic ties
        ],
        # European countries other than Spain use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # BRAZILIAN PORTUGUESE (pt-br) - Latin American context
    # -------------------------------------------------------------------------
    # es-419 with the two languages switched: Brazil leads where Mexico does
    # there, and Portugal is the Tier 2 cultural origin in Spain's place. Keep
    # any other change in sync with es-419.
    "pt-br": {
        TIER_1_LEVEL: [
            "Brazil",  # Home country
            "Argentina",  # Major regional power
            "Chile",  # Major regional power
            "United States",  # English-speaking (always Tier 1)
            "England",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "Mexico",  # Largest Spanish-speaking neighbor
        ],
        TIER_2_LEVEL: [
            "Portugal",  # Cultural origin, not the home country here
            "Peru",  # Regional
            "Cuba",  # Regional
            "China",  # Major trade partner
            "Japan",  # Economic ties, largest diaspora outside Japan
        ],
        # European countries other than Portugal use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # GERMAN (de) - Central European focus
    # -------------------------------------------------------------------------
    "de": {
        TIER_1_LEVEL: [
            "Germany",  # Home country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
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
        # Baltic countries, Finland use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # ITALIAN (it) - Mediterranean and European focus
    # -------------------------------------------------------------------------
    "it": {
        TIER_1_LEVEL: [
            "Italy",  # Home country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
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
        # Nordic and Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # PORTUGUESE (pt) - Lusophone world, Brazilian focus
    # -------------------------------------------------------------------------
    "pt": {
        TIER_1_LEVEL: [
            "Brazil",  # Largest Portuguese-speaking country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
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
        # Nordic and Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # DUTCH (nl) - European and colonial history focus
    # -------------------------------------------------------------------------
    "nl": {
        TIER_1_LEVEL: [
            "England",  # English-speaking (always Tier 1) + neighbor
            "United States",  # English-speaking (always Tier 1)
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
        # Nordic and Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # SWEDISH (sv) - Nordic and European focus
    # -------------------------------------------------------------------------
    "sv": {
        TIER_1_LEVEL: [
            "Sweden",  # Home country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
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
        # Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # VIETNAMESE (vi) - Southeast Asian and French colonial ties
    # -------------------------------------------------------------------------
    "vi": {
        TIER_1_LEVEL: [
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1) + regional
            "China",  # Major neighbor, cultural influence
            "Thailand",  # Southeast Asian neighbor
            "South Korea",  # Regional economic ties
            "Japan",  # Regional power
            "France",  # Colonial history
        ],
        TIER_2_LEVEL: [
            "Russia",  # Historic ties
            "Germany",
            "India",
            "Egypt",  # Historic ties
            "Spain",
            "Italy",
            "Brazil",
            "Poland",
        ],
        # Nordic and Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # JAPANESE (ja) - East Asian focus
    # -------------------------------------------------------------------------
    "ja": {
        TIER_1_LEVEL: [
            "Japan",  # Home country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1) + major ally
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "South Korea",  # Major neighbor
            "China",  # Major neighbor
            "Thailand",  # Popular destination
            "Vietnam",  # Economic ties
            "Russia",  # Neighbor
            "Germany",  # Historic ties
        ],
        TIER_2_LEVEL: [
            "France",
            "India",
            "Brazil",  # Japanese diaspora
            "Egypt",  # Tourism, history
            "Italy",
            "Spain",
            "Poland",
        ],
        # Nordic and Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # KOREAN (ko) - East Asian focus
    # -------------------------------------------------------------------------
    "ko": {
        TIER_1_LEVEL: [
            "South Korea",  # Home country
            "England",  # English-speaking (always Tier 1)
            "United States",  # English-speaking (always Tier 1) + major ally
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1) + trade
            "China",  # Major neighbor
            "Japan",  # Major neighbor
            "Vietnam",  # Economic ties, K-pop popularity
            "Thailand",  # Tourism, K-pop popularity
            "Russia",  # Neighbor
            "Germany",  # Economic ties
        ],
        TIER_2_LEVEL: [
            "France",
            "India",
            "Brazil",
            "Egypt",
            "Italy",
            "Spain",
            "Poland",
        ],
        # Nordic and Baltic countries use Tier 3 (145)
    },
    # -------------------------------------------------------------------------
    # SWAHILI (sw) - East African focus
    # NOTE: Would benefit from Tanzania, Kenya when added to data
    # -------------------------------------------------------------------------
    "sw": {
        TIER_1_LEVEL: [
            "England",  # English-speaking (always Tier 1) + colonial history
            "United States",  # English-speaking (always Tier 1)
            "Canada",  # English-speaking (always Tier 1)
            "Australia",  # English-speaking (always Tier 1)
            "South Africa",  # African neighbor, trade
            "Egypt",  # Major African country, historic ties
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
        # Nordic and Baltic countries use Tier 3 (145)
    },
}

# Taiwan Mandarin takes Mandarin's country emphasis unchanged. Aliased rather
# than copied so the two cannot drift apart.
COUNTRY_PRIORITIES["zh-tw"] = COUNTRY_PRIORITIES["zh"]


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
    "United States": "American",
    "Canada": "Canadian",
    "Japan": "Japanese",
    "China": "Chinese",
    "India": "Indian",
    "Brazil": "Brazilian",
    "Australia": "Australian",
    "Sweden": "Swedish",
    "Norway": "Norwegian",
    "Finland": "Finnish",
    "South Korea": "South Korean",
    "Thailand": "Thai",
    "Vietnam": "Vietnamese",
    "South Africa": "South African",
    "Egypt": "Egyptian",
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

    if country_label in CONTINENT_NAMES:
        return TIER_2_LEVEL

    for level, countries in priorities.items():
        if country_label in countries:
            return level

    # Every other recognized country is the language's lowest-priority tier.
    return TIER_3_LEVEL


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
    known_countries = COUNTRY_NAMES

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
