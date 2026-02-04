"""English-specific type definitions for Wiktionary parsing."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """English noun form results.

    English nouns only have singular and plural forms (no case system, no gender).
    """

    word: str
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Expected form keys for English nouns
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
    """English verb conjugation results.

    English verbs have relatively simple conjugation compared to Romance languages.
    """

    word: str  # The infinitive/base form
    forms: Dict[str, str] = field(default_factory=dict)  # Maps form name to form value
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # English verb forms
    # Form names align with GrammaticalForm enum patterns
    BASE_FORMS = [
        "infinitive",  # Base form (walk)
        "3s_present",  # 3rd person singular present (walks)
        "past",  # Simple past (walked)
        "past_participle",  # Past participle (walked/been)
        "present_participle",  # Present participle/gerund (walking)
    ]
    ALL_FORMS = BASE_FORMS


@dataclass
class AdjectiveDeclension:
    """English adjective form results.

    English adjectives have comparison forms but no gender/number agreement.
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Comparison forms
    COMPARISON_FORMS = [
        "positive",
        "comparative",
        "superlative",
    ]
    ALL_FORMS = COMPARISON_FORMS


@dataclass
class AdverbForms:
    """English adverb form results."""

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # English adverbs have comparative forms
    ALL_FORMS = ["positive", "comparative", "superlative"]
