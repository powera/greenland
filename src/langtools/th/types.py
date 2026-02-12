"""Thai-specific type definitions for linguistic forms.

Thai is an analytic/isolating language with no inflectional morphology.
Words do not change form; grammatical relationships are expressed through
word order, particles, and auxiliary words.  The forms stored here are
pedagogical constructions useful for language learners.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Thai noun form results.

    Thai is an isolating language with no inflectional morphology on nouns.
    Nouns do not change form for singular/plural; plurality is typically
    expressed via classifiers or context.  We store the base form and
    classifier for pedagogical purposes.

    Thai classifiers (ลักษณนาม) are an essential part of noun grammar:
    - คน (khon) for people
    - ตัว (tua) for animals and clothing
    - อัน (an) for small objects
    - เล่ม (lem) for books and sharp objects
    - คัน (khan) for vehicles and umbrellas
    - ใบ (bai) for flat objects, leaves, containers
    - ชิ้น (chin) for pieces/slices
    """

    word: str
    classifier: Optional[str] = None
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
    """Thai verb form results.

    Thai verbs do not conjugate for person, number, or tense.  Tense and
    aspect are expressed with auxiliary particles:
    - Present/habitual: bare verb (กิน = eat/eats)
    - Past/completed: verb + แล้ว (กินแล้ว = ate/has eaten)
    - Future/prospective: จะ + verb (จะกิน = will eat)
    - Progressive: กำลัง + verb (กำลังกิน = is eating)

    We store the base form plus common tense constructions for pedagogical
    purposes.
    """

    word: str  # The dictionary form
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    # Thai uses aspect markers rather than conjugation
    PRESENT_FORMS = ["present"]
    PAST_FORMS = ["past"]
    FUTURE_FORMS = ["future"]
    ALL_FORMS = PRESENT_FORMS + PAST_FORMS + FUTURE_FORMS


@dataclass
class AdjectiveForms:
    """Thai adjective form results.

    Thai adjectives (คำคุณศัพท์) function as stative verbs and can appear
    predicatively without a copula (e.g. อาหารอร่อย = "food is delicious").

    Comparative and superlative degrees are formed analytically:
    - Positive: base form (สวย = beautiful)
    - Comparative: base + กว่า (สวยกว่า = more beautiful)
    - Superlative: base + ที่สุด (สวยที่สุด = most beautiful)
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    ALL_FORMS = ["positive", "comparative", "superlative"]


@dataclass
class AdverbForms:
    """Thai adverb form results.

    Thai adverbs (คำกริยาวิเศษณ์) modify verbs, adjectives, or other adverbs.
    Many Thai adverbs are derived from adjectives and can take the same
    comparative degree modifiers:
    - Positive: base form (เร็ว = quickly)
    - Comparative: base + กว่า (เร็วกว่า = more quickly)
    - Superlative: base + ที่สุด (เร็วที่สุด = most quickly)
    """

    word: str
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    ALL_FORMS = ["positive", "comparative", "superlative"]
