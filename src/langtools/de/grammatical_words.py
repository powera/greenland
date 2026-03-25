"""German grammatical/function-word data.

Four tiers:

1. **personal_pronouns** – ich, du, er, sie, … + possessive determiners
2. **grammatical_words** – articles, contracted forms, kein-forms,
   auxiliaries, modals, particles, indefinite pronouns (man, jemand, …)
3. **function_words** – prepositions, conjunctions
4. **non_personal_pronouns** – interrogatives (wer, was, …),
   demonstratives (dieser, jener, …), indefinite determiners (jeder, alle, …)

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

GERMAN_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # Personal pronouns (all cases)
        "ich",
        "du",
        "er",
        "sie",
        "es",
        "wir",
        "ihr",
        "mich",
        "dich",
        "sich",
        "uns",
        "euch",
        "mir",
        "dir",
        "ihm",
        "ihnen",
        # Possessive determiners (all inflected forms)
        "mein",
        "meine",
        "meinen",
        "meinem",
        "meiner",
        "meines",
        "dein",
        "deine",
        "deinen",
        "deinem",
        "deiner",
        "deines",
        "sein",
        "seine",
        "seinen",
        "seinem",
        "seiner",
        "seines",
        "ihr",
        "ihre",
        "ihren",
        "ihrem",
        "ihrer",
        "ihres",
        "unser",
        "unsere",
        "unseren",
        "unserem",
        "unserer",
        "unseres",
        "euer",
        "eure",
        "euren",
        "eurem",
        "eurer",
        "eures",
    }
)

# ── tier 2: grammatical words ─────────────────────────────────────────

GERMAN_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Definite articles (all cases / genders)
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        # Indefinite articles (all cases / genders)
        "ein",
        "eine",
        "einen",
        "einem",
        "einer",
        "eines",
        # Contracted preposition + article forms
        "am",
        "ans",
        "aufs",
        "beim",
        "im",
        "ins",
        "vom",
        "zum",
        "zur",
        # Negation
        "nicht",
        "kein",
        "keine",
        "keinen",
        "keinem",
        "keiner",
        "keines",
        # Particles
        "noch",
        "schon",
        "ja",
        "nein",
        "doch",
        "nur",
        "auch",
        "mal",
        "eben",
        "halt",
        "wohl",
        "bloß",
        "etwa",
        # Indefinite pronouns (not teachable as lemmas)
        "man",
        "jemand",
        "niemand",
        "etwas",
        "nichts",
        # Auxiliary verbs — sein
        "bin",
        "bist",
        "ist",
        "sind",
        "seid",
        "war",
        "warst",
        "waren",
        "wart",
        # Auxiliary verbs — haben
        "habe",
        "hast",
        "hat",
        "haben",
        "habt",
        "hatte",
        "hatten",
        # Auxiliary verbs — werden
        "werde",
        "wirst",
        "wird",
        "werden",
        "werdet",
        "wurde",
        "wurden",
        # Modal verbs — können
        "kann",
        "kannst",
        "können",
        "könnt",
        "konnte",
        "konnten",
        # Modal verbs — dürfen
        "darf",
        "darfst",
        "dürfen",
        "dürft",
        "durfte",
        "durften",
        # Modal verbs — müssen
        "muss",
        "musst",
        "müssen",
        "müsst",
        "musste",
        "mussten",
        # Modal verbs — sollen
        "soll",
        "sollst",
        "sollen",
        "sollt",
        "sollte",
        "sollten",
        # Modal verbs — wollen
        "will",
        "willst",
        "wollen",
        "wollt",
        "wollte",
        "wollten",
        # Modal verbs — mögen
        "mag",
        "magst",
        "mögen",
        "mögt",
        "mochte",
        "mochten",
        "möchte",
        "möchten",
    }
)

# ── tier 3: function words (prepositions, conjunctions) ───────────────

GERMAN_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Prepositions
        "an",
        "auf",
        "aus",
        "bei",
        "bis",
        "durch",
        "für",
        "gegen",
        "hinter",
        "in",
        "mit",
        "nach",
        "neben",
        "ohne",
        "über",
        "um",
        "unter",
        "von",
        "vor",
        "zu",
        "zwischen",
        "ab",
        "außer",
        "seit",
        "statt",
        "trotz",
        "wegen",
        "während",
        "gegenüber",
        # Conjunctions
        "und",
        "oder",
        "aber",
        "denn",
        "sondern",
        "weil",
        "wenn",
        "dass",
        "ob",
        "als",
        "obwohl",
        "damit",
        "falls",
        "bevor",
        "nachdem",
        "seitdem",
        "sobald",
        "solange",
        "indem",
        "weder",
        "sowohl",
    }
)

# ── tier 4: non-personal pronouns ─────────────────────────────────────

GERMAN_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # Interrogative pronouns
        "wer",
        "wen",
        "wem",
        "wessen",
        "was",
        "wo",
        "wann",
        "warum",
        "wie",
        "welcher",
        "welche",
        "welches",
        "welchen",
        "welchem",
        # Demonstrative determiners
        "dieser",
        "diese",
        "dieses",
        "diesen",
        "diesem",
        "jener",
        "jene",
        "jenes",
        "jenen",
        "jenem",
        # Indefinite determiners
        "jeder",
        "jede",
        "jedes",
        "jeden",
        "jedem",
        "alle",
        "alles",
        "einige",
        "manche",
    }
)

# ── aggregate sets ─────────────────────────────────────────────────────

GERMAN_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=GERMAN_PERSONAL_PRONOUNS,
        grammatical_words=GERMAN_GRAMMATICAL_WORDS,
        function_words=GERMAN_FUNCTION_WORDS,
        non_personal_pronouns=GERMAN_NON_PERSONAL_PRONOUNS,
        articles=frozenset(
            {
                "der",
                "die",
                "das",
                "den",
                "dem",
                "des",
                "ein",
                "eine",
                "einen",
                "einem",
                "einer",
                "eines",
            }
        ),
        auxiliaries=frozenset(
            {
                "bin",
                "bist",
                "ist",
                "sind",
                "seid",
                "war",
                "waren",
                "habe",
                "hast",
                "hat",
                "haben",
                "habt",
                "werde",
                "wirst",
                "wird",
                "werden",
                "werdet",
                "wurde",
                "wurden",
            }
        ),
        contractions=frozenset({"am", "ans", "aufs", "beim", "im", "ins", "vom", "zum", "zur"}),
        prepositions=frozenset(
            {
                "an",
                "auf",
                "aus",
                "bei",
                "bis",
                "durch",
                "für",
                "gegen",
                "in",
                "mit",
                "nach",
                "ohne",
                "über",
                "um",
                "unter",
                "von",
                "vor",
                "zu",
                "zwischen",
            }
        ),
        interrogatives=frozenset(
            {
                "wer",
                "wen",
                "wem",
                "wessen",
                "was",
                "wo",
                "wann",
                "warum",
                "wie",
                "welcher",
                "welche",
                "welches",
            }
        ),
        demonstratives=frozenset(
            {
                "dieser",
                "diese",
                "dieses",
                "diesen",
                "diesem",
                "jener",
                "jene",
                "jenes",
                "jenen",
                "jenem",
            }
        ),
    )
)

GERMAN_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    GERMAN_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

GERMAN_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    GERMAN_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

GERMAN_ALL_TIERS: Final[frozenset[str]] = frozenset(GERMAN_GRAMMATICAL_ONLY | GERMAN_ALSO_LEMMA)
