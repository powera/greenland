"""French grammatical/function-word data.

Four tiers:

1. **personal_pronouns** – je, tu, il, me, se, mon, ma, …
2. **grammatical_words** – articles (le, la, un, du, au, …)
3. **function_words** – prepositions (à, sur), conjunctions (et)
4. **non_personal_pronouns** – interrogatives and demonstratives (qui, ce, …)

Tiers 1–2 have no analogues in data/release; tiers 3–4 do.
"""

from typing import Final

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

FRENCH_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
    FRENCH_PERSONAL_PRONOUNS | FRENCH_GRAMMATICAL_WORDS
)

FRENCH_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
    FRENCH_FUNCTION_WORDS | FRENCH_NON_PERSONAL_PRONOUNS
)

FRENCH_ALL_TIERS: Final[frozenset[str]] = frozenset(FRENCH_GRAMMATICAL_ONLY | FRENCH_ALSO_LEMMA)
