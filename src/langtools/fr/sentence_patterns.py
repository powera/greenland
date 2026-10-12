"""French pattern sentences: vouloir / avoir / aimer / être + color /
être + feeling / number + noun, for every person.

The lessons are the article: its gender, the partitive for a mass noun
("je veux du pain"), le/la for a liked thing where English has none
("j'aime le pain"), and elision (l'avion, j'ai).  French never drops the
subject pronoun.

Mirrors Trakaido's frenchSentenceQuiz.ts.
"""

import re
from typing import Dict, List, Optional, Sequence, Tuple

from langtools.sentence_patterns.common import (
    COLORABLE_GROUPS,
    ENGLISH_NUMBERS,
    adjective_forms,
    capitalize,
    english_clause,
    english_indefinite,
    missing,
    missing_gender,
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

# Words starting with an aspirated h, which takes le/la rather than l'.
FEELINGS = frozenset({"happy", "sad", "tired", "excited"})

ASPIRATED_H = frozenset(
    {
        "hache",
        "haie",
        "hall",
        "hamac",
        "hamburger",
        "hamster",
        "hanche",
        "hangar",
        "haricot",
        "harpe",
        "hasard",
        "hauteur",
        "héros",
        "hérisson",
        "hibou",
        "hockey",
        "homard",
        "hot-dog",
        "housse",
        "hublot",
        "huit",
    }
)

NUMBERS: Dict[int, str] = {
    2: "deux",
    3: "trois",
    4: "quatre",
    5: "cinq",
    6: "six",
    7: "sept",
    8: "huit",
    9: "neuf",
    10: "dix",
}

VERBS: Dict[str, Dict[str, str]] = {
    "vouloir": {
        "1s": "veux",
        "2s": "veux",
        "3s": "veut",
        "1p": "voulons",
        "2p": "voulez",
        "3p": "veulent",
    },
    "avoir": {"1s": "ai", "2s": "as", "3s": "a", "1p": "avons", "2p": "avez", "3p": "ont"},
    "aimer": {
        "1s": "aime",
        "2s": "aimes",
        "3s": "aime",
        "1p": "aimons",
        "2p": "aimez",
        "3p": "aiment",
    },
    "être": {"1s": "suis", "2s": "es", "3s": "est", "1p": "sommes", "2p": "êtes", "3p": "sont"},
}

# Subject key -> (default pronoun, feminine alternative or None).
PRONOUNS: Dict[str, Tuple[str, Optional[str]]] = {
    "1s": ("je", None),
    "2s": ("tu", None),
    "3s_m": ("il", None),
    "3s_f": ("elle", None),
    "1p": ("nous", None),
    "2p": ("vous", None),
    "3p": ("ils", "elles"),
}


def is_mass(noun: SlotNoun) -> bool:
    return noun.countability == "uncountable"


def elides(word: str) -> bool:
    """Whether le/la/de la/je shorten before this word."""
    lower = word.lower()
    if lower.startswith("h"):
        return re.split(r"[\s-]", lower)[0] not in ASPIRATED_H
    return bool(re.match(r"[aeiouyàâäéèêëîïôöùûüœæ]", lower))


def _with(article: str, word: str) -> str:
    return f"{article}{word}" if article.endswith("'") else f"{article} {word}"


def _the(noun: SlotNoun) -> str:
    """'le chien', 'la pomme', "l'avion"."""
    article = "l'" if elides(noun.target) else ("le" if noun.gender == "masculine" else "la")
    return _with(article, noun.target)


def _a(noun: SlotNoun) -> str:
    return f"{'un' if noun.gender == 'masculine' else 'une'} {noun.target}"


def _some(noun: SlotNoun) -> str:
    """'du pain', 'de la viande', "de l'eau"."""
    article = "de l'" if elides(noun.target) else ("du" if noun.gender == "masculine" else "de la")
    return _with(article, noun.target)


def _clause(subject: Subject, verb: str, rest: str) -> Tuple[str, List[str]]:
    """'Je veux un chat', "J'ai un chat", 'Ils veulent un chat'."""
    form = VERBS[verb][subject.person]
    pronoun, feminine = PRONOUNS[subject.key]
    variants = [pronoun] + ([feminine] if feminine else [])
    texts = [
        capitalize(_with("j'" if p == "je" and elides(form) else p, f"{form} {rest}"))
        for p in variants
    ]
    return texts[0], texts[1:]


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
    if noun.gender is None:
        return [missing_gender("want", noun)]
    if is_mass(noun):
        thing, english_thing = _some(noun), noun.english
    else:
        thing, english_thing = _a(noun), english_indefinite(noun.english)
    correct, accepted = _clause(subject, "vouloir", thing)
    english = english_clause(subject, "want", english_thing)
    return [sentence("want", (noun,), english, correct, subject, tuple(accepted))]


def _have(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if noun.gender is None:
        return [missing_gender("have", noun)]
    correct, accepted = _clause(subject, "avoir", _a(noun))
    english = english_clause(subject, "have", english_indefinite(noun.english))
    return [sentence("have", (noun,), english, correct, subject, tuple(accepted))]


def _like_one(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if noun.gender is None:
        return [missing_gender("like-one", noun)]
    correct, accepted = _clause(subject, "aimer", _the(noun))
    thing = noun.english if is_mass(noun) else f"the {noun.english}"
    english = english_clause(subject, "like", thing)
    return [sentence("like-one", (noun,), english, correct, subject, tuple(accepted))]


def _like_many(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if not noun.forms.get("plural"):
        return [missing("like-many", noun, "form plural")]
    if not noun.english_plural:
        return [missing("like-many", noun, "en plural")]
    correct, accepted = _clause(subject, "aimer", f"les {noun.forms['plural']}")
    english = english_clause(subject, "like", noun.english_plural)
    return [sentence("like-many", (noun,), english, correct, subject, tuple(accepted))]


def _color(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    noun = _noun(words)
    color = words[1]
    assert isinstance(color, SlotAdjective)
    if noun.gender is None:
        return [missing_gender("color", noun)]
    forms = adjective_forms(color)
    if forms is None:
        return [missing("color", color, "adjective gender/number forms")]
    results: List[Outcome] = [
        sentence(
            "color",
            (noun, color),
            f"The {noun.english} is {color.english}.",
            f"{capitalize(_the(noun))} est {forms[(noun.gender, False)]}",
        )
    ]
    if not noun.forms.get("plural"):
        results.append(missing("color", noun, "form plural"))
    elif not noun.english_plural:
        results.append(missing("color", noun, "en plural"))
    else:
        results.append(
            sentence(
                "color",
                (noun, color),
                f"The {noun.english_plural} are {color.english}.",
                f"Les {noun.forms['plural']} sont {forms[(noun.gender, True)]}",
            )
        )
    return results


def _feeling(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    feeling = words[0]
    assert isinstance(feeling, SlotAdjective)
    forms = adjective_forms(feeling)
    if forms is None:
        return [missing("feeling", feeling, "adjective gender/number forms")]
    plural = subject.person.endswith("p")
    etre = VERBS["être"][subject.person]
    pronoun, feminine_pronoun = PRONOUNS[subject.key]
    if subject.gender:
        pairs = [(pronoun, forms[(subject.gender, plural)])]
    else:
        # Either gender, with the pronoun agreeing: "elles sont fatiguées".
        pairs = [
            (pronoun, forms[("masculine", plural)]),
            (feminine_pronoun or pronoun, forms[("feminine", plural)]),
        ]
    variants = [capitalize(f"{p} {etre} {adjective}") for p, adjective in pairs]
    english = english_clause(subject, "be", feeling.english)
    return [sentence("feeling", (feeling,), english, variants[0], subject, tuple(variants[1:]))]


def _number(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if not noun.forms.get("plural"):
        return [missing("number", noun, "form plural")]
    if not noun.english_plural:
        return [missing("number", noun, "en plural")]
    results: List[Outcome] = []
    for value, french in NUMBERS.items():
        correct, accepted = _clause(subject, "avoir", f"{french} {noun.forms['plural']}")
        digits, _ = _clause(subject, "avoir", f"{value} {noun.forms['plural']}")
        english = english_clause(subject, "have", f"{ENGLISH_NUMBERS[value]} {noun.english_plural}")
        results.append(
            sentence("number", (noun,), english, correct, subject, tuple(accepted + [digits]))
        )
    return results


PATTERNS: List[SentencePattern] = [
    SentencePattern("want", _objects, _want),
    SentencePattern("have", _countables, _have),
    SentencePattern("like-one", _objects, _like_one),
    SentencePattern("like-many", _plurals, _like_many),
    SentencePattern("color", _colorables, _color, personal=False),
    SentencePattern("feeling", _feelings, _feeling),
    SentencePattern("number", _plurals, _number),
]
