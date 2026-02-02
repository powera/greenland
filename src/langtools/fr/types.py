"""French-specific type definitions for Wiktionary parsing."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class FrenchGender(Enum):
    """French grammatical gender."""

    MASCULINE = "m"
    FEMININE = "f"


@dataclass
class NounDeclension:
    """French noun form results."""

    word: str
    gender: Optional[FrenchGender] = None
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # French nouns have singular and plural forms
    SINGULAR_FORMS = ["singular"]
    PLURAL_FORMS = ["plural"]
    ALL_FORMS = SINGULAR_FORMS + PLURAL_FORMS

    def has_singular(self) -> bool:
        """Check if this noun has singular forms."""
        return any(self.forms.get(form) for form in self.SINGULAR_FORMS)

    def has_plural(self) -> bool:
        """Check if this noun has plural forms."""
        return any(self.forms.get(form) for form in self.PLURAL_FORMS)


@dataclass
class VerbConjugation:
    """French verb conjugation results."""

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    auxiliary: Optional[str] = None  # avoir or être
    confidence: float = 1.0
    notes: Optional[str] = None

    # French verb forms (6 persons x 3 tenses + participles)
    # These form names align with GrammaticalForm enum in enums.py
    # Present indicative (Présent de l'indicatif)
    PRESENT_FORMS = [
        "1s_present",  # je
        "2s_present",  # tu
        "3s_present",  # il/elle
        "1p_present",  # nous
        "2p_present",  # vous
        "3p_present",  # ils/elles
    ]
    # Imperfect (Imparfait) - uses "impf" to match GrammaticalForm enum
    IMPF_FORMS = [
        "1s_impf",
        "2s_impf",
        "3s_impf",
        "1p_impf",
        "2p_impf",
        "3p_impf",
    ]
    # Future (Futur simple)
    FUTURE_FORMS = [
        "1s_future",
        "2s_future",
        "3s_future",
        "1p_future",
        "2p_future",
        "3p_future",
    ]
    # Past participle forms (for passé composé)
    PARTICIPLE_FORMS = [
        "pc_m",  # masculine past participle (e.g., "allé")
        "pc_f",  # feminine past participle (e.g., "allée")
    ]
    ALL_FORMS = PRESENT_FORMS + IMPF_FORMS + FUTURE_FORMS + PARTICIPLE_FORMS


@dataclass
class AdjectiveDeclension:
    """French adjective form results.

    French adjectives agree in gender and number with the noun they modify.
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # French adjectives have 4 agreement forms
    # Form names align with GrammaticalForm enum (ADJ_FR_SINGULAR_M, etc.)
    AGREEMENT_FORMS = [
        "singular_m",
        "singular_f",
        "plural_m",
        "plural_f",
    ]
    ALL_FORMS = AGREEMENT_FORMS


@dataclass
class AdverbForms:
    """French adverb form results."""

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # French adverbs have comparative forms
    ALL_FORMS = ["positive", "comparative", "superlative"]
