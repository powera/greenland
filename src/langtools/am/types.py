"""Amharic-specific type definitions for linguistic forms."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Amharic noun form results.

    Amharic nouns have grammatical gender (masculine/feminine) and form
    plurals with the suffix -ዎች (-woch) or -ኦች (-och).  Some nouns have
    irregular plural forms.  Amharic uses the Ge'ez (Ethiopic) script,
    an abugida where each character represents a consonant-vowel pair.
    """

    word: str
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

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
    """Amharic verb conjugation results.

    Amharic verbs follow a Semitic triconsonantal root system and conjugate
    for person, number, gender, tense, and mood.  The main tenses are
    perfect (past), imperfect (present/future), and gerundive.  Verb forms
    are built by applying vowel patterns and affixes to the root consonants.
    """

    word: str  # The citation form (3rd person masculine singular perfect)
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    PRESENT_FORMS = ["present"]
    PAST_FORMS = ["past"]
    FUTURE_FORMS = ["future"]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS
