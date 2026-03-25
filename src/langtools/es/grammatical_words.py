"""Spanish grammatical/function-word data.

Four tiers:

1. **personal_pronouns** – yo, tú, él, me, te, se, mi, tu, su, …
2. **grammatical_words** – articles (el, la, un, …), contracted (al, del)
3. **function_words** – prepositions (a, con, de, …), conjunctions (y)
4. **non_personal_pronouns** – interrogatives and demonstratives (qué, este, …)

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

SPANISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=SPANISH_PERSONAL_PRONOUNS,
        grammatical_words=SPANISH_GRAMMATICAL_WORDS,
        function_words=SPANISH_FUNCTION_WORDS,
        non_personal_pronouns=SPANISH_NON_PERSONAL_PRONOUNS,
        articles=frozenset({"el", "la", "los", "las", "un", "una", "unos", "unas"}),
        contractions=frozenset({"al", "del"}),
        prepositions=frozenset({"a", "con", "de", "en", "para", "por"}),
        conjunctions=frozenset({"y"}),
        interrogatives=frozenset(
            {"qué", "quién", "quiénes", "cuál", "cuáles", "dónde", "cuándo", "cómo"}
        ),
        demonstratives=frozenset(
            {
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
        ),
    )
)

SPANISH_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    SPANISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

SPANISH_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    SPANISH_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

SPANISH_ALL_TIERS: Final[frozenset[str]] = frozenset(SPANISH_GRAMMATICAL_ONLY | SPANISH_ALSO_LEMMA)
