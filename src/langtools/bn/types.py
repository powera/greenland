"""Bengali-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Bengali noun declension results.

    Bengali nouns decline across 4 cases and 2 numbers.
    Bengali has no grammatical gender in the European sense.

    Cases:
    - Nominative (কর্তা/নির্দেশক): unmarked — subject
    - Objective (কর্ম): suffix -কে (-ke) — direct/indirect object
    - Genitive (সম্বন্ধ): suffix -র/-এর (-r/-er) — possession
    - Locative (অধিকরণ): suffix -তে/-এ/-য় (-te/-e/-y) — location

    Plurals are formed with suffixes like -গুলো (-gulo) for inanimates
    or -রা (-ra) for animate nouns.  Bengali uses the Bengali (Eastern
    Nagari) script.
    """

    word: str
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for nouns (4 cases × 2 numbers = 8 forms)
    SINGULAR_FORMS = [
        "nominative_singular",
        "objective_singular",
        "genitive_singular",
        "locative_singular",
    ]
    PLURAL_FORMS = [
        "nominative_plural",
        "objective_plural",
        "genitive_plural",
        "locative_plural",
    ]
    ALL_FORMS = SINGULAR_FORMS + PLURAL_FORMS

    def has_singular(self) -> bool:
        """Check if this noun has singular forms."""
        return any(self.forms.get(form) for form in self.SINGULAR_FORMS if self.forms.get(form))

    def has_plural(self) -> bool:
        """Check if this noun has plural forms."""
        return any(self.forms.get(form) for form in self.PLURAL_FORMS if self.forms.get(form))


@dataclass
class VerbConjugation:
    """Bengali verb conjugation results.

    Bengali verbs conjugate for person and register across 3 main tenses.
    The citation form is the infinitive ending in -া (-a).

    Persons (register-based):
    - 1st person (আমি ami)
    - 2nd person intimate (তুই tui)
    - 2nd person familiar (তুমি tumi)
    - 3rd person ordinary (সে se)
    - 3rd person honorific (আপনি/তিনি apni/tini)

    Tenses:
    - Present simple (সাধারণ বর্তমান)
    - Past simple (সাধারণ অতীত)
    - Future (সাধারণ ভবিষ্যৎ)
    """

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys: 5 persons × 3 tenses = 15 forms
    PRESENT_FORMS = [
        "1_present",
        "2int_present",
        "2fam_present",
        "3_present",
        "3hon_present",
    ]
    PAST_FORMS = [
        "1_past",
        "2int_past",
        "2fam_past",
        "3_past",
        "3hon_past",
    ]
    FUTURE_FORMS = [
        "1_future",
        "2int_future",
        "2fam_future",
        "3_future",
        "3hon_future",
    ]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS


@dataclass
class AdjectiveForms:
    """Bengali adjective form results.

    Bengali adjectives are mostly uninflected (they do not decline for
    case, number, or gender).  However, they have comparative degrees:

    - Positive (মূল): ভালো (bhalo, good)
    - Comparative (তুলনামূলক): ভালোতর (bhalotoro) / আরও ভালো (aro bhalo)
    - Superlative (সর্বোচ্চ): ভালোতম (bhalotomo) / সবচেয়ে ভালো (sobcheye bhalo)

    Both synthetic (-তর/-তম suffixes) and analytic (আরও/সবচেয়ে) forms
    are common.  Provide the most natural form for each degree.
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for adjectives (comparative degrees)
    ALL_FORMS = ["positive", "comparative", "superlative"]
