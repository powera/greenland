"""Estonian-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Estonian noun declension results.

    Estonian nouns decline across 14 cases and 2 numbers.
    Estonian has no grammatical gender.
    """

    word: str
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for nouns (14 cases)
    SINGULAR_FORMS = [
        "nominative_singular",
        "genitive_singular",
        "partitive_singular",
        "illative_singular",
        "inessive_singular",
        "elative_singular",
        "allative_singular",
        "adessive_singular",
        "ablative_singular",
        "translative_singular",
        "terminative_singular",
        "essive_singular",
        "abessive_singular",
        "comitative_singular",
    ]
    PLURAL_FORMS = [
        "nominative_plural",
        "genitive_plural",
        "partitive_plural",
        "illative_plural",
        "inessive_plural",
        "elative_plural",
        "allative_plural",
        "adessive_plural",
        "ablative_plural",
        "translative_plural",
        "terminative_plural",
        "essive_plural",
        "abessive_plural",
        "comitative_plural",
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
    """Estonian verb conjugation results.

    Estonian verbs conjugate by person and number across multiple tenses.
    """

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Present (Olevik)
    PRESENT_FORMS = [
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
    ]
    # Past (Lihtminevik)
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    # Future (Tulevik - saama + infinitive)
    FUTURE_FORMS = [
        "1s_future",
        "2s_future",
        "3s_future",
        "1p_future",
        "2p_future",
        "3p_future",
    ]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS


@dataclass
class AdjectiveDeclension:
    """Estonian adjective declension results.

    Estonian adjectives agree with nouns in case and number.
    They decline across 14 cases and 2 numbers (28 forms).
    Estonian has no grammatical gender, so there is no gender distinction.
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for adjectives (14 cases × 2 numbers = 28 forms)
    SINGULAR_FORMS = [
        "nominative_singular",
        "genitive_singular",
        "partitive_singular",
        "illative_singular",
        "inessive_singular",
        "elative_singular",
        "allative_singular",
        "adessive_singular",
        "ablative_singular",
        "translative_singular",
        "terminative_singular",
        "essive_singular",
        "abessive_singular",
        "comitative_singular",
    ]
    PLURAL_FORMS = [
        "nominative_plural",
        "genitive_plural",
        "partitive_plural",
        "illative_plural",
        "inessive_plural",
        "elative_plural",
        "allative_plural",
        "adessive_plural",
        "ablative_plural",
        "translative_plural",
        "terminative_plural",
        "essive_plural",
        "abessive_plural",
        "comitative_plural",
    ]
    ALL_FORMS = SINGULAR_FORMS + PLURAL_FORMS


@dataclass
class AdverbForms:
    """Estonian adverb form results."""

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for adverbs (comparative degrees)
    ALL_FORMS = ["positive", "comparative", "superlative"]
