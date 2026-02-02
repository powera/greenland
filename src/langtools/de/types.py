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

    # German verb forms (6 persons x multiple tenses)
    # Present tense (Präsens)
    PRESENT_FORMS = [
        "1s_present",  # ich
        "2s_present",  # du
        "3s_present",  # er/sie/es
        "1p_present",  # wir
        "2p_present",  # ihr
        "3p_present",  # sie/Sie
    ]
    # Simple past (Präteritum)
    PAST_FORMS = [
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
    ]
    # Subjunctive II (Konjunktiv II)
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
        "past_participle",
        "present_participle",
        "imperative_singular",
        "imperative_plural",
        "auxiliary",  # haben or sein
    ]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + SUBJUNCTIVE_FORMS + OTHER_FORMS


@dataclass
class AdjectiveDeclension:
    """German adjective declension results.

    German adjectives have three declension patterns:
    - Strong (no article): ein großer Mann
    - Weak (definite article): der große Mann
    - Mixed (indefinite article): ein großer Mann (nominative) vs einen großen Mann (accusative)
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Strong declension forms (4 cases x 4 genders incl. plural = 16 forms)
    # Weak declension forms (same structure)
    # Mixed declension forms (same structure)
    # For simplicity, we store the most common (strong) forms
    STRONG_SINGULAR_M = [
        "nominative_singular_m_strong",
        "genitive_singular_m_strong",
        "dative_singular_m_strong",
        "accusative_singular_m_strong",
    ]
    STRONG_SINGULAR_F = [
        "nominative_singular_f_strong",
        "genitive_singular_f_strong",
        "dative_singular_f_strong",
        "accusative_singular_f_strong",
    ]
    STRONG_SINGULAR_N = [
        "nominative_singular_n_strong",
        "genitive_singular_n_strong",
        "dative_singular_n_strong",
        "accusative_singular_n_strong",
    ]
    STRONG_PLURAL = [
        "nominative_plural_strong",
        "genitive_plural_strong",
        "dative_plural_strong",
        "accusative_plural_strong",
    ]

    # Predicative and comparative forms
    COMPARISON_FORMS = [
        "positive",
        "comparative",
        "superlative",
    ]

    ALL_FORMS = (
        STRONG_SINGULAR_M + STRONG_SINGULAR_F + STRONG_SINGULAR_N + STRONG_PLURAL + COMPARISON_FORMS
    )


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
