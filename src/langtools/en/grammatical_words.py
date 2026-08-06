"""English grammatical/function-word data.

Four tiers, from most grammatical to most lemma-like:

1. **personal_pronouns** – I, me, my, he, she, … (not in data/release)
2. **grammatical_words** – articles, auxiliaries, contractions (not in data/release)
3. **function_words** – conjunctions, prepositions (in data/release)
4. **non_personal_pronouns** – who, this, that, each, … (in data/release)

Tiers 1–2 have no analogues in data/release; tiers 3–4 do.

Legacy exports (``ENGLISH_GRAMMATICAL_WORDS_BY_CATEGORY``,
``ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS``) are kept for backward
compatibility with ``util/stopwords.py`` and ``dramblys``.
"""

from typing import Final

from langtools.grammatical_word_schema import (
    ALSO_LEMMA_SUBCATEGORIES,
    GRAMMATICAL_ONLY_SUBCATEGORIES,
    ContractionAnnotation,
    GrammaticalSubcategory,
    GrammaticalWordsBySubcategory,
    build_subcategory_mapping,
    union_subcategories,
)

# ── tier 1: personal pronouns ──────────────────────────────────────────

ENGLISH_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    w.lower()
    for w in [
        "I",
        "me",
        "my",
        "mine",
        "myself",
        "we",
        "us",
        "our",
        "ours",
        "ourselves",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "he",
        "him",
        "his",
        "himself",
        "she",
        "her",
        "hers",
        "herself",
        "it",
        "its",
        "itself",
        "they",
        "them",
        "their",
        "theirs",
        "themselves",
    ]
)

# ── tier 2: grammatical words (articles, auxiliaries, contractions) ────

ENGLISH_ARTICLES: Final[list[str]] = [
    "a",
    "an",
    "the",
]

ENGLISH_AUXILIARY_VERBS: Final[list[str]] = [
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "shall",
    "will",
    "should",
    "would",
    "may",
    "might",
    "must",
    "ought",
    "can",
    "cannot",
    "could",
]

# Contractions, with the part of speech of the leading word and the expanded
# form. The expansion is display data: consumers that annotate English text
# (e.g. the atacama export) surface it in a tooltip, and it is the reason this
# is a mapping rather than the flat list it used to be. "pos" is "verb" for the
# auxiliary/negation forms and "pronoun" for the pronoun-led ones.
ENGLISH_CONTRACTION_ANNOTATIONS: Final[dict[str, ContractionAnnotation]] = {
    # Negations (auxiliary verb + not)
    "don't": ContractionAnnotation(pos="verb", expansion="do not"),
    "doesn't": ContractionAnnotation(pos="verb", expansion="does not"),
    "didn't": ContractionAnnotation(pos="verb", expansion="did not"),
    "isn't": ContractionAnnotation(pos="verb", expansion="is not"),
    "aren't": ContractionAnnotation(pos="verb", expansion="are not"),
    "wasn't": ContractionAnnotation(pos="verb", expansion="was not"),
    "weren't": ContractionAnnotation(pos="verb", expansion="were not"),
    "haven't": ContractionAnnotation(pos="verb", expansion="have not"),
    "hasn't": ContractionAnnotation(pos="verb", expansion="has not"),
    "hadn't": ContractionAnnotation(pos="verb", expansion="had not"),
    "can't": ContractionAnnotation(pos="verb", expansion="cannot"),
    "couldn't": ContractionAnnotation(pos="verb", expansion="could not"),
    "won't": ContractionAnnotation(pos="verb", expansion="will not"),
    "wouldn't": ContractionAnnotation(pos="verb", expansion="would not"),
    "shouldn't": ContractionAnnotation(pos="verb", expansion="should not"),
    "mustn't": ContractionAnnotation(pos="verb", expansion="must not"),
    "mightn't": ContractionAnnotation(pos="verb", expansion="might not"),
    "needn't": ContractionAnnotation(pos="verb", expansion="need not"),
    "shan't": ContractionAnnotation(pos="verb", expansion="shall not"),
    "ain't": ContractionAnnotation(pos="verb", expansion="am not"),
    # Pronoun + "am"
    "i'm": ContractionAnnotation(pos="pronoun", expansion="I am"),
    # Pronoun + "are"
    "you're": ContractionAnnotation(pos="pronoun", expansion="you are"),
    "we're": ContractionAnnotation(pos="pronoun", expansion="we are"),
    "they're": ContractionAnnotation(pos="pronoun", expansion="they are"),
    # Pronoun + "is"/"has"
    "he's": ContractionAnnotation(pos="pronoun", expansion="he is"),
    "she's": ContractionAnnotation(pos="pronoun", expansion="she is"),
    "it's": ContractionAnnotation(pos="pronoun", expansion="it is"),
    "that's": ContractionAnnotation(pos="pronoun", expansion="that is"),
    "there's": ContractionAnnotation(pos="pronoun", expansion="there is"),
    "here's": ContractionAnnotation(pos="pronoun", expansion="here is"),
    "what's": ContractionAnnotation(pos="pronoun", expansion="what is"),
    "who's": ContractionAnnotation(pos="pronoun", expansion="who is"),
    "where's": ContractionAnnotation(pos="pronoun", expansion="where is"),
    "how's": ContractionAnnotation(pos="pronoun", expansion="how is"),
    "let's": ContractionAnnotation(pos="pronoun", expansion="let us"),
    # Pronoun + "have"
    "i've": ContractionAnnotation(pos="pronoun", expansion="I have"),
    "you've": ContractionAnnotation(pos="pronoun", expansion="you have"),
    "we've": ContractionAnnotation(pos="pronoun", expansion="we have"),
    "they've": ContractionAnnotation(pos="pronoun", expansion="they have"),
    # Pronoun + "will"
    "i'll": ContractionAnnotation(pos="pronoun", expansion="I will"),
    "you'll": ContractionAnnotation(pos="pronoun", expansion="you will"),
    "he'll": ContractionAnnotation(pos="pronoun", expansion="he will"),
    "she'll": ContractionAnnotation(pos="pronoun", expansion="she will"),
    "we'll": ContractionAnnotation(pos="pronoun", expansion="we will"),
    "they'll": ContractionAnnotation(pos="pronoun", expansion="they will"),
    "it'll": ContractionAnnotation(pos="pronoun", expansion="it will"),
    "that'll": ContractionAnnotation(pos="pronoun", expansion="that will"),
    # Pronoun + "would"/"had"
    "i'd": ContractionAnnotation(pos="pronoun", expansion="I would"),
    "you'd": ContractionAnnotation(pos="pronoun", expansion="you would"),
    "he'd": ContractionAnnotation(pos="pronoun", expansion="he would"),
    "she'd": ContractionAnnotation(pos="pronoun", expansion="she would"),
    "we'd": ContractionAnnotation(pos="pronoun", expansion="we would"),
    "they'd": ContractionAnnotation(pos="pronoun", expansion="they would"),
}

# Surface forms only. Kept as a list for the callers that just need membership
# (util/stopwords.py, dramblys); keys are already lowercase.
ENGLISH_GRAMMATICAL_CONTRACTIONS: Final[list[str]] = list(ENGLISH_CONTRACTION_ANNOTATIONS)

# Negators. These are particles rather than a category of their own: English
# spreads negation across several parts of speech ("not" adverbial, "no"
# determiner, "neither" correlative), so no single POS covers them and none is
# a teachable lemma. Listing them here keeps them out of lemma lookup, which
# otherwise matches "not" against the interjection "no".
ENGLISH_PARTICLES: Final[list[str]] = [
    "not",
    "n't",
    "never",
    "no",
    "nor",
    "neither",
]

ENGLISH_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    [w.lower() for w in ENGLISH_ARTICLES]
    + [w.lower() for w in ENGLISH_AUXILIARY_VERBS]
    + [w.lower() for w in ENGLISH_GRAMMATICAL_CONTRACTIONS]
    + [w.lower() for w in ENGLISH_PARTICLES]
)

# ── tier 3: function words (conjunctions, prepositions) ───────────────

ENGLISH_PREPOSITIONS: Final[list[str]] = [
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "off",
    "on",
    "onto",
    "out",
    "over",
    "to",
    "under",
    "up",
    "with",
    "about",
    "above",
    "after",
    "before",
    "between",
    "during",
    "through",
    "upon",
    "without",
]

ENGLISH_CONJUNCTIONS: Final[list[str]] = [
    "and",
    "but",
    "if",
    "or",
    "because",
    "as",
    "until",
    "while",
    "though",
    "so",
    "than",
    "since",
    "till",
    "nor",
]

ENGLISH_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    [w.lower() for w in ENGLISH_PREPOSITIONS] + [w.lower() for w in ENGLISH_CONJUNCTIONS]
)

# ── tier 4: non-personal pronouns / determiners ───────────────────────

ENGLISH_INTERROGATIVE_PRONOUNS: Final[list[str]] = [
    "who",
    "whom",
    "whose",
    "which",
    "what",
    "that",
]

ENGLISH_DETERMINERS: Final[list[str]] = [
    "this",
    "that",
    "these",
    "those",
    "some",
    "all",
    "any",
    "every",
    "no",
    "such",
    "another",
    "each",
    "either",
    "neither",
]

ENGLISH_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    [w.lower() for w in ENGLISH_INTERROGATIVE_PRONOUNS] + [w.lower() for w in ENGLISH_DETERMINERS]
)

# ── aggregate sets ─────────────────────────────────────────────────────

ENGLISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=ENGLISH_PERSONAL_PRONOUNS,
        grammatical_words=ENGLISH_GRAMMATICAL_WORDS,
        function_words=ENGLISH_FUNCTION_WORDS,
        non_personal_pronouns=ENGLISH_NON_PERSONAL_PRONOUNS,
        articles=frozenset(word.lower() for word in ENGLISH_ARTICLES),
        auxiliaries=frozenset(word.lower() for word in ENGLISH_AUXILIARY_VERBS),
        particles=frozenset(word.lower() for word in ENGLISH_PARTICLES),
        contractions=frozenset(word.lower() for word in ENGLISH_GRAMMATICAL_CONTRACTIONS),
        prepositions=frozenset(word.lower() for word in ENGLISH_PREPOSITIONS),
        conjunctions=frozenset(word.lower() for word in ENGLISH_CONJUNCTIONS),
        determiners=frozenset(word.lower() for word in ENGLISH_DETERMINERS),
        interrogatives=frozenset(word.lower() for word in ENGLISH_INTERROGATIVE_PRONOUNS),
        demonstratives=frozenset({"this", "that", "these", "those"}),
    )
)

# Tiers 1+2: linker skips these (not in data/release)
ENGLISH_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    ENGLISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

# Tiers 3+4: linker should resolve these (in data/release)
ENGLISH_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    ENGLISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

# All four tiers combined
ENGLISH_ALL_TIERS: Final[frozenset[str]] = frozenset(ENGLISH_GRAMMATICAL_ONLY | ENGLISH_ALSO_LEMMA)

# ── backward-compatible exports ────────────────────────────────────────

ENGLISH_GRAMMATICAL_ONLY_WITH_CONTRACTIONS: Final[frozenset[str]] = ENGLISH_GRAMMATICAL_ONLY

ENGLISH_GRAMMATICAL_WORDS_BY_CATEGORY: Final[dict[str, list[str]]] = {
    "pronouns": (sorted(ENGLISH_PERSONAL_PRONOUNS) + ENGLISH_INTERROGATIVE_PRONOUNS),
    "auxiliary_verbs": ENGLISH_AUXILIARY_VERBS,
    "prepositions": ENGLISH_PREPOSITIONS,
    "conjunctions": ENGLISH_CONJUNCTIONS,
    "determiners": ENGLISH_ARTICLES + ENGLISH_DETERMINERS,
}

ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS: Final[frozenset[str]] = ENGLISH_ALL_TIERS

# ── stopword annotations ───────────────────────────────────────────────

# Part of speech to report for each subcategory. Iteration order resolves words
# that belong to more than one: "that" is a determiner before an interrogative,
# and "no"/"nor"/"neither" are particles before determiners/conjunctions.
# "demonstratives" is absent because its members are all determiners already.
_SUBCATEGORY_POS: Final[tuple[tuple[GrammaticalSubcategory, str], ...]] = (
    ("personal_pronouns", "pronoun"),
    ("articles", "article"),
    ("auxiliaries", "auxiliary_verb"),
    ("particles", "particle"),
    ("prepositions", "preposition"),
    ("conjunctions", "conjunction"),
    ("determiners", "determiner"),
    ("interrogatives", "pronoun"),
)

# Inflected forms grouped under a single display headword. Only forms whose
# headword differs from the word itself are listed; everything else maps to
# itself. Migrated from data/release/stopwords/en.jsonl, which was the export's
# hand-maintained input before this module became the source of truth.
_DISPLAY_HEADWORDS: Final[dict[str, str]] = {
    # personal pronouns, grouped by person
    "me": "I",
    "my": "I",
    "mine": "I",
    "myself": "I",
    "us": "we",
    "our": "we",
    "ours": "we",
    "ourselves": "we",
    "your": "you",
    "yours": "you",
    "yourself": "you",
    "yourselves": "you",
    "him": "he",
    "his": "he",
    "himself": "he",
    "her": "she",
    "hers": "she",
    "herself": "she",
    "its": "it",
    "itself": "it",
    "them": "they",
    "their": "they",
    "theirs": "they",
    "themselves": "they",
    # articles
    "an": "a",
    # auxiliaries, grouped by paradigm
    "am": "be",
    "is": "be",
    "are": "be",
    "was": "be",
    "were": "be",
    "been": "be",
    "being": "be",
    "has": "have",
    "had": "have",
    "does": "do",
    "did": "do",
    "would": "will",
    "should": "shall",
    "could": "can",
    "cannot": "can",
    "might": "may",
}


def _build_stopword_annotations() -> dict[str, dict[str, str]]:
    """Build the {word: {pos, lemma}} table for every English grammatical word.

    Covers all four tiers plus contractions, so any word the registry knows is
    annotatable. "lemma" is a display headword, not a link to the Lemma table:
    these words have no GUID and never resolve to a lemma entry.
    """
    annotations: dict[str, dict[str, str]] = {}

    for subcategory, pos in _SUBCATEGORY_POS:
        for word in sorted(ENGLISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY.get(subcategory, ())):
            annotations.setdefault(word, {"pos": pos, "lemma": _DISPLAY_HEADWORDS.get(word, word)})

    for word, annotation in ENGLISH_CONTRACTION_ANNOTATIONS.items():
        annotations[word] = {"pos": annotation.pos, "lemma": annotation.expansion}

    return annotations


ENGLISH_STOPWORD_ANNOTATIONS: Final[dict[str, dict[str, str]]] = _build_stopword_annotations()
