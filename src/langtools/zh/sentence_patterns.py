"""Chinese pattern sentences: 想要 / 有 / 喜欢 / 是…的 + color / 很 + feeling /
number + noun, for every person.

Chinese verbs do not inflect and nouns have no plural, so the lesson is the
measure word: 一只猫, 两本书.  Every pattern that counts or points at a noun
needs the noun's ``measure_words`` grammar fact; without it the noun is
skipped.  Liking takes the bare noun (我喜欢猫), so there is one "like"
pattern rather than a singular and a plural one.

Trakaido has no Chinese drill yet; this is the reference for one.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from langtools.sentence_patterns.common import (
    COLORABLE_GROUPS,
    ENGLISH_NUMBERS,
    english_clause,
    english_indefinite,
    missing,
    objects,
    sentence,
)
from langtools.sentence_patterns.types import (
    Outcome,
    SentencePattern,
    SlotAdjective,
    SlotNoun,
    SlotWord,
    Subject,
    WordPools,
)

# 两, not 二, counts things.
FEELINGS = frozenset({"happy", "sad", "angry", "tired", "excited", "afraid", "hungry"})

NUMBERS: Dict[int, str] = {
    2: "两",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
    10: "十",
}

# Subject key -> (default pronoun, feminine alternative or None).
PRONOUNS: Dict[str, Tuple[str, Optional[str]]] = {
    "1s": ("我", None),
    "2s": ("你", None),
    "3s_m": ("他", None),
    "3s_f": ("她", None),
    "1p": ("我们", None),
    "2p": ("你们", None),
    "3p": ("他们", "她们"),
}


def is_mass(noun: SlotNoun) -> bool:
    return noun.countability == "uncountable"


def _predicate(adjective: SlotAdjective) -> str:
    """The adjective without the attributive 的 some translations carry
    (害怕的 -> 害怕); the frame adds 的 where it wants one."""
    text = adjective.target
    return text[:-1] if len(text) > 1 and text.endswith("的") else text


def _clause(subject: Subject, rest: str) -> Tuple[str, List[str]]:
    pronoun, feminine = PRONOUNS[subject.key]
    return f"{pronoun}{rest}", [f"{feminine}{rest}"] if feminine else []


# -- candidates ---------------------------------------------------------------


def _objects(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
    return [(n,) for n in objects(pools.nouns)]


def _countables(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
    return [(n,) for n in objects(pools.nouns) if not is_mass(n)]


def _plurals(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
    return [(n,) for n in objects(pools.nouns) if not is_mass(n)]


def _colorables(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
    nouns = [n for n in pools.nouns if n.group in COLORABLE_GROUPS and not is_mass(n)]
    return [(n, c) for n in nouns for c in pools.colors()]


def _feelings(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
    return [(a,) for a in pools.feelings() if a.english in FEELINGS]


# -- builds -------------------------------------------------------------------


def _noun(words: Sequence[SlotWord]) -> SlotNoun:
    noun = words[0]
    assert isinstance(noun, SlotNoun)
    return noun


def _want(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if is_mass(noun):
        thing, english_thing = noun.target, noun.english
    elif not noun.measure_word:
        return [missing("want", noun, "measure_words")]
    else:
        thing, english_thing = f"一{noun.measure_word}{noun.target}", english_indefinite(
            noun.english
        )
    correct, accepted = _clause(subject, f"想要{thing}")
    english = english_clause(subject, "want", english_thing)
    return [sentence("want", (noun,), english, correct, subject, tuple(accepted))]


def _have(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if not noun.measure_word:
        return [missing("have", noun, "measure_words")]
    correct, accepted = _clause(subject, f"有一{noun.measure_word}{noun.target}")
    english = english_clause(subject, "have", english_indefinite(noun.english))
    return [sentence("have", (noun,), english, correct, subject, tuple(accepted))]


def _like(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if is_mass(noun):
        english_thing = noun.english
    elif not noun.english_plural:
        return [missing("like", noun, "en plural")]
    else:
        english_thing = noun.english_plural
    correct, accepted = _clause(subject, f"喜欢{noun.target}")
    english = english_clause(subject, "like", english_thing)
    return [sentence("like", (noun,), english, correct, subject, tuple(accepted))]


def _color(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    noun = _noun(words)
    color = words[1]
    assert isinstance(color, SlotAdjective)
    if not noun.measure_word:
        return [missing("color", noun, "measure_words")]
    # "This cat is black": 这只猫是黑色的.  English "the" has no measure-word
    # equivalent, so the prompt names the demonstrative.
    return [
        sentence(
            "color",
            (noun, color),
            f"This {noun.english} is {color.english}.",
            f"这{noun.measure_word}{noun.target}是{_predicate(color)}的",
        )
    ]


def _feeling(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    feeling = words[0]
    assert isinstance(feeling, SlotAdjective)
    # A bare adjective predicate needs a degree adverb; 很 is the neutral one.
    correct, accepted = _clause(subject, f"很{_predicate(feeling)}")
    english = english_clause(subject, "be", feeling.english)
    return [sentence("feeling", (feeling,), english, correct, subject, tuple(accepted))]


def _number(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if not noun.measure_word:
        return [missing("number", noun, "measure_words")]
    if not noun.english_plural:
        return [missing("number", noun, "en plural")]
    results: List[Outcome] = []
    for value, chinese in NUMBERS.items():
        correct, accepted = _clause(subject, f"有{chinese}{noun.measure_word}{noun.target}")
        english = english_clause(subject, "have", f"{ENGLISH_NUMBERS[value]} {noun.english_plural}")
        results.append(sentence("number", (noun,), english, correct, subject, tuple(accepted)))
    return results


PATTERNS: List[SentencePattern] = [
    SentencePattern("want", _objects, _want),
    SentencePattern("have", _countables, _have),
    SentencePattern("like", _objects, _like),
    SentencePattern("color", _colorables, _color, personal=False),
    SentencePattern("feeling", _feelings, _feeling),
    SentencePattern("number", _plurals, _number),
]
