"""Spanish noun gender predicted from the ending.

This is a cross-check, not a source of facts.  Gender is stored as a
``grammatical_gender`` grammar fact decided by the LLM (see
``words.grammar_fact_tasks.grammatical_gender``); the prediction here only
flags an LLM answer that contradicts a reliable ending, so a reviewer can look
at it.

Only endings that are right for nearly every noun are listed.  Anything else
returns ``None`` -- a missing prediction costs nothing, while a wrong one sends
a correct fact to review.

Gender values
-------------

``masculine`` and ``feminine``, plus ``common`` for a noun with a single form
that takes either gender depending on who it refers to: el/la estudiante,
el/la artista, el/la joven, el/la testigo.  ``common`` is not for a pair of
different words (actor/actriz, profesor/profesora): the lemma's translation is
one of those words, and it gets that word's gender.  Nor is it for nouns whose
meaning changes with gender (el capital "money" / la capital "city"); those are
separate senses, each with its own gender.  The ending rule never predicts
``common``.

Regional gender
---------------

A word nearly always has the same gender in Spain and Latin America, which is
why es-419 copies the es fact when both use the same word.  The few that do
not are listed in ``REGIONAL_GENDER_WORDS``; es-419 asks the LLM for those,
and each variety's prompt names the region whose usage to give.
"""

from typing import FrozenSet, List, Optional, Set, Tuple

# The grammatical_gender values a Spanish noun may take; see above.
GENDERS: List[str] = ["masculine", "feminine", "common"]

_BASE_GENDER_SYSTEM_DESCRIPTION = (
    "2-way system (masculine/feminine). Use 'common' only for a noun with a single "
    "form that takes either gender depending on who it refers to (el/la estudiante, "
    "el/la artista, el/la joven). Do not use 'common' when there are separate "
    "masculine and feminine words (actor/actriz, profesor/profesora): give the "
    "gender of the word provided."
)

# Gender-system descriptions given to the LLM (see prompts/grammar/gender), one
# per stored variety.
GENDER_SYSTEM_DESCRIPTION_SPAIN = (
    f"{_BASE_GENDER_SYSTEM_DESCRIPTION} Answer for Peninsular Spanish (Spain): where "
    "a word's gender differs by region, give the gender used in Spain (la radio)."
)
GENDER_SYSTEM_DESCRIPTION_LATIN_AMERICA = (
    f"{_BASE_GENDER_SYSTEM_DESCRIPTION} Answer for neutral Latin American Spanish: "
    "where a word's gender differs by region, give the gender most widely used in "
    "Latin America, not Spain's (el radio for the device)."
)

# Words whose gender differs between Spain and Latin America, so es-419 must
# not copy es's fact for them.
REGIONAL_GENDER_WORDS: FrozenSet[str] = frozenset(
    {
        "radio",  # la radio (Spain) / el radio (most of Latin America)
        "sartén",  # la sartén / el sartén
        "sauna",  # la sauna / el sauna (Southern Cone)
        "pijama",  # el pijama / la pijama (Mexico)
        "piyama",
        "bikini",  # el bikini / la bikini (Argentina)
        "biquini",
        "lente",  # las lentes / los lentes (glasses)
        "lentes",
    }
)


def has_regional_gender(noun: str) -> bool:
    """Return True if *noun*'s gender may differ between Spain and Latin America."""
    return noun.strip().lower() in REGIONAL_GENDER_WORDS


# Feminine suffixes with essentially no exceptions among common nouns.
_FEMININE_ENDINGS: Tuple[str, ...] = ("ción", "sión", "dad", "tad", "tud", "umbre", "itis")

# Masculine suffixes, each with a short exception list below.
_MASCULINE_ENDINGS: Tuple[str, ...] = ("aje", "or", "o")

# -o nouns that are feminine (mostly clipped forms: la foto(grafía)).  "radio"
# is in REGIONAL_GENDER_WORDS instead: el radio is also radius and radium.
_FEMININE_O: Set[str] = {"mano", "foto", "moto", "libido", "seo", "dinamo", "nao"}

# -or nouns that are feminine.
_FEMININE_OR: Set[str] = {"flor", "labor", "coliflor", "sor"}

# -a nouns that are masculine.  -ma (el problema, but la cama) and -ista
# (el/la artista) are left out of the -a rule altogether.
_MASCULINE_A: Set[str] = {
    "día",
    "mapa",
    "planeta",
    "cometa",
    "poeta",
    "atleta",
    "tranvía",
    "papa",
    "profeta",
    "pirata",
    "guardia",
    "policía",
}


def _head_noun(noun: str) -> Optional[str]:
    """Return the head of *noun*: the first word, since Spanish is head-first.

    Capitalised input (a proper noun or brand, "Keytruda") has no predictable
    gender and returns ``None``.
    """
    text = noun.strip()
    if not text or text[0].isupper():
        return None
    head = text.split()[0]
    return head if head.isalpha() else None


def predict_gender(noun: str) -> Optional[str]:
    """Return ``"masculine"`` or ``"feminine"`` for a reliable ending, else ``None``."""
    head = _head_noun(noun)
    if head is None or has_regional_gender(head):
        return None

    if head.endswith(_FEMININE_ENDINGS):
        return "feminine"

    if head.endswith(_MASCULINE_ENDINGS):
        if head in _FEMININE_O or head in _FEMININE_OR:
            return "feminine"
        return "masculine"

    if head.endswith("a") and not head.endswith(("ma", "ista")):
        if head in _MASCULINE_A:
            return "masculine"
        return "feminine"

    return None
