"""Rule-based French adjective and noun inflection helpers.

French adjectives agree with their noun in gender and number.  This module
handles a table of common irregular adjectives plus the regular endings whose
feminine is predictable (-e, -eux, -er, -f, -al, -el, -en, -on, -et, -ot, -in,
-ais/-ois/-is/-us, vowels, -t, -d, -r, -l).  Endings whose feminine varies
(-teur: conservatrice but menteuse; -c, -g, -x) return ``None`` unless the word
is in the table, so the caller can fall back to the LLM.

Five adjectives also have a masculine singular used before a vowel or mute h
(``un bel homme``, ``un nouvel an``, ``un vieil ami``); those fill the
``singular_m_prevocalic`` slot, and every other adjective leaves it out.
Prepositional phrases standing in for an adjective (``en bois``, ``à pois``)
do not agree at all and repeat one form in every slot.

Noun plurals are regular apart from a few closed lists (-al/-aux,
-ail/-aux, -ou/-oux, -eu/-eux) and a handful of suppletive words.
"""

from typing import Dict, Optional, Set


def _table(singular_m: str, singular_f: str, plural_m: str, plural_f: str) -> Dict[str, str]:
    return {
        "singular_m": singular_m,
        "singular_f": singular_f,
        "plural_m": plural_m,
        "plural_f": plural_f,
    }


# Masculine singular → full agreement table for irregular adjectives.
_IRREGULAR: Dict[str, Dict[str, str]] = {
    "beau": _table("beau", "belle", "beaux", "belles"),
    "nouveau": _table("nouveau", "nouvelle", "nouveaux", "nouvelles"),
    "vieux": _table("vieux", "vieille", "vieux", "vieilles"),
    "fou": _table("fou", "folle", "fous", "folles"),
    "mou": _table("mou", "molle", "mous", "molles"),
    "blanc": _table("blanc", "blanche", "blancs", "blanches"),
    "franc": _table("franc", "franche", "francs", "franches"),
    "sec": _table("sec", "sèche", "secs", "sèches"),
    "grec": _table("grec", "grecque", "grecs", "grecques"),
    "turc": _table("turc", "turque", "turcs", "turques"),
    "public": _table("public", "publique", "publics", "publiques"),
    "caduc": _table("caduc", "caduque", "caducs", "caduques"),
    "doux": _table("doux", "douce", "doux", "douces"),
    "faux": _table("faux", "fausse", "faux", "fausses"),
    "roux": _table("roux", "rousse", "roux", "rousses"),
    "jaloux": _table("jaloux", "jalouse", "jaloux", "jalouses"),
    "long": _table("long", "longue", "longs", "longues"),
    "frais": _table("frais", "fraîche", "frais", "fraîches"),
    "favori": _table("favori", "favorite", "favoris", "favorites"),
    "gentil": _table("gentil", "gentille", "gentils", "gentilles"),
    "gros": _table("gros", "grosse", "gros", "grosses"),
    "gras": _table("gras", "grasse", "gras", "grasses"),
    "bas": _table("bas", "basse", "bas", "basses"),
    "las": _table("las", "lasse", "las", "lasses"),
    "épais": _table("épais", "épaisse", "épais", "épaisses"),
    "exprès": _table("exprès", "expresse", "exprès", "expresses"),
    "tiers": _table("tiers", "tierce", "tiers", "tierces"),
    "bon": _table("bon", "bonne", "bons", "bonnes"),
    "bref": _table("bref", "brève", "brefs", "brèves"),
    "malin": _table("malin", "maligne", "malins", "malignes"),
    "bénin": _table("bénin", "bénigne", "bénins", "bénignes"),
    "aigu": _table("aigu", "aiguë", "aigus", "aiguës"),
    "ambigu": _table("ambigu", "ambiguë", "ambigus", "ambiguës"),
    "contigu": _table("contigu", "contiguë", "contigus", "contiguës"),
    "andalou": _table("andalou", "andalouse", "andalous", "andalouses"),
    "hébreu": _table("hébreu", "hébraïque", "hébreux", "hébraïques"),
    "final": _table("final", "finale", "finaux", "finales"),
    "dû": _table("dû", "due", "dus", "dues"),
}

# Masculine singular used before a vowel or mute h.
_PREVOCALIC: Dict[str, str] = {
    "beau": "bel",
    "nouveau": "nouvel",
    "vieux": "vieil",
    "fou": "fol",
    "mou": "mol",
}

# -al adjectives whose masculine plural is -als rather than -aux.
_AL_PLURAL_S: Set[str] = {"banal", "bancal", "fatal", "natal", "naval", "glacial", "tonal"}

# -et adjectives with a feminine in -ète rather than -ette.
_ET_GRAVE: Set[str] = {"complet", "incomplet", "concret", "discret", "indiscret", "inquiet"}
_ET_GRAVE.update({"replet", "secret"})

# -ot adjectives that double the t (sotte); the rest just add -e (idiote).
_OT_DOUBLE: Set[str] = {"sot", "vieillot", "pâlot", "maigriot", "boulot"}

# -eur adjectives that add -e like any regular one (supérieure, meilleure);
# the rest of -eur, apart from -teur, takes -euse (rêveuse, trompeuse).
_EUR_PLUS_E: Set[str] = {"meilleur", "majeur", "mineur"}

_VOWEL_ENDINGS = ("é", "i", "u", "ai", "y")

# A phrase opening with one of these is a prepositional phrase (en bois,
# à pois, sans sucre), which does not agree with its noun.
_PREPOSITIONS: Set[str] = {
    "à",
    "au",
    "aux",
    "avec",
    "de",
    "des",
    "du",
    "en",
    "par",
    "pour",
    "sans",
    "sous",
    "sur",
}


def _plural(singular: str) -> str:
    """Plural of a regular form: +s unless it already ends in -s or -x."""
    if singular.endswith(("s", "x")):
        return singular
    return singular + "s"


def _regular(singular_m: str, singular_f: str) -> Dict[str, str]:
    return _table(singular_m, singular_f, _plural(singular_m), _plural(singular_f))


def _feminine(singular_m: str) -> Optional[str]:
    """Return the feminine singular of a regular adjective, or None."""
    if singular_m.endswith("eux"):
        return singular_m[:-1] + "se"
    if singular_m.endswith("er"):
        return singular_m[:-2] + "ère"
    if singular_m.endswith("f"):
        return singular_m[:-1] + "ve"
    if singular_m.endswith("e"):
        return singular_m
    if singular_m.endswith(("el", "eil", "ul", "en", "on")):
        return singular_m + singular_m[-1] + "e"
    if singular_m.endswith("et"):
        if singular_m in _ET_GRAVE:
            return singular_m[:-2] + "ète"
        return singular_m + "te"
    if singular_m.endswith("ot"):
        return singular_m + ("te" if singular_m in _OT_DOUBLE else "e")
    if singular_m.endswith("eur"):
        if singular_m in _EUR_PLUS_E or singular_m.endswith("érieur"):
            return singular_m + "e"
        if singular_m.endswith("teur"):
            return None
        return singular_m[:-1] + "se"
    if singular_m.endswith(("ais", "ois", "is", "us")):
        return singular_m + "e"
    if singular_m.endswith("eau"):
        # jumeau / jumelle: only beau and nouveau are common, and both are in
        # the irregular table.
        return None
    if singular_m.endswith(_VOWEL_ENDINGS) or singular_m.endswith(
        ("t", "d", "r", "l", "in", "un", "an")
    ):
        return singular_m + "e"
    return None


def _invariant_phrase(phrase: str) -> Optional[Dict[str, str]]:
    """Return the one-form table for a prepositional phrase, else None."""
    words = phrase.split()
    if len(words) < 2:
        return None
    if words[0] not in _PREPOSITIONS and not words[0].startswith(("d'", "d’")):
        return None
    return _table(phrase, phrase, phrase, phrase)


def build_adjective_forms(
    adjective: str, feminine_form: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Build m/f × singular/plural agreement forms from the masculine singular.

    *feminine_form* is the stored ``feminine_form`` grammar fact for an
    adjective the rules get wrong, and replaces the rule's feminine.  Adds the
    prevocalic masculine for the five adjectives that have one.  Returns
    ``None`` when the feminine cannot be derived reliably, leaving those cases
    to the LLM.
    """
    singular_m = adjective.strip().lower()
    if len(singular_m) < 2:
        return None
    if " " in singular_m:
        return _invariant_phrase(singular_m)
    if singular_m.startswith(("d'", "d’")):
        # d'or, d'époque: a prepositional phrase written as one token.
        return _table(singular_m, singular_m, singular_m, singular_m)

    forms: Optional[Dict[str, str]]
    if feminine_form:
        forms = _regular(singular_m, feminine_form.strip())
    elif singular_m in _IRREGULAR:
        forms = dict(_IRREGULAR[singular_m])
    elif singular_m.endswith("al"):
        plural_m = singular_m + "s" if singular_m in _AL_PLURAL_S else singular_m[:-2] + "aux"
        al_feminine = singular_m + "e"
        forms = _table(singular_m, al_feminine, plural_m, al_feminine + "s")
    else:
        derived_feminine = _feminine(singular_m)
        forms = _regular(singular_m, derived_feminine) if derived_feminine else None

    if forms is None:
        return None
    if singular_m in _PREVOCALIC:
        forms["singular_m_prevocalic"] = _PREVOCALIC[singular_m]
    return forms


# --- Nouns -----------------------------------------------------------------

_SUPPLETIVE_PLURALS: Dict[str, str] = {
    "œil": "yeux",
    "ciel": "cieux",
    "aïeul": "aïeux",
    "monsieur": "messieurs",
    "madame": "mesdames",
    "mademoiselle": "mesdemoiselles",
    "bonhomme": "bonshommes",
    "gentilhomme": "gentilshommes",
}

# -al nouns that take -als rather than -aux.
_AL_NOUN_PLURAL_S: Set[str] = {"bal", "carnaval", "chacal", "festival", "récital", "régal", "cal"}

# -ail nouns that take -aux rather than -ails.
_AIL_NOUN_PLURAL_AUX: Set[str] = {
    "bail",
    "corail",
    "émail",
    "soupirail",
    "travail",
    "vitrail",
    "vantail",
}

# -ou nouns that take -oux rather than -ous.
_OU_NOUN_PLURAL_X: Set[str] = {"bijou", "caillou", "chou", "genou", "hibou", "joujou", "pou"}

# -au/-eau/-eu nouns that take -s rather than -x.
_X_NOUN_PLURAL_S: Set[str] = {"pneu", "bleu", "émeu", "landau", "sarrau"}

# Second words that mark a "noun + complement" compound, which pluralises its
# head: pomme de terre -> pommes de terre, machine à laver -> machines à laver.
_COMPLEMENT_LINKS: Set[str] = {"à", "de", "d'", "en"}


def _noun_plural(noun: str) -> str:
    if noun in _SUPPLETIVE_PLURALS:
        return _SUPPLETIVE_PLURALS[noun]
    if noun.endswith(("s", "x", "z")):
        return noun
    if noun.endswith("al"):
        return noun + "s" if noun in _AL_NOUN_PLURAL_S else noun[:-2] + "aux"
    if noun.endswith("ail"):
        return noun[:-3] + "aux" if noun in _AIL_NOUN_PLURAL_AUX else noun + "s"
    if noun.endswith("ou"):
        return noun + ("x" if noun in _OU_NOUN_PLURAL_X else "s")
    if noun.endswith(("au", "eu")):
        return noun + ("s" if noun in _X_NOUN_PLURAL_S else "x")
    return noun + "s"


def build_noun_forms(
    noun: str,
    irregular_plural: Optional[str] = None,
    number_type: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Build the singular and plural of a French noun.

    *irregular_plural* is the stored ``plural`` grammar fact, which wins over
    the rules; *number_type* is the ``number_type`` fact (see the comment in
    the body for how each value fills the slots).  A "noun + de/à
    complement" compound pluralises its head.  Returns ``None`` for capitalised
    words (proper nouns, brands), hyphenated compounds and other multi-word
    phrases.
    """
    singular = noun.strip()
    if not singular or singular[0].isupper() or "-" in singular:
        return None
    # Same convention as langtools.en.inflection: a plurale tantum repeats the
    # word in both slots; uncountable and singulare tantum have no plural.
    if number_type == "plurale_tantum":
        return {"singular": singular, "plural": singular}
    if number_type in ("uncountable", "singulare_tantum"):
        return {"singular": singular}
    if irregular_plural:
        return {"singular": singular, "plural": irregular_plural.strip()}

    words = singular.split()
    if (
        len(words) > 1
        and words[1] not in _COMPLEMENT_LINKS
        and not words[1].startswith(("d'", "d’"))
    ):
        return None
    head_plural = _noun_plural(words[0])
    return {"singular": singular, "plural": " ".join([head_plural, *words[1:]])}
