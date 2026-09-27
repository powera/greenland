"""Dutch lemma-matching hooks for :mod:`langtools.tokenizer`.

``split_contractions`` expands the apostrophe clippings ("'t", "z'n").
``candidate_lemmas`` reverses plurals and diminutives, adjective "-e" and
comparison, regular verb conjugation and participles (including separable
"opgebeld") and the common irregular verbs; verbs also yield their reflexive
lemma ("zich vergissen").

Dutch spelling doubles or undoubles letters as syllables open and close
("boom" / "bomen", "kat" / "katten", "brief" / "brieven"), so every stripped
stem is re-spelled in each of those ways before an ending is added back.
"""

from typing import Dict, List, Tuple

from langtools.suffix_rules import CandidateList, invert_paradigms

_CONTRACTIONS: Dict[str, Tuple[str, ...]] = {
    "'t": ("het",),
    "'n": ("een",),
    "m'n": ("mijn",),
    "z'n": ("zijn",),
    "d'r": ("haar",),
    "'s": ("des",),
}

_VOWELS = "aeiouy"
_LONG_VOWELS = ("aa", "ee", "oo", "uu")

_SEPARABLE_PREFIXES = tuple(
    sorted(
        (
            "aan af bij door in mee na om op over terug toe uit vast voor weg samen tegen langs"
        ).split(),
        key=len,
        reverse=True,
    )
)

_IRREGULAR = invert_paradigms(
    {
        "zijn": "ben bent is zijn was waren geweest",
        "hebben": "heb hebt heeft had hadden gehad",
        "gaan": "ga gaat gingen ging gegaan",
        "doen": "doe doet deed deden gedaan",
        "staan": "sta staat stond stonden gestaan",
        "slaan": "sla slaat sloeg sloegen geslagen",
        "zien": "zie ziet zag zagen gezien",
        "kunnen": "kan kun kunt kon konden gekund",
        "willen": "wil wilt wou wilde wilden gewild",
        "zullen": "zal zult zou zouden",
        "mogen": "mag mocht mochten gemogen",
        "moeten": "moet moest moesten gemoeten",
        "komen": "kom komt kwam kwamen gekomen",
        "weten": "weet weten wist wisten geweten",
        "worden": "word wordt werd werden geworden",
        "krijgen": "krijg krijgt kreeg kregen gekregen",
        "nemen": "neem neemt nam namen genomen",
        "geven": "geef geeft gaf gaven gegeven",
        "eten": "eet eet at aten gegeten",
        "lezen": "lees leest las lazen gelezen",
        "zeggen": "zeg zegt zei zeiden gezegd",
        "vinden": "vond vonden gevonden",
        "denken": "dacht dachten gedacht",
        "brengen": "bracht brachten gebracht",
        "kopen": "kocht kochten gekocht",
        "zoeken": "zocht zochten gezocht",
    }
)


def split_contractions(token: str) -> List[str]:
    """Expand apostrophe clippings; ``[token]`` otherwise."""
    return list(_CONTRACTIONS.get(token, (token,)))


def _respellings(stem: str) -> List[str]:
    """Spellings a stem may take once its ending is removed or restored.

    Covers the four Dutch alternations: doubled consonant ("katt-" / "kat"),
    doubled vowel ("bom-" / "boom"), and final devoicing of v/z ("briev-" /
    "brief", "huiz-" / "huis").  Returns the input first.
    """
    variants = [stem]
    if len(stem) >= 2 and stem[-1] == stem[-2] and stem[-1] not in _VOWELS:
        variants.append(stem[:-1])
    for voiced, voiceless in (("v", "f"), ("z", "s")):
        for variant in list(variants):
            if variant.endswith(voiced):
                variants.append(variant[:-1] + voiceless)
            elif variant.endswith(voiceless):
                variants.append(variant[:-1] + voiced)
    for variant in list(variants):
        if len(variant) < 2 or variant[-1] in _VOWELS:
            continue
        head, vowel = variant[:-2], variant[-2]
        if vowel not in "aeou":
            continue
        if variant[-3:-1] in _LONG_VOWELS:
            # Closed long vowel re-opens as a single letter: "loop" -> "lop-en".
            variants.append(variant[:-3] + vowel + variant[-1])
        elif not head or head[-1] not in _VOWELS:
            # Open short spelling may be a long vowel: "bom-" -> "boom".
            variants.append(head + vowel + vowel + variant[-1])
            # ... or a closed short vowel that doubles its consonant: "zit" -> "zitt-en".
            variants.append(variant + variant[-1])
    out: List[str] = []
    for variant in variants:
        if variant not in out:
            out.append(variant)
    return out


def _singular_stems(token: str) -> List[str]:
    """Base nouns/adjectives behind plural, diminutive, inflected or compared forms."""
    stems: List[str] = []
    for suffix in ("eren", "en", "e", "er", "ste", "etje", "tje", "pje", "kje", "je"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            stems.extend(_respellings(token[: -len(suffix)]))
    for suffix in ("'s", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            stems.append(token[: -len(suffix)])
    return stems


def _infinitives_from_stem(stem: str) -> List[str]:
    """Infinitives for a verb stem: "werk" -> "werken", "loop" -> "lopen"."""
    return [variant + "en" for variant in _respellings(stem)]


def _participle_infinitives(word: str) -> List[str]:
    """Infinitives behind a "ge-" participle ("gewerkt", "gelopen")."""
    if not word.startswith("ge") or len(word) < 5:
        return []
    core = word[2:]
    if core.endswith("en"):
        return [core]
    if core.endswith(("d", "t")):
        return _infinitives_from_stem(core[:-1])
    return []


def _verb_candidates(token: str) -> List[str]:
    verbs: List[str] = list(_IRREGULAR.get(token, ()))
    # Present: bare stem ("werk") or stem + t ("werkt").
    verbs.extend(_infinitives_from_stem(token))
    if token.endswith("t") and len(token) > 3:
        verbs.extend(_infinitives_from_stem(token[:-1]))
    # Weak past: -de/-te/-den/-ten.
    for suffix in ("den", "ten", "de", "te"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            verbs.extend(_infinitives_from_stem(token[: -len(suffix)]))
    verbs.extend(_participle_infinitives(token))
    for prefix in _SEPARABLE_PREFIXES:
        rest = token[len(prefix) :]
        if token.startswith(prefix) and len(rest) >= 5 and rest.startswith("ge"):
            verbs.extend(prefix + verb for verb in _participle_infinitives(rest))
    return [verb for verb in verbs if len(verb) > 3 and verb.endswith("n")]


def candidate_lemmas(token: str) -> List[str]:
    """Guess Dutch dictionary forms for a lowercased surface token."""
    candidates = CandidateList(token, min_length=2)
    candidates.extend(_IRREGULAR.get(token, ()))
    candidates.extend(_singular_stems(token))
    verbs = _verb_candidates(token)
    candidates.extend(verbs)
    candidates.extend("zich " + verb for verb in verbs)
    return candidates.as_list()
