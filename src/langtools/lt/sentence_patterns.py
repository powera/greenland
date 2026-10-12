"""Lithuanian pattern sentences: noriu / turiu / man patinka / būti + color /
būti + feeling / number + noun, for every person.

Lithuanian has no articles, so the lesson is the case each verb takes:
norėti + genitive, turėti + accusative, patikti + nominative (with the liker
in the dative), and after turėti a number 2-9 agrees with the noun in the
accusative plural while dešimt takes the genitive plural.

Mirrors Trakaido's LithuanianSentenceQuiz.swift / lithuanianSentenceQuiz.ts.
"""

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
    require_forms,
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

# Numbers 2-10 as they appear after turėti: (masculine, feminine).
FEELINGS = frozenset({"happy", "sad", "angry", "tired", "excited", "afraid", "hungry"})

NUMBERS: Dict[int, Tuple[str, str]] = {
    2: ("du", "dvi"),
    3: ("tris", "tris"),
    4: ("keturis", "keturias"),
    5: ("penkis", "penkias"),
    6: ("šešis", "šešias"),
    7: ("septynis", "septynias"),
    8: ("aštuonis", "aštuonias"),
    9: ("devynis", "devynias"),
    10: ("dešimt", "dešimt"),
}

# Subject key -> (default pronoun, feminine alternative or None).
PRONOUNS: Dict[str, Tuple[str, Optional[str]]] = {
    "1s": ("aš", None),
    "2s": ("tu", None),
    "3s_m": ("jis", None),
    "3s_f": ("ji", None),
    "1p": ("mes", None),
    "2p": ("jūs", None),
    "3p": ("jie", "jos"),
}

DATIVE_PRONOUNS: Dict[str, Tuple[str, Optional[str]]] = {
    "1s": ("man", None),
    "2s": ("tau", None),
    "3s_m": ("jam", None),
    "3s_f": ("jai", None),
    "1p": ("mums", None),
    "2p": ("jums", None),
    "3p": ("jiems", "joms"),
}

VERBS: Dict[str, Dict[str, str]] = {
    "norėti": {
        "1s": "noriu",
        "2s": "nori",
        "3s": "nori",
        "1p": "norime",
        "2p": "norite",
        "3p": "nori",
    },
    "turėti": {
        "1s": "turiu",
        "2s": "turi",
        "3s": "turi",
        "1p": "turime",
        "2p": "turite",
        "3p": "turi",
    },
    "mėgti": {
        "1s": "mėgstu",
        "2s": "mėgsti",
        "3s": "mėgsta",
        "1p": "mėgstame",
        "2p": "mėgstate",
        "3p": "mėgsta",
    },
    "būti": {"1s": "esu", "2s": "esi", "3s": "yra", "1p": "esame", "2p": "esate", "3p": "yra"},
}


def is_mass(noun: SlotNoun) -> bool:
    return noun.countability == "uncountable"


def _clause(subject: Subject, verb: str, rest: str) -> Tuple[str, List[str]]:
    """'Noriu duonos' for 1st/2nd person, 'Jis nori duonos' for 3rd.

    The verb ending marks 1st and 2nd person, so the pronoun is optional
    there; in the 3rd person it carries the gender and stays.
    """
    form = VERBS[verb][subject.person]
    pronoun, feminine = PRONOUNS[subject.key]
    with_pronoun = f"{capitalize(pronoun)} {form} {rest}"
    accepted: List[str] = []
    if feminine:
        accepted.append(f"{capitalize(feminine)} {form} {rest}")
    if subject.person.startswith("3"):
        return with_pronoun, accepted
    return capitalize(f"{form} {rest}"), [with_pronoun] + accepted


def _like(subject: Subject, liked: str, liked_accusative: str) -> Tuple[str, List[str]]:
    """'Man patinka X', also 'Mėgstu X' with the accusative."""
    dative, feminine = DATIVE_PRONOUNS[subject.key]
    correct = f"{capitalize(dative)} patinka {liked}"
    accepted = [f"{capitalize(feminine)} patinka {liked}"] if feminine else []
    megti, megti_accepted = _clause(subject, "mėgti", liked_accusative)
    return correct, accepted + [megti] + megti_accepted


# -- candidates --------------------------------------------------------------


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


# -- builds ------------------------------------------------------------------


def _noun(words: Sequence[SlotWord]) -> SlotNoun:
    noun = words[0]
    assert isinstance(noun, SlotNoun)
    return noun


def _want(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if lacking := require_forms(noun, ("genitive_singular",)):
        return [missing("want", noun, lacking)]
    thing = noun.english if is_mass(noun) else english_indefinite(noun.english)
    correct, accepted = _clause(subject, "norėti", noun.forms["genitive_singular"])
    english = english_clause(subject, "want", thing)
    return [sentence("want", (noun,), english, correct, subject, tuple(accepted))]


def _have(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if lacking := require_forms(noun, ("accusative_singular",)):
        return [missing("have", noun, lacking)]
    correct, accepted = _clause(subject, "turėti", noun.forms["accusative_singular"])
    english = english_clause(subject, "have", english_indefinite(noun.english))
    return [sentence("have", (noun,), english, correct, subject, tuple(accepted))]


def _like_one(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if lacking := require_forms(noun, ("accusative_singular",)):
        return [missing("like-one", noun, lacking)]
    nominative = noun.forms.get("nominative_singular") or noun.target
    correct, accepted = _like(subject, nominative, noun.forms["accusative_singular"])
    thing = noun.english if is_mass(noun) else f"the {noun.english}"
    english = english_clause(subject, "like", thing)
    return [sentence("like-one", (noun,), english, correct, subject, tuple(accepted))]


def _like_many(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if lacking := require_forms(noun, ("nominative_plural", "accusative_plural")):
        return [missing("like-many", noun, lacking)]
    if not noun.english_plural:
        return [missing("like-many", noun, "en plural")]
    correct, accepted = _like(
        subject, noun.forms["nominative_plural"], noun.forms["accusative_plural"]
    )
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
    singular = capitalize(noun.forms.get("nominative_singular") or noun.target)
    adjective = forms[(noun.gender, False)]
    results: List[Outcome] = [
        sentence(
            "color",
            (noun, color),
            f"The {noun.english} is {color.english}.",
            f"{singular} yra {adjective}",
            also_accepted=(f"{singular} {adjective}",),
        )
    ]
    if not noun.forms.get("nominative_plural"):
        results.append(missing("color", noun, "form nominative_plural"))
    elif not noun.english_plural:
        results.append(missing("color", noun, "en plural"))
    else:
        plural = capitalize(noun.forms["nominative_plural"])
        adjective = forms[(noun.gender, True)]
        results.append(
            sentence(
                "color",
                (noun, color),
                f"The {noun.english_plural} are {color.english}.",
                f"{plural} yra {adjective}",
                also_accepted=(f"{plural} {adjective}",),
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
    gender = subject.gender or "masculine"
    be = VERBS["būti"][subject.person]
    pronoun, feminine_pronoun = PRONOUNS[subject.key]
    correct = f"{capitalize(pronoun)} {be} {forms[(gender, plural)]}"
    accepted: List[str] = []
    if subject.gender is None:
        # I/you/we are either gender; they takes jos for an all-female group.
        accepted.append(
            f"{capitalize(feminine_pronoun or pronoun)} {be} {forms[('feminine', plural)]}"
        )
    if not subject.person.startswith("3"):
        accepted += [capitalize(a.split(" ", 1)[1]) for a in [correct] + accepted]
    english = english_clause(subject, "be", feeling.english)
    return [sentence("feeling", (feeling,), english, correct, subject, tuple(accepted))]


def _number(words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
    assert subject is not None
    noun = _noun(words)
    if noun.gender is None:
        return [missing_gender("number", noun)]
    if lacking := require_forms(noun, ("accusative_plural", "genitive_plural")):
        return [missing("number", noun, lacking)]
    if not noun.english_plural:
        return [missing("number", noun, "en plural")]
    results: List[Outcome] = []
    for value, (masculine, feminine) in NUMBERS.items():
        number = masculine if noun.gender == "masculine" else feminine
        # dešimt counts like a noun and takes the genitive plural.
        case = "genitive_plural" if value == 10 else "accusative_plural"
        correct, accepted = _clause(subject, "turėti", f"{number} {noun.forms[case]}")
        digits, _ = _clause(subject, "turėti", f"{value} {noun.forms[case]}")
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
