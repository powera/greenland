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

ENGLISH_GRAMMATICAL_CONTRACTIONS: Final[list[str]] = [
    "don't",
    "doesn't",
    "didn't",
    "can't",
    "couldn't",
    "won't",
    "wouldn't",
    "isn't",
    "aren't",
    "wasn't",
    "weren't",
    "haven't",
    "hasn't",
    "hadn't",
    "I'm",
    "I'll",
    "I've",
    "I'd",
    "you're",
    "you'll",
    "you've",
    "he's",
    "she's",
    "it's",
    "we're",
    "we've",
    "they're",
    "what's",
    "where's",
    "who's",
    "that's",
    "there's",
    "here's",
    "let's",
    "that'll",
    "ain't",
]

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
