"""Mechanical Lithuanian noun declension for common regular classes."""

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Set

from clients.wiktionary.types import NounNumberType

_CASES: tuple[str, ...] = (
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "instrumental",
    "locative",
    "vocative",
)

_IRREGULAR_NOUNS: Set[str] = {
    "žmogus",
    "dievas",
    "sesuo",
    "duktė",
    "moteris",
}


@dataclass(frozen=True)
class DeclensionPattern:
    """Suffix table for a regular declension class."""

    class_name: str
    gender: str
    nominative_suffix: str
    singular_suffixes: Mapping[str, str]
    plural_suffixes: Mapping[str, str]


_PATTERNS: tuple[DeclensionPattern, ...] = (
    DeclensionPattern(
        class_name="masc_ius",
        gender="masculine",
        nominative_suffix="ius",
        singular_suffixes={
            "nominative": "ius",
            "genitive": "iaus",
            "dative": "iui",
            "accusative": "ių",
            "instrumental": "iumi",
            "locative": "iuje",
            "vocative": "iau",
        },
        plural_suffixes={
            "nominative": "iai",
            "genitive": "ių",
            "dative": "iams",
            "accusative": "ius",
            "instrumental": "iais",
            "locative": "iuose",
            "vocative": "iai",
        },
    ),
    DeclensionPattern(
        class_name="masc_us",
        gender="masculine",
        nominative_suffix="us",
        singular_suffixes={
            "nominative": "us",
            "genitive": "aus",
            "dative": "ui",
            "accusative": "ų",
            "instrumental": "umi",
            "locative": "uje",
            "vocative": "au",
        },
        plural_suffixes={
            "nominative": "ūs",
            "genitive": "ų",
            "dative": "ums",
            "accusative": "us",
            "instrumental": "umis",
            "locative": "uose",
            "vocative": "ūs",
        },
    ),
    DeclensionPattern(
        class_name="masc_ias",
        gender="masculine",
        nominative_suffix="ias",
        singular_suffixes={
            "nominative": "ias",
            "genitive": "io",
            "dative": "iui",
            "accusative": "ią",
            "instrumental": "iu",
            "locative": "yje",
            "vocative": "y",
        },
        plural_suffixes={
            "nominative": "iai",
            "genitive": "ių",
            "dative": "iams",
            "accusative": "ius",
            "instrumental": "iais",
            "locative": "iuose",
            "vocative": "iai",
        },
    ),
    DeclensionPattern(
        class_name="masc_ys",
        gender="masculine",
        nominative_suffix="ys",
        singular_suffixes={
            "nominative": "ys",
            "genitive": "io",
            "dative": "iui",
            "accusative": "į",
            "instrumental": "iu",
            "locative": "yje",
            "vocative": "y",
        },
        plural_suffixes={
            "nominative": "iai",
            "genitive": "ių",
            "dative": "iams",
            "accusative": "ius",
            "instrumental": "iais",
            "locative": "iuose",
            "vocative": "iai",
        },
    ),
    DeclensionPattern(
        class_name="masc_as",
        gender="masculine",
        nominative_suffix="as",
        singular_suffixes={
            "nominative": "as",
            "genitive": "o",
            "dative": "ui",
            "accusative": "ą",
            "instrumental": "u",
            "locative": "e",
            "vocative": "e",
        },
        plural_suffixes={
            "nominative": "ai",
            "genitive": "ų",
            "dative": "ams",
            "accusative": "us",
            "instrumental": "ais",
            "locative": "uose",
            "vocative": "ai",
        },
    ),
    DeclensionPattern(
        class_name="masc_is",
        gender="masculine",
        nominative_suffix="is",
        singular_suffixes={
            "nominative": "is",
            "genitive": "io",
            "dative": "iui",
            "accusative": "į",
            "instrumental": "iu",
            "locative": "yje",
            "vocative": "i",
        },
        plural_suffixes={
            "nominative": "iai",
            "genitive": "ių",
            "dative": "iams",
            "accusative": "ius",
            "instrumental": "iais",
            "locative": "iuose",
            "vocative": "iai",
        },
    ),
    DeclensionPattern(
        class_name="fem_is",
        gender="feminine",
        nominative_suffix="is",
        singular_suffixes={
            "nominative": "is",
            "genitive": "ies",
            "dative": "iai",
            "accusative": "į",
            "instrumental": "imi",
            "locative": "yje",
            "vocative": "ie",
        },
        plural_suffixes={
            "nominative": "ys",
            "genitive": "ių",
            "dative": "ims",
            "accusative": "is",
            "instrumental": "imis",
            "locative": "yse",
            "vocative": "ys",
        },
    ),
    DeclensionPattern(
        class_name="fem_a",
        gender="feminine",
        nominative_suffix="a",
        singular_suffixes={
            "nominative": "a",
            "genitive": "os",
            "dative": "ai",
            "accusative": "ą",
            "instrumental": "a",
            "locative": "oje",
            "vocative": "a",
        },
        plural_suffixes={
            "nominative": "os",
            "genitive": "ų",
            "dative": "oms",
            "accusative": "as",
            "instrumental": "omis",
            "locative": "ose",
            "vocative": "os",
        },
    ),
    DeclensionPattern(
        class_name="fem_ė",
        gender="feminine",
        nominative_suffix="ė",
        singular_suffixes={
            "nominative": "ė",
            "genitive": "ės",
            "dative": "ei",
            "accusative": "ę",
            "instrumental": "e",
            "locative": "ėje",
            "vocative": "e",
        },
        plural_suffixes={
            "nominative": "ės",
            "genitive": "ių",
            "dative": "ėms",
            "accusative": "es",
            "instrumental": "ėmis",
            "locative": "ėse",
            "vocative": "ės",
        },
    ),
)


def _find_pattern(
    noun: str, grammatical_gender: Optional[str] = None
) -> Optional[DeclensionPattern]:
    normalized_noun = noun.strip().lower()
    matching_patterns: List[DeclensionPattern] = []
    for pattern in _PATTERNS:
        if normalized_noun.endswith(pattern.nominative_suffix):
            matching_patterns.append(pattern)

    if not matching_patterns:
        return None

    if grammatical_gender:
        gender_matches = [
            pattern for pattern in matching_patterns if pattern.gender == grammatical_gender
        ]
        if len(gender_matches) == 1:
            return gender_matches[0]
        return None

    if len(matching_patterns) == 1:
        return matching_patterns[0]

    # Ambiguous suffix (e.g., -is can be masculine or feminine) without gender fact.
    return None


def decline_noun(noun: str, grammatical_gender: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Decline a Lithuanian noun using a conservative regular-pattern set.

    Returns ``None`` when no safe mechanical pattern can be applied.
    """
    normalized_noun = noun.strip().lower()
    if not normalized_noun or normalized_noun in _IRREGULAR_NOUNS:
        return None

    pattern = _find_pattern(normalized_noun, grammatical_gender=grammatical_gender)
    if pattern is None:
        return None

    stem = normalized_noun[: -len(pattern.nominative_suffix)]
    forms: Dict[str, str] = {}
    for case_name in _CASES:
        singular_suffix = pattern.singular_suffixes[case_name]
        plural_suffix = pattern.plural_suffixes[case_name]
        forms[f"{case_name}_singular"] = stem + singular_suffix
        forms[f"{case_name}_plural"] = stem + plural_suffix

    forms["number_type"] = NounNumberType.REGULAR.value
    forms["declension_class"] = pattern.class_name
    forms["gender"] = pattern.gender
    return forms


def get_declension_requirements() -> Dict[str, str]:
    """Return metadata needed for high-accuracy mechanical declension."""
    return {
        "lemma": "Nominative singular lemma.",
        "declension_class": "Class label (e.g., -as, -is, -a, -ė, consonant-stem, mixed).",
        "gender": "Masculine/feminine, needed for overlapping endings.",
        "number_type": "Regular vs plurale tantum vs singulare tantum.",
        "irregular_flag": "Whether lemma is irregular or has stem alternations.",
        "stem_override": "Optional stored stem if not derivable from nominative.",
        "stress_pattern": "Needed for accent-correct output if accents are tracked.",
    }


def get_supported_declension_classes() -> List[str]:
    """Return the currently supported mechanical declension classes."""
    return [pattern.class_name for pattern in _PATTERNS]
