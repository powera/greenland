"""German-specific type definitions for Wiktionary parsing."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class GermanGender(Enum):
    """German grammatical gender."""

    MASCULINE = "m"  # der
    FEMININE = "f"  # die
    NEUTER = "n"  # das


@dataclass
class NounDeclension:
    """German noun declension results."""

    word: str
    gender: Optional[GermanGender] = None
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for German nouns (4 cases x 2 numbers = 8 forms)
    SINGULAR_FORMS = [
        "nominative_singular",
        "genitive_singular",
        "dative_singular",
        "accusative_singular",
    ]
    PLURAL_FORMS = [
        "nominative_plural",
        "genitive_plural",
        "dative_plural",
        "accusative_plural",
    ]
    ALL_FORMS = SINGULAR_FORMS + PLURAL_FORMS

    def has_singular(self) -> bool:
        """Check if this noun has singular forms."""
        return any(self.forms.get(form) for form in self.SINGULAR_FORMS)

    def has_plural(self) -> bool:
        """Check if this noun has plural forms."""
        return any(self.forms.get(form) for form in self.PLURAL_FORMS)


@dataclass
class VerbConjugation:
    """German verb conjugation results."""

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # German verb forms (6 persons x 3 tenses)
    # Form names align with GrammaticalForm enum
    # Present tense (Präsens)
    PRESENT_FORMS = [
        "1s_present",  # ich
        "2s_present",  # du
        "3s_present",  # er/sie/es
        "1p_present",  # wir
        "2p_present",  # ihr
        "3p_present",  # sie/Sie
    ]
    # Past tense (Perfekt in enum mapping)
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    # Future (Futur I)
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
    """German adjective declension results.

    German adjectives have complex declension patterns, but for alignment with
    GrammaticalForm enum, we use simplified gender/number forms.
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Form names align with GrammaticalForm enum (ADJ_DE_SINGULAR_M, etc.)
    AGREEMENT_FORMS = [
        "singular_m",
        "singular_f",
        "plural_m",
        "plural_f",
    ]
    ALL_FORMS = AGREEMENT_FORMS


@dataclass
class AdverbForms:
    """German adverb form results."""

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # German adverbs typically have comparative forms
    ALL_FORMS = ["positive", "comparative", "superlative"]
