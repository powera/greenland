"""Shared helpers for rule-based lemma candidate generation.

Language ``tokenizer.py`` modules use these to implement ``candidate_lemmas``:
the inverse of inflection, mapping a surface token ("canciones", "namuose") to
the dictionary forms it could have come from ("canción", "namas").

Reverse morphology is many-to-one and these rules deliberately over-generate.
A candidate is a *guess* to be checked against stored lemmas, never an answer
on its own, so a rule that yields one real lemma and two non-words is doing its
job.  What the rules must avoid is missing the real lemma.
"""

import unicodedata
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

# A suffix table: (surface_suffix, replacement_suffixes).  The empty
# replacement strips the suffix; the empty surface suffix appends to the whole
# token (e.g. Dutch stem "werk" + "en" -> "werken").
SuffixTable = Sequence[Tuple[str, Sequence[str]]]

# Acute/grave accents removed by strip_accents.  Tilde, cedilla, diaeresis and
# the Baltic diacritics are letters in their own right and are kept.
_ACCENT_MARKS = {"̀", "́"}


class CandidateList:
    """Ordered, de-duplicated candidates that never include the input token."""

    def __init__(self, token: str, *, min_length: int = 1) -> None:
        self._token = token
        self._min_length = min_length
        self._items: List[str] = []

    def add(self, candidate: str) -> None:
        """Append *candidate* unless it is the token itself, too short, or seen."""
        if (
            len(candidate) >= self._min_length
            and candidate != self._token
            and candidate not in self._items
        ):
            self._items.append(candidate)

    def extend(self, candidates: Iterable[str]) -> None:
        """Append each of *candidates* in order."""
        for candidate in candidates:
            self.add(candidate)

    def as_list(self) -> List[str]:
        """Return the collected candidates in insertion order."""
        return list(self._items)


def strip_suffixes(word: str, table: SuffixTable, *, min_stem: int = 2) -> List[str]:
    """Apply every matching suffix rule, longest surface suffix first.

    Args:
        word: Lowercased surface token.
        table: ``(surface_suffix, replacements)`` rules.
        min_stem: Characters that must remain once the suffix is removed, so
            short words are not reduced to one-letter stems.

    Returns:
        ``stem + replacement`` for each matching rule, possibly with duplicates.
    """
    out: List[str] = []
    for suffix, replacements in sorted(table, key=lambda rule: -len(rule[0])):
        if not word.endswith(suffix):
            continue
        stem = word[: len(word) - len(suffix)]
        if len(stem) < min_stem:
            continue
        for replacement in replacements:
            out.append(stem + replacement)
    return out


def expand_endings(
    groups: Sequence[Tuple[str, Sequence[str]]],
) -> List[Tuple[str, Tuple[str, ...]]]:
    """Build a suffix table from space-separated ending groups.

    ``[("o as a amos", ("ar",))]`` becomes one rule per ending, which keeps a
    paradigm's endings on one line instead of one tuple each.
    """
    table: List[Tuple[str, Tuple[str, ...]]] = []
    for endings, replacements in groups:
        for ending in endings.split():
            table.append((ending, tuple(replacements)))
    return table


def invert_paradigms(paradigms: Mapping[str, str]) -> Dict[str, Tuple[str, ...]]:
    """Map each listed form to the lemmas it belongs to.

    Args:
        paradigms: ``{lemma: "space separated forms"}`` for irregular words.

    Returns:
        ``{form: (lemma, ...)}``; a form shared by two lemmas (Spanish "fue" is
        both "ser" and "ir") lists both.
    """
    inverted: Dict[str, List[str]] = {}
    for lemma, forms in paradigms.items():
        for form in forms.split():
            lemmas = inverted.setdefault(form, [])
            if lemma not in lemmas:
                lemmas.append(lemma)
    return {form: tuple(lemmas) for form, lemmas in inverted.items()}


def replace_last(text: str, old: str, new: str) -> str:
    """Replace the last occurrence of *old* in *text*; unchanged if absent."""
    index = text.rfind(old)
    if index < 0:
        return text
    return text[:index] + new + text[index + len(old) :]


def strip_accents(text: str) -> str:
    """Remove acute and grave accents only ("jóvenes" -> "jovenes").

    Spanish/Italian/Portuguese mark stress with these, and stress moves under
    inflection; other diacritics (ñ, ç, ü, ą, č) are distinct letters.
    """
    decomposed = unicodedata.normalize("NFD", text)
    kept = "".join(ch for ch in decomposed if ch not in _ACCENT_MARKS)
    return unicodedata.normalize("NFC", kept)
