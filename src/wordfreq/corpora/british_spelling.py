"""Fold British spellings onto the American ones the database stores.

The database's English lemmas and forms are American ("program", "labeling",
"organize"), and en-GB variants are not yet modelled.  A corpus written in
British English -- Europarl above all -- therefore counts "programme" as a
word of its own: it matches no lemma at load time, and it surfaces as a new
word candidate that is really an old word misspelled for us.  Folding at build
time credits the occurrence to the spelling the database will link.

Candidates come from a handful of regular rules (``-ise`` -> ``-ize``,
``-our`` -> ``-or``, ``-tre`` -> ``-ter``, ``-lled`` -> ``-led``, ...) plus a
short list of irregulars.  The rules alone over-generate -- ``-lled`` ->
``-led`` would turn "filled" into "filed" -- so a fold is accepted only when

* the candidate is a known American spelling, and
* the British form itself is *not* a known spelling.

"Known" is the caller's reference set: the database's English lemma and form
texts, plus an American corpus's vocabulary.  "filled" is a form of *fill*, so
it is known and never folds; "honour" is not, and "honor" is, so it does.

Purely mechanical: no network, no database access here.
"""

import re
from typing import Collection, Dict, Iterable, List, Tuple

# The British -re words, without the -re; each group match is the stem.
_RE_STEMS = (
    r"(cent|met|lit|theat|spect|fib|sab|lust|meag|somb|calib|och|sepulch|goit|mit|nit|"
    r"saltpet|manoeuv|reconnoit)re"
)

# (pattern, replacement) applied one at a time to a lowercase word.
_RULES: Tuple[Tuple["re.Pattern[str]", str], ...] = (
    (re.compile(r"isation(s?)$"), r"ization\1"),
    (re.compile(r"is(e|es|ed|ing|er|ers)$"), r"iz\1"),
    (re.compile(r"ys(e|es|ed|ing)$"), r"yz\1"),
    # Only a word-final -our, or one before a suffix: "mourning" is not
    # "morning", however well the reference set knows the latter.
    (
        re.compile(r"our(s|ed|ing|able|ably|ite|ites|ful|less|er|ers|ism|ist|ists|hood|y)?$"),
        r"or\1",
    ),
    # -re -> -er by stem, not by shape: French in the corpus ("entre", "votre",
    # "lettre") looks exactly like "centre" and folds into real English words.
    # A prefix is allowed, so "kilometre" and "epicentre" follow their stem.
    (re.compile(_RE_STEMS + r"(s?)$"), r"\1er\2"),
    (re.compile(_RE_STEMS + r"d$"), r"\1ered"),
    (re.compile(r"ogramme(s?)$"), r"ogram\1"),
    (re.compile(r"ll(ed|ing|er|ers)$"), r"l\1"),
    (re.compile(r"ence$"), "ense"),
    # Medial only ("paediatric", "foetus"): a final "-oes" is a plural, and
    # "canoes" is not "canes".
    (re.compile(r"ae(?=[^aeiou][a-z])"), "e"),
    (re.compile(r"oe(?=[^aeiou][a-z])"), "e"),
)

# Ordinary words the rules would mangle into a *different* known word.
_NEVER_FOLD: frozenset[str] = frozenset(
    {
        "pour",
        "pours",
        "poured",
        "pouring",
        "tour",
        "tours",
        "toured",
        "touring",
        "flour",
        "hours",
        "scour",
        "scours",
        "scoured",
        "scouring",
        "prise",
        "prised",
    }
)

# Irregular pairs no rule produces, or one would produce wrongly.
_IRREGULAR: Dict[str, str] = {
    "practise": "practice",
    "practised": "practiced",
    "practising": "practicing",
    "judgement": "judgment",
    "judgements": "judgments",
    "ageing": "aging",
    "grey": "gray",
    "tyre": "tire",
    "tyres": "tires",
    "plough": "plow",
    "aluminium": "aluminum",
    "fulfil": "fulfill",
    "fulfils": "fulfills",
    "fulfilment": "fulfillment",
    "enrol": "enroll",
    "enrolment": "enrollment",
    "instil": "instill",
    "skilful": "skillful",
    "wilful": "willful",
    "cheque": "check",
    "cheques": "checks",
    "kerb": "curb",
    "sceptic": "skeptic",
    "sceptical": "skeptical",
    "scepticism": "skepticism",
    "manoeuvre": "maneuver",
    "manoeuvres": "maneuvers",
}

# Words shorter than this are never folded by rule: "four" -> "for".
_MIN_RULE_LENGTH = 5


def american_candidates(word: str) -> List[str]:
    """Possible American spellings of a lowercase word, most specific first."""
    if word in _IRREGULAR:
        return [_IRREGULAR[word]]
    if len(word) < _MIN_RULE_LENGTH or word in _NEVER_FOLD:
        return []
    candidates: List[str] = []
    for pattern, replacement in _RULES:
        candidate = pattern.sub(replacement, word)
        if candidate != word and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def build_spelling_map(words: Iterable[str], known: Collection[str]) -> Dict[str, str]:
    """``{british: american}`` for the words in ``words`` that should fold.

    Args:
        words: The corpus vocabulary to consider, any case.
        known: Lowercase spellings accepted as American -- the target of a
            fold must be in it, and the source must not be.

    Returns:
        Lowercase mapping.  Irregulars fold whenever their target is known.
    """
    mapping: Dict[str, str] = {}
    for word in {word.lower() for word in words}:
        if word in known and word not in _IRREGULAR:
            continue
        for candidate in american_candidates(word):
            if candidate in known:
                mapping[word] = candidate
                break
    return mapping


# Any Unicode letter, matching the corpus tokenizer, so "Wallström" is one word
# rather than an ASCII fragment the map could match.
_WORD_RE = re.compile(r"[^\W\d_]+")


def _match_case(original: str, replacement: str) -> str:
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def fold_text(text: str, mapping: Dict[str, str]) -> str:
    """Rewrite every mapped word in ``text``, keeping its capitalization."""
    if not mapping:
        return text

    def replace(match: "re.Match[str]") -> str:
        original = match.group(0)
        target = mapping.get(original.lower())
        return _match_case(original, target) if target else original

    return _WORD_RE.sub(replace, text)


def vocabulary(texts: Iterable[str]) -> set[str]:
    """Every alphabetic word in ``texts``, lowercased."""
    words: set[str] = set()
    for text in texts:
        words.update(match.lower() for match in _WORD_RE.findall(text))
    return words
