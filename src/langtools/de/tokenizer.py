"""German lemma-matching hooks for :mod:`langtools.tokenizer`.

``split_contractions`` expands preposition + article fusions ("im", "zum").
``candidate_lemmas`` reverses noun plural/case endings (with umlaut removal),
adjective declension and comparison, regular verb conjugation, past
participles (including separable "angerufen") and the common irregular verbs;
verbs also yield their reflexive lemma ("sich erinnern").

Candidates are lowercase; stored German nouns are capitalized, so callers must
compare case-insensitively.  Separable verbs split across the sentence ("ich
rufe dich an") are out of reach of a per-token rule.
"""

from typing import Dict, List, Tuple

from langtools.suffix_rules import (
    CandidateList,
    expand_endings,
    invert_paradigms,
    replace_last,
    strip_suffixes,
)

_CONTRACTIONS: Dict[str, Tuple[str, ...]] = {
    "im": ("in", "dem"),
    "ins": ("in", "das"),
    "am": ("an", "dem"),
    "ans": ("an", "das"),
    "zum": ("zu", "dem"),
    "zur": ("zu", "der"),
    "beim": ("bei", "dem"),
    "vom": ("von", "dem"),
    "aufs": ("auf", "das"),
    "durchs": ("durch", "das"),
    "fürs": ("für", "das"),
    "ums": ("um", "das"),
    "übers": ("über", "das"),
}

_NOMINAL_RULES = expand_endings(
    [
        # Plural and case endings (nouns) and strong/weak endings (adjectives).
        ("e en n er s es em", ("",)),
        ("ern", ("", "er")),  # Kindern -> Kind
        ("nen", ("",)),  # Freundinnen -> Freundin
        # Comparative and superlative.
        ("ere eren erem erer eres", ("",)),
        ("st ste sten stem ster stes", ("",)),
        ("este esten estem ester estes", ("",)),
    ]
)

_VERB_RULES = expand_endings(
    [
        # Present.
        ("e st t en est et", ("en",)),
        # -eln/-ern verbs keep the "e" of the ending in the stem.
        ("e t st", ("n",)),
        # Weak past.
        ("te test ten tet", ("en", "n")),
        ("ete etest eten etet", ("en",)),
    ]
)

# Separable prefixes that put "ge"/"zu" between themselves and the stem.
_SEPARABLE_PREFIXES = tuple(
    sorted(
        (
            "ab an auf aus bei ein fest fort her hin los mit nach vor weg zu zurück "
            "zusammen weiter heim"
        ).split(),
        key=len,
        reverse=True,
    )
)

_UMLAUTS: Tuple[Tuple[str, str], ...] = (("äu", "au"), ("ä", "a"), ("ö", "o"), ("ü", "u"))

_IRREGULAR = invert_paradigms(
    {
        "sein": "bin bist ist sind seid war warst waren wart gewesen sei wäre wären",
        "haben": "habe hast hat haben habt hatte hattest hatten hattet gehabt hätte hätten",
        "werden": "werde wirst wird werden werdet wurde wurdest wurden geworden würde würden",
        "können": "kann kannst konnte konnten gekonnt könnte könnten",
        "müssen": "muss musst musste mussten gemusst müsste",
        "wollen": "will willst wollte wollten gewollt",
        "sollen": "soll sollst sollte sollten gesollt",
        "dürfen": "darf darfst durfte durften dürfte",
        "mögen": "mag magst mochte mochten möchte möchtest möchten",
        "wissen": "weiß weißt wusste wussten gewusst",
        "gehen": "ging gingen gegangen",
        "kommen": "kam kamen gekommen",
        "sehen": "sieht siehst sah sahen",
        "geben": "gibt gibst gab gaben",
        "nehmen": "nimmt nimmst nahm nahmen genommen",
        "essen": "isst aß aßen gegessen",
        "sprechen": "spricht sprichst sprach sprachen gesprochen",
        "tun": "tue tust tut tat taten getan",
        "stehen": "stand standen gestanden",
        "finden": "fand fanden",
        "bringen": "brachte brachten gebracht",
        "denken": "dachte dachten gedacht",
        "bleiben": "blieb blieben",
        "schreiben": "schrieb schrieben",
        "trinken": "trank tranken getrunken",
        "sitzen": "saß saßen gesessen",
        "liegen": "lag lagen",
        "laufen": "lief liefen",
        "fahren": "fuhr fuhren",
        "helfen": "hilft hilfst half halfen geholfen",
        "treffen": "trifft traf trafen getroffen",
    }
)


def split_contractions(token: str) -> List[str]:
    """Expand preposition + article fusions; ``[token]`` otherwise."""
    return list(_CONTRACTIONS.get(token, (token,)))


def _deumlaut(word: str) -> List[str]:
    """Remove the last umlaut: Äpfel -> apfel, Häuser -> haus-."""
    for old, new in _UMLAUTS:
        if old in word:
            return [replace_last(word, old, new)]
    return []


def _stem_vowel_variants(infinitive: str) -> List[str]:
    """Undo present-tense vowel changes: lies- -> les-, gib- -> geb-, fähr- -> fahr-."""
    stem, ending = infinitive[: -len("en")], "en"
    if not infinitive.endswith("en"):
        return []
    variants = [variant + ending for variant in _deumlaut(stem)]
    for old, new in (("ie", "e"), ("i", "e")):
        if old in stem:
            variants.append(replace_last(stem, old, new) + ending)
    return variants


def _participle_infinitives(word: str) -> List[str]:
    """Infinitives behind a "ge-" participle ("gemacht", "gefahren")."""
    if not word.startswith("ge") or len(word) < 6:
        return []
    core = word[2:]
    out: List[str] = []
    if core.endswith("et"):
        out.append(core[:-2] + "en")  # gearbeitet -> arbeiten
    if core.endswith("t"):
        out.extend([core[:-1] + "en", core[:-1] + "n"])  # gemacht, gewandert
    if core.endswith("en"):
        out.append(core)  # gefahren -> fahren
    return out


def _verb_candidates(word: str) -> List[str]:
    verbs: List[str] = list(_IRREGULAR.get(word, ()))
    verbs.extend(strip_suffixes(word, _VERB_RULES, min_stem=2))
    verbs.extend(_participle_infinitives(word))
    for prefix in _SEPARABLE_PREFIXES:
        rest = word[len(prefix) :]
        if not word.startswith(prefix) or len(rest) < 4:
            continue
        if rest.startswith("ge"):
            verbs.extend(prefix + verb for verb in _participle_infinitives(rest))
        elif rest.startswith("zu"):
            verbs.append(prefix + rest[2:])  # anzurufen -> anrufen
        verbs.extend(prefix + verb for verb in _IRREGULAR.get(rest, ()))
    expanded: List[str] = []
    for verb in verbs:
        if len(verb) > 3 and verb.endswith("n"):
            expanded.append(verb)
            expanded.extend(_stem_vowel_variants(verb))
    return expanded


def candidate_lemmas(token: str) -> List[str]:
    """Guess German dictionary forms (lowercased) for a lowercased token."""
    candidates = CandidateList(token, min_length=2)
    candidates.extend(_IRREGULAR.get(token, ()))

    nominal = strip_suffixes(token, _NOMINAL_RULES, min_stem=2)
    candidates.extend(nominal)
    # Umlaut plurals and comparatives: Mütter -> Mutter, größer -> groß.
    for form in [token, *nominal]:
        candidates.extend(_deumlaut(form))

    verbs = _verb_candidates(token)
    candidates.extend(verbs)
    candidates.extend("sich " + verb for verb in verbs)
    return candidates.as_list()
