"""Data types for pattern sentences.

A pattern sentence is a short fixed frame ("I want a ___", "The ___ is red")
filled with one open-class word from the database.  The frame's verbs,
pronouns, articles and numerals are closed-class grammar and live in the
language's pattern module; the slot words come from the database with their
forms, and a word missing a form a pattern needs is reported as a Skip rather
than guessed at.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional, Sequence, Tuple, Union

Gender = Literal["masculine", "feminine"]


@dataclass(frozen=True)
class Subject:
    """A grammatical subject a personal pattern is conjugated for.

    ``person`` is the verb slot (1s ... 3p).  ``gender`` is set only where
    English names it (he/she); 1s, 2s and the plurals default to the
    masculine form and accept the feminine one as well.
    """

    key: str
    person: str
    gender: Optional[Gender]
    english: str
    detail: Optional[str] = None


SUBJECTS: Tuple[Subject, ...] = (
    Subject("1s", "1s", None, "I"),
    Subject("2s", "2s", None, "you", "you: one person"),
    Subject("3s_m", "3s", "masculine", "he"),
    Subject("3s_f", "3s", "feminine", "she"),
    Subject("1p", "1p", None, "we"),
    Subject("2p", "2p", None, "you", "you: several people"),
    Subject("3p", "3p", None, "they"),
)


@dataclass(frozen=True)
class SlotNoun:
    """A noun that can fill a pattern slot, with its forms in one language.

    ``forms`` is keyed by the part of the grammatical form after the language
    code: ``noun/lt_accusative_singular`` -> ``accusative_singular``.
    ``gender`` is set only for masculine/feminine; ``gender_fact`` keeps the
    stored value (e.g. French "common") so a report can say why it is unset.
    """

    guid: str
    english: str
    target: str
    group: str
    countability: Optional[str] = None
    english_countability: Optional[str] = None
    number_type: Optional[str] = None
    english_number_type: Optional[str] = None
    english_plural: Optional[str] = None
    gender: Optional[Gender] = None
    gender_fact: Optional[str] = None
    measure_word: Optional[str] = None
    level: Optional[int] = None
    forms: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SlotAdjective:
    """A color or feeling adjective, with its forms in one language."""

    guid: str
    english: str
    target: str
    kind: Literal["color", "feeling"]
    level: Optional[int] = None
    forms: Dict[str, str] = field(default_factory=dict)


SlotWord = Union[SlotNoun, SlotAdjective]


@dataclass(frozen=True)
class WordPools:
    nouns: List[SlotNoun]
    adjectives: List[SlotAdjective]

    def colors(self) -> List[SlotAdjective]:
        return [a for a in self.adjectives if a.kind == "color"]

    def feelings(self) -> List[SlotAdjective]:
        return [a for a in self.adjectives if a.kind == "feeling"]


@dataclass(frozen=True)
class RenderedSentence:
    pattern_id: str
    english: str
    target: str
    word_guids: Tuple[str, ...]
    subject: Optional[str] = None
    detail: Optional[str] = None
    also_accepted: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Skip:
    """A word that cannot fill a pattern, and the missing data that stops it."""

    pattern_id: str
    guid: str
    reason: str


Outcome = Union[RenderedSentence, Skip]

# A pattern's build function: the slot words, then the subject (None for an
# impersonal pattern such as "The cat is black").
BuildFunc = Callable[[Sequence[SlotWord], Optional[Subject]], List[Outcome]]
CandidatesFunc = Callable[[WordPools], List[Tuple[SlotWord, ...]]]


@dataclass(frozen=True)
class SentencePattern:
    pattern_id: str
    candidates: CandidatesFunc
    build: BuildFunc
    personal: bool = True


@dataclass
class PatternResult:
    sentences: List[RenderedSentence] = field(default_factory=list)
    skips: List[Skip] = field(default_factory=list)
