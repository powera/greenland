"""French grammatical/function-word data.

* **grammatical_only** – articles, possessives, pronoun clitics.
* **also_lemma** – prepositions and conjunctions that have data/release entries.
"""

from typing import Final

# ── tier 1: always grammatical, never a lemma ──────────────────────────

FRENCH_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
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
        # Personal pronouns (subject)
        "je",
        "tu",
        "il",
        "elle",
        "on",
        "nous",
        "vous",
        "ils",
        "elles",
        # Personal pronoun clitics (object / reflexive)
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

# ── tier 2: function words that are (or could be) lemmas ───────────────

FRENCH_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
    {
        # Prepositions
        "à",
        "sur",
        # Conjunction
        "et",
        # Demonstratives (data/release determiners)
        "ce",
        "ces",
    }
)

# ── backward-compatible broad set ──────────────────────────────────────

FRENCH_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    FRENCH_GRAMMATICAL_ONLY | FRENCH_ALSO_LEMMA
)
