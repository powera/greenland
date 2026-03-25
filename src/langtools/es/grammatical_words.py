"""Spanish grammatical/function-word data.

Four tiers:

1. **personal_pronouns** – yo, tú, él, me, te, se, mi, tu, su, …
2. **grammatical_words** – articles (el, la, un, …), contracted (al, del)
3. **function_words** – prepositions (a, con, de, …), conjunctions (y)
4. **non_personal_pronouns** – interrogatives and demonstratives (qué, este, …)

Tiers 1–2 have no analogues in data/release; tiers 3–4 do.
"""

from typing import Final

# ── tier 1: personal pronouns ──────────────────────────────────────────

SPANISH_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # Subject pronouns
        "yo",
        "tú",
        "él",
        "ella",
        "usted",
        "nosotros",
        "nosotras",
        "vosotros",
        "vosotras",
        "ellos",
        "ellas",
        "ustedes",
        # Object / reflexive clitics
        "me",
        "te",
        "se",
        "lo",
        "la",
        "le",
        "nos",
        "os",
        "los",
        "las",
        "les",
        # Possessives (unstressed)
        "mi",
        "mis",
        "tu",
        "tus",
        "su",
        "sus",
        "nuestro",
        "nuestra",
        "nuestros",
        "nuestras",
        "vuestro",
        "vuestra",
        "vuestros",
        "vuestras",
        # Possessives (stressed)
        "mío",
        "mía",
        "míos",
        "mías",
        "tuyo",
        "tuya",
        "tuyos",
        "tuyas",
        "suyo",
        "suya",
        "suyos",
        "suyas",
    }
)

# ── tier 2: grammatical words (articles) ──────────────────────────────

SPANISH_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Definite articles
        "el",
        "la",
        "los",
        "las",
        # Indefinite articles
        "un",
        "una",
        "unos",
        "unas",
        # Contracted articles
        "al",
        "del",
    }
)

# ── tier 3: function words (prepositions, conjunctions) ───────────────

SPANISH_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Prepositions
        "a",
        "con",
        "de",
        "en",
        "para",
        "por",
        # Conjunction
        "y",
    }
)

# ── tier 4: non-personal pronouns (interrogatives, demonstratives) ────

SPANISH_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # Interrogatives
        "qué",
        "quién",
        "quiénes",
        "cuál",
        "cuáles",
        "dónde",
        "cuándo",
        "cómo",
        # Demonstratives
        "este",
        "esta",
        "estos",
        "estas",
        "ese",
        "esa",
        "esos",
        "esas",
        "aquel",
        "aquella",
        "aquellos",
        "aquellas",
    }
)

# ── aggregate sets ─────────────────────────────────────────────────────

SPANISH_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
    SPANISH_PERSONAL_PRONOUNS | SPANISH_GRAMMATICAL_WORDS
)

SPANISH_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
    SPANISH_FUNCTION_WORDS | SPANISH_NON_PERSONAL_PRONOUNS
)

SPANISH_ALL_TIERS: Final[frozenset[str]] = frozenset(SPANISH_GRAMMATICAL_ONLY | SPANISH_ALSO_LEMMA)
