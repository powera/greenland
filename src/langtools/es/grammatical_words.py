"""Spanish grammatical/function-word data.

* **grammatical_only** – articles, personal pronoun clitics, possessives.
* **also_lemma** – prepositions and conjunctions that have data/release entries.
"""

from typing import Final

# ── tier 1: always grammatical, never a lemma ──────────────────────────

SPANISH_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
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
        # Personal pronoun clitics / unstressed pronouns
        "le",
        "les",
        "lo",
        "me",
        "nos",
        "os",
        "se",
        "te",
        # Personal pronouns (subject)
        "yo",
        "tú",
        "él",
        "ella",
        "nosotros",
        "nosotras",
        "vosotros",
        "vosotras",
        "ellos",
        "ellas",
        "usted",
        "ustedes",
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

# ── tier 2: function words that are (or could be) lemmas ───────────────

SPANISH_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
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

# ── backward-compatible broad set ──────────────────────────────────────

SPANISH_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    SPANISH_GRAMMATICAL_ONLY | SPANISH_ALSO_LEMMA
)
