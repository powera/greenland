"""Swedish lemma-matching hooks for :mod:`langtools.tokenizer`.

``candidate_lemmas`` reverses the definite and plural noun suffixes
("bilarna", "huset"), adjective agreement and comparison, the four verb
conjugations (present, past, supine, s-forms) and the common irregular verbs.
Deponent verbs are stored in their "-s" form ("hoppas"), which the s-form rules
produce directly.
"""

from typing import List

from langtools.suffix_rules import (
    CandidateList,
    expand_endings,
    invert_paradigms,
    strip_suffixes,
)

_NOMINAL_RULES = expand_endings(
    [
        # Definite singular: bilen, huset, flickan, äpplet.
        ("en et n t", ("",)),
        ("an", ("a",)),
        # Plural indefinite / definite: bilar, flickor, pojkar, bilarna, husen.
        ("ar arna", ("", "e")),
        ("or orna", ("a",)),
        ("er erna", ("", "e")),
        ("na ena", ("",)),
        # Genitive.
        ("s", ("",)),
        # Adjective agreement and comparison: stora, stort, nytt, större.
        ("a tt", ("",)),
        ("are ast aste", ("",)),
    ]
)

_VERB_RULES = expand_endings(
    [
        # Present: talar, läser, bor.
        ("ar er", ("a",)),
        ("r", ("",)),
        # Past: talade, hörde, läste, bodde, kände.
        ("ade de te", ("a",)),
        ("dde", ("",)),
        ("nde", ("nna",)),
        ("mde", ("mma",)),
        # Supine / participle: talat, läst, bott, skrivit.
        ("at t it", ("a",)),
        ("tt", ("",)),
        ("ad", ("a",)),
        # s-forms (passive and deponent): finns -> finnas, talas -> tala.
        ("s", ("as", "a")),
        ("ades tes des", ("as", "a")),
        # Imperative is the bare stem: läs -> läsa.
        ("", ("a",)),
    ]
)

_IRREGULAR = invert_paradigms(
    {
        "vara": "är var varit",
        "ha": "har hade haft",
        "gå": "går gick gått",
        "göra": "gör gjorde gjort",
        "kunna": "kan kunde kunnat",
        "vilja": "vill ville velat",
        "skola": "ska skall skulle",
        "få": "får fick fått",
        "se": "ser såg sett",
        "komma": "kom kommit",
        "ta": "tar tog tagit",
        "säga": "säger sa sade sagt",
        "veta": "vet visste vetat",
        "ge": "ger gav gett givit",
        "stå": "står stod stått",
        "bli": "blir blev blivit",
        "måste": "måst",
        "äta": "åt ätit",
        "dricka": "drack druckit",
        "sitta": "satt suttit",
        "ligga": "låg legat",
        "man": "män",
        "bok": "böcker",
        "fot": "fötter",
        "hand": "händer",
        "stad": "städer",
    }
)


def candidate_lemmas(token: str) -> List[str]:
    """Guess Swedish dictionary forms for a lowercased surface token."""
    candidates = CandidateList(token, min_length=2)
    candidates.extend(_IRREGULAR.get(token, ()))
    candidates.extend(strip_suffixes(token, _NOMINAL_RULES, min_stem=2))
    candidates.extend(strip_suffixes(token, _VERB_RULES, min_stem=2))
    return candidates.as_list()
