"""French grammatical/function-word data.

Four tiers:

1. **personal_pronouns** – je, tu, il, me, se, mon, ma, …
2. **grammatical_words** – articles (le, la, un, du, au, …)
3. **function_words** – prepositions (à, sur), conjunctions (et)
4. **non_personal_pronouns** – interrogatives and demonstratives (qui, ce, …)

Tiers 1–2 have no analogues in data/release; tiers 3–4 do.
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

FRENCH_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # Subject pronouns
        "je",
        "tu",
        "il",
        "elle",
        "on",
        "nous",
        "vous",
        "ils",
        "elles",
        # Object / reflexive clitics
        "me",
        "te",
        "se",
        "le",
        "la",
        "lui",
        "leur",
        "en",
        "y",
        # Possessives
        "mon",
        "ma",
        "mes",
        "ton",
        "ta",
        "tes",
        "son",
        "sa",
        "ses",
        "notre",
        "nos",
        "votre",
        "vos",
        "leur",
        "leurs",
    }
)

# ── tier 2: grammatical words (articles) ──────────────────────────────

FRENCH_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Definite articles
        "le",
        "la",
        "les",
        "l'",
        # Indefinite / partitive articles
        "un",
        "une",
        "du",
        "de",
        "des",
        # Contracted articles
        "au",
        "aux",
    }
)

# ── tier 3: function words (prepositions, conjunctions) ───────────────

FRENCH_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Prepositions
        "à",
        "sur",
        # Conjunction
        "et",
    }
)

# ── tier 4: non-personal pronouns (interrogatives, demonstratives) ────

FRENCH_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # Demonstratives
        "ce",
        "cet",
        "cette",
        "ces",
        # Interrogatives / relatives
        "qui",
        "que",
        "quel",
        "quelle",
        "quels",
        "quelles",
        "où",
    }
)

# ── aggregate sets ─────────────────────────────────────────────────────

FRENCH_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=FRENCH_PERSONAL_PRONOUNS,
        grammatical_words=FRENCH_GRAMMATICAL_WORDS,
        function_words=FRENCH_FUNCTION_WORDS,
        non_personal_pronouns=FRENCH_NON_PERSONAL_PRONOUNS,
        articles=frozenset({"le", "la", "les", "l'", "un", "une", "du", "de", "des"}),
        contractions=frozenset({"au", "aux"}),
        prepositions=frozenset({"à", "sur"}),
        conjunctions=frozenset({"et"}),
        interrogatives=frozenset({"qui", "que", "quel", "quelle", "quels", "quelles", "où"}),
        demonstratives=frozenset({"ce", "cet", "cette", "ces"}),
    )
)

FRENCH_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    FRENCH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

FRENCH_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    FRENCH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

FRENCH_ALL_TIERS: Final[frozenset[str]] = frozenset(FRENCH_GRAMMATICAL_ONLY | FRENCH_ALSO_LEMMA)
