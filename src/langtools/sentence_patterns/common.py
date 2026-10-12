"""Helpers shared by every language's pattern sentences: the English side,
the slot-word groups, and the checks that turn a missing form into a Skip."""

import re

from typing import Dict, List, Optional, Tuple

from langtools.sentence_patterns.types import (
    Gender,
    RenderedSentence,
    Skip,
    SlotAdjective,
    SlotNoun,
    SlotWord,
    Subject,
)

# Noun subtypes for things you can sensibly want, have and like; the same
# groups as Trakaido's objectGroups.
OBJECT_GROUPS = frozenset(
    {"food", "clothing_accessory", "animal", "small_movable_object", "vehicle"}
)

# Noun subtypes you can sensibly describe by color.
COLORABLE_GROUPS = frozenset(
    {
        "clothing_accessory",
        "animal",
        "small_movable_object",
        "vehicle",
        "shape",
        "building_structure",
    }
)

ENGLISH_NUMBERS: Dict[int, str] = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}

_ENGLISH_PRESENT: Dict[str, Tuple[str, str]] = {
    # verb -> (form for 3s, form for every other person); "be" is special-cased.
    "want": ("wants", "want"),
    "have": ("has", "have"),
    "like": ("likes", "like"),
}


def english_verb(verb: str, subject: Subject) -> str:
    if verb == "be":
        return {"1s": "am", "3s": "is"}.get(subject.person, "are")
    third, other = _ENGLISH_PRESENT[verb]
    return third if subject.person == "3s" else other


def capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def english_clause(subject: Subject, verb: str, rest: str) -> str:
    """'he' + 'want' + 'a cat' -> 'He wants a cat.'"""
    return capitalize(f"{subject.english} {english_verb(verb, subject)} {rest}.")


def english_indefinite(phrase: str) -> str:
    first = phrase.split()[0].lower() if phrase.split() else ""
    # Common silent-h and consonantal vowel onsets in beginner vocabulary.
    if first.startswith(("hour", "honest", "honor", "honour", "heir")):
        return f"an {phrase}"
    if first.startswith(
        ("one", "euro", "unicorn", "uniform", "union", "unit", "university", "utensil")
    ):
        return f"a {phrase}"
    return f"an {phrase}" if first[:1] in "aeiou" else f"a {phrase}"


def missing(pattern_id: str, word: SlotWord, what: str) -> Skip:
    return Skip(pattern_id, word.guid, f"missing {what}")


def missing_gender(pattern_id: str, noun: SlotNoun) -> Skip:
    if noun.gender_fact:
        return missing(pattern_id, noun, f"masculine/feminine gender (fact is {noun.gender_fact})")
    return missing(pattern_id, noun, "grammatical_gender")


def require_forms(noun: SlotNoun, keys: Tuple[str, ...]) -> Optional[str]:
    """The first of ``keys`` the noun lacks, as a Skip reason fragment."""
    for key in keys:
        if not noun.forms.get(key):
            return f"form {key}"
    return None


def adjective_form(adjective: SlotAdjective, gender: Gender, plural: bool) -> Optional[str]:
    """The nominative form for a gender and number.

    Spanish and French key these ``singular_m``; Lithuanian prefixes the case.
    """
    name = f"{'plural' if plural else 'singular'}_{gender[0]}"
    return adjective.forms.get(name) or adjective.forms.get(f"nominative_{name}")


def adjective_forms(adjective: SlotAdjective) -> Optional[Dict[Tuple[Gender, bool], str]]:
    """All four gender/number forms, or None when any is missing."""
    result: Dict[Tuple[Gender, bool], str] = {}
    genders: List[Gender] = ["masculine", "feminine"]
    for gender in genders:
        for plural in (False, True):
            form = adjective_form(adjective, gender, plural)
            if not form:
                return None
            result[(gender, plural)] = form
    return result


def sentence(
    pattern_id: str,
    words: Tuple[SlotWord, ...],
    english: str,
    target: str,
    subject: Optional[Subject] = None,
    also_accepted: Tuple[str, ...] = (),
) -> RenderedSentence:
    accepted = tuple(dict.fromkeys(a for a in also_accepted if a != target))
    return RenderedSentence(
        pattern_id=pattern_id,
        english=english,
        target=target,
        word_guids=tuple(w.guid for w in words),
        subject=subject.key if subject else None,
        detail=subject.detail if subject else None,
        also_accepted=accepted,
    )


def objects(nouns: List[SlotNoun]) -> List[SlotNoun]:
    return [n for n in nouns if n.group in OBJECT_GROUPS]


def strip_disambiguation(text: str) -> str:
    """Remove parenthetical sense labels from displayed vocabulary."""
    return re.sub(r"\s+", " ", re.sub(r"\s*\([^)]*\)\s*", " ", text)).strip()
