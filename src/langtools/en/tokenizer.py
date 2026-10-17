"""English lemma-matching hooks for :mod:`langtools.tokenizer`.

``split_contractions`` expands English contractions into their words: "i'm" ->
["i", "am"], "don't" -> ["do", "not"], "should've" -> ["should", "have"].  A
contraction is two words in one token, not a word of its own, so it has no
lemma; its meaning is carried by the parts.  French "du" and Spanish "del" are
handled the same way.

The listed contractions come from
:data:`langtools.en.grammatical_words.ENGLISH_CONTRACTION_ANNOTATIONS`, so the
two never disagree.  Anything not listed falls back to the regular clitics
("'ll", "'ve", "'re", "'m", "'d", "n't") attached to any word.

Two clitics are ambiguous, and the expansion gives one reading only: "'s" may
be "is", "has" or (in "let's") "us", and "'d" may be "would" or "had".  For
lemma lookup that is harmless -- both readings are forms of the same few
auxiliaries.  A bare "'s" is split only for the listed pronouns: on a noun
("world's") it is almost always a possessive, which is a form of the noun
rather than a second word.
"""

from typing import Dict, List, Tuple

from langtools.en.grammatical_words import ENGLISH_CONTRACTION_ANNOTATIONS

# The annotation's expansion is display text; "cannot" is one word there but
# two parts here, matching every other "n't" contraction.
_EXPANSION_OVERRIDES: Dict[str, Tuple[str, ...]] = {
    "can't": ("can", "not"),
}

_CONTRACTIONS: Dict[str, Tuple[str, ...]] = {
    surface: _EXPANSION_OVERRIDES.get(surface, tuple(annotation.expansion.lower().split()))
    for surface, annotation in ENGLISH_CONTRACTION_ANNOTATIONS.items()
}

# Regular clitics, tried in order against contractions not listed above
# ("mary'll", "would've", "mightn't").
_CLITICS: Tuple[Tuple[str, str], ...] = (
    ("n't", "not"),
    ("'ll", "will"),
    ("'ve", "have"),
    ("'re", "are"),
    ("'m", "am"),
    ("'d", "would"),
)


def split_contractions(token: str) -> List[str]:
    """Expand an English contraction; return ``[token]`` otherwise.

    *token* arrives lowercased with apostrophes folded to ASCII by
    :func:`langtools.tokenizer.split_contractions`.
    """
    listed = _CONTRACTIONS.get(token)
    if listed is not None:
        return list(listed)
    for clitic, word in _CLITICS:
        stem = token[: -len(clitic)]
        if token.endswith(clitic) and stem.isalpha():
            return [stem, word]
    return [token]
