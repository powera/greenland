"""Japanese-specific type definitions for linguistic forms.

Japanese nouns do not inflect, but verbs have genuine conjugation.
The four key conjugation forms stored here are the ones most essential
for learners:

* **ます形 (masu-form):** polite present/future (食べます)
* **て形 (te-form):** conjunctive / request form (食べて)
* **た形 (ta-form):** plain past (食べた)
* **ない形 (nai-form):** plain negative (食べない)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from clients.wiktionary.types import NounNumberType


@dataclass
class NounDeclension:
    """Japanese noun form results.

    Japanese nouns have no grammatical number, gender, or case inflection.
    Particles (は, が, を, etc.) attach as separate words.
    The single stored form is the dictionary headword.
    """

    word: str
    number_type: NounNumberType = NounNumberType.REGULAR
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    BASE_FORMS = ["base"]
    ALL_FORMS = BASE_FORMS

    def has_base(self) -> bool:
        """Check if this noun has a base form."""
        return any(self.forms.get(form) for form in self.BASE_FORMS)


@dataclass
class VerbConjugation:
    """Japanese verb conjugation results.

    Japanese verbs conjugate into many forms.  We store the four most
    useful for learners:

    * masu – polite non-past (e.g. 食べます)
    * te   – conjunctive (e.g. 食べて)
    * ta   – plain past (e.g. 食べた)
    * nai  – plain negative (e.g. 食べない)

    Verb groups:
    * Group 1 (五段動詞 godan): consonant-stem verbs (書く, 飲む, 話す, …)
    * Group 2 (一段動詞 ichidan): vowel-stem verbs (食べる, 見る, …)
    * Group 3 (irregular): する and 来る (くる)
    """

    word: str  # dictionary form (辞書形)
    forms: Dict[str, str] = field(default_factory=dict)
    alternatives: Dict[str, List[str]] = field(default_factory=dict)
    raw_template: Optional[str] = None
    confidence: float = 1.0
    notes: Optional[str] = None

    MASU_FORMS = ["masu"]
    TE_FORMS = ["te"]
    TA_FORMS = ["ta"]
    NAI_FORMS = ["nai"]
    ALL_FORMS = MASU_FORMS + TE_FORMS + TA_FORMS + NAI_FORMS
