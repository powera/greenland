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

    # French verb forms (6 persons x multiple tenses)
    # Present indicative (Présent de l'indicatif)
    PRESENT_FORMS = [
        "1s_present",  # je
        "2s_present",  # tu
        "3s_present",  # il/elle
        "1p_present",  # nous
        "2p_present",  # vous
        "3p_present",  # ils/elles
    ]
    # Imperfect (Imparfait)
    IMPERFECT_FORMS = [
        "1s_imperfect",
        "2s_imperfect",
        "3s_imperfect",
        "1p_imperfect",
        "2p_imperfect",
        "3p_imperfect",
    ]
    # Simple past (Passé simple)
    SIMPLE_PAST_FORMS = [
        "1s_simple_past",
        "2s_simple_past",
        "3s_simple_past",
        "1p_simple_past",
        "2p_simple_past",
        "3p_simple_past",
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
    # Conditional (Conditionnel présent)
    CONDITIONAL_FORMS = [
        "1s_conditional",
        "2s_conditional",
        "3s_conditional",
        "1p_conditional",
        "2p_conditional",
        "3p_conditional",
    ]
    # Present subjunctive (Subjonctif présent)
    SUBJUNCTIVE_FORMS = [
        "1s_subjunctive",
        "2s_subjunctive",
        "3s_subjunctive",
        "1p_subjunctive",
        "2p_subjunctive",
        "3p_subjunctive",
    ]
    # Other forms
    OTHER_FORMS = [
        "infinitive",
        "present_participle",  # participe présent
        "past_participle",  # participe passé
        "past_participle_f",  # feminine form
        "past_participle_mp",  # masculine plural
        "past_participle_fp",  # feminine plural
        "imperative_2s",  # tu form
        "imperative_1p",  # nous form
        "imperative_2p",  # vous form
    ]
    ALL_FORMS = (
        PRESENT_FORMS
        + IMPERFECT_FORMS
        + SIMPLE_PAST_FORMS
        + FUTURE_FORMS
        + CONDITIONAL_FORMS
        + SUBJUNCTIVE_FORMS
        + OTHER_FORMS
    )


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
    AGREEMENT_FORMS = [
        "masculine_singular",
        "feminine_singular",
        "masculine_plural",
        "feminine_plural",
    ]
    # Comparative forms
    COMPARISON_FORMS = [
        "positive",
        "comparative",
        "superlative",
    ]
    ALL_FORMS = AGREEMENT_FORMS + COMPARISON_FORMS


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
