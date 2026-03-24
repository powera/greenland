"""English grammatical/function-word data.

Words are split into two tiers:

* **grammatical_only** – pure grammar that should never be linked to a lemma
  (articles, personal pronouns, auxiliary verbs, contractions).
* **also_lemma** – function words that *also* appear (or could appear) as
  teachable lemma entries in data/release (conjunctions, prepositions,
  interrogative pronouns, determiners other than articles).

The legacy ``ENGLISH_GRAMMATICAL_WORDS_BY_CATEGORY`` dict and the broad
``ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS`` frozenset are kept for
backward compatibility with ``util/stopwords.py`` and ``dramblys``.
"""

from typing import Final

# ── tier 1: always grammatical, never a lemma ──────────────────────────

ENGLISH_GRAMMATICAL_ONLY_BY_CATEGORY: Final[dict[str, list[str]]] = {
    "personal_pronouns": [
        "I",
        "me",
        "my",
        "myself",
        "mine",
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
    ],
    "articles": [
        "a",
        "an",
        "the",
    ],
    "auxiliary_verbs": [
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
        "can",
        "could",
    ],
}

ENGLISH_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
    word.lower() for words in ENGLISH_GRAMMATICAL_ONLY_BY_CATEGORY.values() for word in words
)

# ── tier 2: function words that are (or could be) lemmas ───────────────

ENGLISH_ALSO_LEMMA_BY_CATEGORY: Final[dict[str, list[str]]] = {
    "interrogative_pronouns": [
        "who",
        "whom",
        "whose",
        "which",
        "what",
        "that",
    ],
    "prepositions": [
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
    ],
    "conjunctions": [
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
    ],
    "determiners": [
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
    ],
}

ENGLISH_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
    word.lower() for words in ENGLISH_ALSO_LEMMA_BY_CATEGORY.values() for word in words
)

# ── contractions (always grammatical) ──────────────────────────────────

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

ENGLISH_GRAMMATICAL_ONLY_WITH_CONTRACTIONS: Final[frozenset[str]] = frozenset(
    ENGLISH_GRAMMATICAL_ONLY | {word.lower() for word in ENGLISH_GRAMMATICAL_CONTRACTIONS}
)

# ── backward-compatible broad sets ─────────────────────────────────────

ENGLISH_GRAMMATICAL_WORDS_BY_CATEGORY: Final[dict[str, list[str]]] = {
    "pronouns": (
        ENGLISH_GRAMMATICAL_ONLY_BY_CATEGORY["personal_pronouns"]
        + ENGLISH_ALSO_LEMMA_BY_CATEGORY["interrogative_pronouns"]
    ),
    "auxiliary_verbs": ENGLISH_GRAMMATICAL_ONLY_BY_CATEGORY["auxiliary_verbs"],
    "prepositions": ENGLISH_ALSO_LEMMA_BY_CATEGORY["prepositions"],
    "conjunctions": ENGLISH_ALSO_LEMMA_BY_CATEGORY["conjunctions"],
    "determiners": (
        ENGLISH_GRAMMATICAL_ONLY_BY_CATEGORY["articles"]
        + ENGLISH_ALSO_LEMMA_BY_CATEGORY["determiners"]
    ),
}

ENGLISH_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    ENGLISH_GRAMMATICAL_ONLY | ENGLISH_ALSO_LEMMA
)

ENGLISH_GRAMMATICAL_WORDS_WITH_CONTRACTIONS: Final[frozenset[str]] = frozenset(
    ENGLISH_GRAMMATICAL_WORDS | {word.lower() for word in ENGLISH_GRAMMATICAL_CONTRACTIONS}
)
