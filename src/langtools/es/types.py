"""Spanish-specific type definitions for Wiktionary parsing."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


class SpanishGender(Enum):
    """Spanish grammatical gender."""

    MASCULINE = "m"  # el
    FEMININE = "f"  # la


@dataclass
class NounDeclension:
    """Spanish noun declension results.

    Spanish nouns only have singular and plural forms (no case system).
    """

    word: str
    gender: Optional[SpanishGender] = None
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for Spanish nouns (just singular and plural)
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
    """Spanish verb conjugation results.

    Spanish verbs have extensive conjugation with multiple tenses and moods.
    """

    word: str  # The infinitive form
    forms: Dict[str, str] = field(default_factory=dict)  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Spanish verb forms (6 persons x multiple tenses)
    # Form names align with GrammaticalForm enum
    # Present indicative (Presente de indicativo)
    PRESENT_FORMS = [
        "1s_present",  # yo
        "2s_present",  # tú
        "3s_present",  # él/ella/usted
        "1p_present",  # nosotros
        "2p_present",  # vosotros
        "3p_present",  # ellos/ellas/ustedes
    ]
    # Preterite (Pretérito indefinido)
    PRETERITE_FORMS = [
        "1s_preterite",
        "2s_preterite",
        "3s_preterite",
        "1p_preterite",
        "2p_preterite",
        "3p_preterite",
    ]
    # Imperfect (Pretérito imperfecto)
    IMPERFECT_FORMS = [
        "1s_imperfect",
        "2s_imperfect",
        "3s_imperfect",
        "1p_imperfect",
        "2p_imperfect",
        "3p_imperfect",
    ]
    # Future (Futuro simple)
    FUTURE_FORMS = [
        "1s_future",
        "2s_future",
        "3s_future",
        "1p_future",
        "2p_future",
        "3p_future",
    ]
    # Conditional (Condicional simple)
    CONDITIONAL_FORMS = [
        "1s_conditional",
        "2s_conditional",
        "3s_conditional",
        "1p_conditional",
        "2p_conditional",
        "3p_conditional",
    ]
    # Present subjunctive (Presente de subjuntivo)
    SUBJUNCTIVE_PRESENT_FORMS = [
        "1s_subjunctive_present",
        "2s_subjunctive_present",
        "3s_subjunctive_present",
        "1p_subjunctive_present",
        "2p_subjunctive_present",
        "3p_subjunctive_present",
    ]
    # Imperative (Imperativo)
    IMPERATIVE_FORMS = [
        "2s_imperative",  # tú
        "3s_imperative",  # usted
        "1p_imperative",  # nosotros
        "2p_imperative",  # vosotros
        "3p_imperative",  # ustedes
    ]
    # Non-finite forms
    PARTICIPLE_FORMS = [
        "infinitive",
        "gerund",  # gerundio
        "past_participle",  # participio pasado
    ]
    ALL_FORMS = (
        PRESENT_FORMS
        + PRETERITE_FORMS
        + IMPERFECT_FORMS
        + FUTURE_FORMS
        + CONDITIONAL_FORMS
        + SUBJUNCTIVE_PRESENT_FORMS
        + IMPERATIVE_FORMS
        + PARTICIPLE_FORMS
    )


@dataclass
class AdjectiveDeclension:
    """Spanish adjective declension results.

    Spanish adjectives agree in gender and number (4 forms).
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Form names align with GrammaticalForm enum
    # Gender/number agreement forms
    AGREEMENT_FORMS = [
        "singular_m",  # masculino singular
        "singular_f",  # femenino singular
        "plural_m",  # masculino plural
        "plural_f",  # femenino plural
    ]
    # Comparison forms
    COMPARISON_FORMS = [
        "positive",
        "comparative",
        "superlative",
    ]
    ALL_FORMS = AGREEMENT_FORMS + COMPARISON_FORMS


@dataclass
class AdverbForms:
    """Spanish adverb form results."""

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Spanish adverbs typically have comparative forms
    ALL_FORMS = ["positive", "comparative", "superlative"]
