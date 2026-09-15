"""Rule-based Spanish verb conjugation.

Generates conjugated forms mechanically for regular verbs and common
irregular patterns. Covers indicative (present, preterite, imperfect,
future, conditional), subjunctive present, imperative, and non-finite forms.

Irregular verbs are handled via:
1. Stem-change patterns (e→ie, o→ue, e→i, u→ue) applied to specific tenses
2. Spelling-change rules (c→qu, g→gu, z→c, etc.) to preserve pronunciation
3. Irregular future/conditional stems
4. Fully irregular verb tables for ser, ir, haber, etc.
"""

from typing import Dict, List, Optional, Set, Tuple

from langtools.es.orthography import respell_with_stress, stressed_nucleus, strip_accents

# ---------------------------------------------------------------------------
# Regular endings
# ---------------------------------------------------------------------------

# Each tuple: (yo, tú, él, nosotros, vosotros, ellos)
_AR_PRESENT = ("o", "as", "a", "amos", "áis", "an")
_ER_PRESENT = ("o", "es", "e", "emos", "éis", "en")
_IR_PRESENT = ("o", "es", "e", "imos", "ís", "en")

_AR_PRETERITE = ("é", "aste", "ó", "amos", "asteis", "aron")
_ER_PRETERITE = ("í", "iste", "ió", "imos", "isteis", "ieron")
_IR_PRETERITE = ("í", "iste", "ió", "imos", "isteis", "ieron")

_AR_IMPERFECT = ("aba", "abas", "aba", "ábamos", "abais", "aban")
_ER_IMPERFECT = ("ía", "ías", "ía", "íamos", "íais", "ían")
_IR_IMPERFECT = ("ía", "ías", "ía", "íamos", "íais", "ían")

# Future and conditional use the full infinitive as stem
_FUTURE = ("é", "ás", "á", "emos", "éis", "án")
_CONDITIONAL = ("ía", "ías", "ía", "íamos", "íais", "ían")

_AR_SUBJUNCTIVE_PRESENT = ("e", "es", "e", "emos", "éis", "en")
_ER_SUBJUNCTIVE_PRESENT = ("a", "as", "a", "amos", "áis", "an")
_IR_SUBJUNCTIVE_PRESENT = ("a", "as", "a", "amos", "áis", "an")

REGULAR_ENDINGS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "ar": {
        "present": _AR_PRESENT,
        "preterite": _AR_PRETERITE,
        "imperfect": _AR_IMPERFECT,
        "subjunctive_present": _AR_SUBJUNCTIVE_PRESENT,
    },
    "er": {
        "present": _ER_PRESENT,
        "preterite": _ER_PRETERITE,
        "imperfect": _ER_IMPERFECT,
        "subjunctive_present": _ER_SUBJUNCTIVE_PRESENT,
    },
    "ir": {
        "present": _IR_PRESENT,
        "preterite": _IR_PRETERITE,
        "imperfect": _IR_IMPERFECT,
        "subjunctive_present": _IR_SUBJUNCTIVE_PRESENT,
    },
}

PERSONS = ("1s", "2s", "3s", "1p", "2p", "3p")

# ---------------------------------------------------------------------------
# Stem-changing verbs
# ---------------------------------------------------------------------------

# Which person indices get the stem change in the PRESENT tense
# (boot verbs: all singular + 3p, i.e. indices 0,1,2,5)
_BOOT_INDICES = {0, 1, 2, 5}

# Stem-change type → (from_vowel, to_vowel)
STEM_CHANGE_MAP: Dict[str, Tuple[str, str]] = {
    "e>ie": ("e", "ie"),
    "o>ue": ("o", "ue"),
    "e>i": ("e", "i"),
    "u>ue": ("u", "ue"),
    "i>ie": ("i", "ie"),
}

# Common stem-changing verbs: infinitive → change type
# This is not exhaustive but covers the most frequent verbs.
STEM_CHANGING_VERBS: Dict[str, str] = {
    # e → ie
    "pensar": "e>ie",
    "cerrar": "e>ie",
    "comenzar": "e>ie",
    "empezar": "e>ie",
    "despertar": "e>ie",
    "gobernar": "e>ie",
    "negar": "e>ie",
    "recomendar": "e>ie",
    "sentar": "e>ie",
    "acertar": "e>ie",
    "apretar": "e>ie",
    "atravesar": "e>ie",
    "calentar": "e>ie",
    "confesar": "e>ie",
    "encerrar": "e>ie",
    "helar": "e>ie",
    "manifestar": "e>ie",
    "merendar": "e>ie",
    "nevar": "e>ie",
    "quebrar": "e>ie",
    "regar": "e>ie",
    "tropezar": "e>ie",
    "entender": "e>ie",
    "perder": "e>ie",
    "querer": "e>ie",
    "defender": "e>ie",
    "encender": "e>ie",
    "ascender": "e>ie",
    "atender": "e>ie",
    "descender": "e>ie",
    "extender": "e>ie",
    "verter": "e>ie",
    "sentir": "e>ie",
    "mentir": "e>ie",
    "preferir": "e>ie",
    "convertir": "e>ie",
    "divertir": "e>ie",
    "hervir": "e>ie",
    "sugerir": "e>ie",
    "advertir": "e>ie",
    "adherir": "e>ie",
    "arrepentir": "e>ie",
    "consentir": "e>ie",
    "digerir": "e>ie",
    "herir": "e>ie",
    "invertir": "e>ie",
    "referir": "e>ie",
    # o → ue
    "contar": "o>ue",
    "encontrar": "o>ue",
    "recordar": "o>ue",
    "mostrar": "o>ue",
    "costar": "o>ue",
    "volar": "o>ue",
    "soñar": "o>ue",
    "probar": "o>ue",
    "almorzar": "o>ue",
    "rogar": "o>ue",
    "acordar": "o>ue",
    "acostar": "o>ue",
    "apostar": "o>ue",
    "aprobar": "o>ue",
    "colgar": "o>ue",
    "comprobar": "o>ue",
    "demostrar": "o>ue",
    "forzar": "o>ue",
    "rodar": "o>ue",
    "sonar": "o>ue",
    "tostar": "o>ue",
    "poder": "o>ue",
    "volver": "o>ue",
    "mover": "o>ue",
    "resolver": "o>ue",
    "soler": "o>ue",
    "cocer": "o>ue",
    "doler": "o>ue",
    "devolver": "o>ue",
    "envolver": "o>ue",
    "llover": "o>ue",
    "morder": "o>ue",
    "oler": "o>ue",
    "torcer": "o>ue",
    "dormir": "o>ue",
    "morir": "o>ue",
    # e → i (only -ir verbs)
    "pedir": "e>i",
    "servir": "e>i",
    "repetir": "e>i",
    "seguir": "e>i",
    "vestir": "e>i",
    "medir": "e>i",
    "competir": "e>i",
    "impedir": "e>i",
    "conseguir": "e>i",
    "perseguir": "e>i",
    "corregir": "e>i",
    "elegir": "e>i",
    "despedir": "e>i",
    "gemir": "e>i",
    "rendir": "e>i",
    "reñir": "e>i",
    "teñir": "e>i",
    "ceñir": "e>i",
    # u → ue
    "jugar": "u>ue",
    # i → ie
    "adquirir": "i>ie",
    "inquirir": "i>ie",
}


def _apply_stem_change(stem: str, from_v: str, to_v: str) -> str:
    """Apply a vowel stem change to the *last* occurrence of from_v in stem."""
    idx = stem.rfind(from_v)
    if idx == -1:
        return stem
    return stem[:idx] + to_v + stem[idx + len(from_v) :]


# ---------------------------------------------------------------------------
# Spelling-change rules (orthographic adjustments)
# ---------------------------------------------------------------------------


def _spelling_adjust_ar_subj(stem: str) -> str:
    """Adjust -ar verb stem for subjunctive (stem + e-vowel endings).

    c → qu, g → gu, z → c, gu → gü before 'e'.
    """
    if stem.endswith("c"):
        return stem[:-1] + "qu"
    if stem.endswith("gu"):
        # The u must stay audible: averiguar → averigüe.
        return stem[:-1] + "ü"
    if stem.endswith("g"):
        return stem + "u"
    if stem.endswith("z"):
        return stem[:-1] + "c"
    return stem


def _spelling_adjust_preterite_yo(stem: str, verb_class: str) -> str:
    """Adjust stem for 1s preterite of -ar verbs.

    c → qu, g → gu, z → c, gu → gü before 'é'.
    """
    if verb_class != "ar":
        return stem
    return _spelling_adjust_ar_subj(stem)


# ---------------------------------------------------------------------------
# Irregular future / conditional stems
# ---------------------------------------------------------------------------

IRREGULAR_FUTURE_STEMS: Dict[str, str] = {
    "caber": "cabr",
    "decir": "dir",
    "haber": "habr",
    "hacer": "har",
    "poder": "podr",
    "poner": "pondr",
    "querer": "querr",
    "saber": "sabr",
    "salir": "saldr",
    "tener": "tendr",
    "valer": "valdr",
    "venir": "vendr",
}

# ---------------------------------------------------------------------------
# Irregular preterite stems (pretérito grave / strong preterites)
# These use special endings: -e, -iste, -o, -imos, -isteis, -ieron/-eron
# ---------------------------------------------------------------------------

_STRONG_PRET_ENDINGS = ("e", "iste", "o", "imos", "isteis", "ieron")
_STRONG_PRET_ENDINGS_J = ("e", "iste", "o", "imos", "isteis", "eron")

IRREGULAR_PRETERITE: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "andar": ("anduv", _STRONG_PRET_ENDINGS),
    "caber": ("cup", _STRONG_PRET_ENDINGS),
    "estar": ("estuv", _STRONG_PRET_ENDINGS),
    "haber": ("hub", _STRONG_PRET_ENDINGS),
    "hacer": ("hic", _STRONG_PRET_ENDINGS),  # 3s: hizo handled below
    "poder": ("pud", _STRONG_PRET_ENDINGS),
    "poner": ("pus", _STRONG_PRET_ENDINGS),
    "querer": ("quis", _STRONG_PRET_ENDINGS),
    "saber": ("sup", _STRONG_PRET_ENDINGS),
    "tener": ("tuv", _STRONG_PRET_ENDINGS),
    "venir": ("vin", _STRONG_PRET_ENDINGS),
    "decir": ("dij", _STRONG_PRET_ENDINGS_J),
    "traer": ("traj", _STRONG_PRET_ENDINGS_J),
    "conducir": ("conduj", _STRONG_PRET_ENDINGS_J),
    "producir": ("produj", _STRONG_PRET_ENDINGS_J),
    "traducir": ("traduj", _STRONG_PRET_ENDINGS_J),
}

# ---------------------------------------------------------------------------
# Irregular 1s present indicative
# ---------------------------------------------------------------------------

IRREGULAR_1S_PRESENT: Dict[str, str] = {
    "caber": "quepo",
    "caer": "caigo",
    "conocer": "conozco",
    "dar": "doy",
    "decir": "digo",
    "hacer": "hago",
    "oír": "oigo",
    "poner": "pongo",
    "saber": "sé",
    "salir": "salgo",
    "tener": "tengo",
    "traer": "traigo",
    "valer": "valgo",
    "venir": "vengo",
    "ver": "veo",
}

# ---------------------------------------------------------------------------
# Irregular past participles
# ---------------------------------------------------------------------------

IRREGULAR_PAST_PARTICIPLES: Dict[str, str] = {
    "abrir": "abierto",
    "cubrir": "cubierto",
    "decir": "dicho",
    "escribir": "escrito",
    "hacer": "hecho",
    "morir": "muerto",
    "poner": "puesto",
    "resolver": "resuelto",
    "romper": "roto",
    "satisfacer": "satisfecho",
    "ver": "visto",
    "volver": "vuelto",
    "imprimir": "impreso",
    "freír": "frito",
}

# ---------------------------------------------------------------------------
# Fully irregular verb tables
# ---------------------------------------------------------------------------

# Each maps form_key → conjugated string
_SER: Dict[str, str] = {
    "1s_present": "soy",
    "2s_present": "eres",
    "3s_present": "es",
    "1p_present": "somos",
    "2p_present": "sois",
    "3p_present": "son",
    "1s_preterite": "fui",
    "2s_preterite": "fuiste",
    "3s_preterite": "fue",
    "1p_preterite": "fuimos",
    "2p_preterite": "fuisteis",
    "3p_preterite": "fueron",
    "1s_imperfect": "era",
    "2s_imperfect": "eras",
    "3s_imperfect": "era",
    "1p_imperfect": "éramos",
    "2p_imperfect": "erais",
    "3p_imperfect": "eran",
    "1s_subjunctive_present": "sea",
    "2s_subjunctive_present": "seas",
    "3s_subjunctive_present": "sea",
    "1p_subjunctive_present": "seamos",
    "2p_subjunctive_present": "seáis",
    "3p_subjunctive_present": "sean",
    "2s_imperative": "sé",
    "3s_imperative": "sea",
    "1p_imperative": "seamos",
    "2p_imperative": "sed",
    "3p_imperative": "sean",
    "gerund": "siendo",
    "past_participle": "sido",
}

_IR: Dict[str, str] = {
    "1s_present": "voy",
    "2s_present": "vas",
    "3s_present": "va",
    "1p_present": "vamos",
    "2p_present": "vais",
    "3p_present": "van",
    "1s_preterite": "fui",
    "2s_preterite": "fuiste",
    "3s_preterite": "fue",
    "1p_preterite": "fuimos",
    "2p_preterite": "fuisteis",
    "3p_preterite": "fueron",
    "1s_imperfect": "iba",
    "2s_imperfect": "ibas",
    "3s_imperfect": "iba",
    "1p_imperfect": "íbamos",
    "2p_imperfect": "ibais",
    "3p_imperfect": "iban",
    "1s_subjunctive_present": "vaya",
    "2s_subjunctive_present": "vayas",
    "3s_subjunctive_present": "vaya",
    "1p_subjunctive_present": "vayamos",
    "2p_subjunctive_present": "vayáis",
    "3p_subjunctive_present": "vayan",
    "2s_imperative": "ve",
    "3s_imperative": "vaya",
    "1p_imperative": "vamos",
    "2p_imperative": "id",
    "3p_imperative": "vayan",
    "gerund": "yendo",
    "past_participle": "ido",
}

_HABER: Dict[str, str] = {
    "1s_present": "he",
    "2s_present": "has",
    "3s_present": "ha",
    "1p_present": "hemos",
    "2p_present": "habéis",
    "3p_present": "han",
    "1s_preterite": "hube",
    "2s_preterite": "hubiste",
    "3s_preterite": "hubo",
    "1p_preterite": "hubimos",
    "2p_preterite": "hubisteis",
    "3p_preterite": "hubieron",
    "1s_imperfect": "había",
    "2s_imperfect": "habías",
    "3s_imperfect": "había",
    "1p_imperfect": "habíamos",
    "2p_imperfect": "habíais",
    "3p_imperfect": "habían",
    "1s_subjunctive_present": "haya",
    "2s_subjunctive_present": "hayas",
    "3s_subjunctive_present": "haya",
    "1p_subjunctive_present": "hayamos",
    "2p_subjunctive_present": "hayáis",
    "3p_subjunctive_present": "hayan",
    "2s_imperative": "he",
    "3s_imperative": "haya",
    "1p_imperative": "hayamos",
    "2p_imperative": "habed",
    "3p_imperative": "hayan",
    "gerund": "habiendo",
    "past_participle": "habido",
}

_ESTAR: Dict[str, str] = {
    "1s_present": "estoy",
    "2s_present": "estás",
    "3s_present": "está",
    "1p_present": "estamos",
    "2p_present": "estáis",
    "3p_present": "están",
    "1s_subjunctive_present": "esté",
    "2s_subjunctive_present": "estés",
    "3s_subjunctive_present": "esté",
    "1p_subjunctive_present": "estemos",
    "2p_subjunctive_present": "estéis",
    "3p_subjunctive_present": "estén",
    "2s_imperative": "está",
    "3s_imperative": "esté",
    "1p_imperative": "estemos",
    "2p_imperative": "estad",
    "3p_imperative": "estén",
    "gerund": "estando",
    "past_participle": "estado",
}

_DAR: Dict[str, str] = {
    "1s_present": "doy",
    "2s_present": "das",
    "3s_present": "da",
    "1p_present": "damos",
    "2p_present": "dais",
    "3p_present": "dan",
    "1s_preterite": "di",
    "2s_preterite": "diste",
    "3s_preterite": "dio",
    "1p_preterite": "dimos",
    "2p_preterite": "disteis",
    "3p_preterite": "dieron",
    "1s_subjunctive_present": "dé",
    "2s_subjunctive_present": "des",
    "3s_subjunctive_present": "dé",
    "1p_subjunctive_present": "demos",
    "2p_subjunctive_present": "deis",
    "3p_subjunctive_present": "den",
    "2s_imperative": "da",
    "3s_imperative": "dé",
    "1p_imperative": "demos",
    "2p_imperative": "dad",
    "3p_imperative": "den",
    "gerund": "dando",
    "past_participle": "dado",
}

FULLY_IRREGULAR: Dict[str, Dict[str, str]] = {
    "ser": _SER,
    "ir": _IR,
    "haber": _HABER,
    "estar": _ESTAR,
    "dar": _DAR,
}

# ---------------------------------------------------------------------------
# -ucir verbs (conducir, producir, traducir, etc.) take the -zco present below
# and an irregular -uj- preterite.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# -cer/-cir spelling families
#
# A vowel before the -cer/-cir ending gives the inchoative -zco pattern
# (conocer -> conozco, florecer -> florezco, traducir -> traduzco); a consonant
# before it gives a plain c -> z swap before the back vowels (vencer -> venzo,
# esparcir -> esparzo).  Only a short list of verbs escapes the vowel rule.
# ---------------------------------------------------------------------------

_ZCO_EXCEPTIONS: Set[str] = {
    "cocer",
    "contrahacer",
    "deshacer",
    "escocer",
    "hacer",
    "mecer",
    "recocer",
    "rehacer",
    "remecer",
    "satisfacer",
}

_VOWELS = "aeiouáéíóú"

# -iar verbs that stress the weak vowel in the boot forms (enviar -> envío)
# rather than gliding over it (cambiar -> cambio).  The split is lexical, so
# the accented ones are listed; -uar follows a rule instead (see below).
ACCENTED_IAR_VERBS: Set[str] = {
    "ampliar",
    "confiar",
    "criar",
    "desafiar",
    "desviar",
    "enfriar",
    "enviar",
    "espiar",
    "fiar",
    "guiar",
    "liar",
    "resfriar",
    "rociar",
    "vaciar",
    "variar",
}

# Stems that already end in a palatal absorb the i of -ió / -ieron / -iendo:
# gruñir -> gruñó, gruñendo; bullir -> bulleron.
_I_ABSORBING_STEM_ENDINGS = ("ñ", "ll", "ch")


def _stresses_weak_vowel(inf: str) -> bool:
    """True if the boot forms break the glide and accent the stem's i/u.

    -uar follows the spelling: the u is a silent digraph marker after g or c
    (averiguar → averiguo, evacuar → evacuo) and a full vowel otherwise
    (actuar → actúo, continuar → continúo).  -iar is lexical.
    """
    if inf in ACCENTED_IAR_VERBS:
        return True
    if inf.endswith("uar"):
        return len(inf) > 3 and inf[-4] not in "gc"
    return False


def _takes_zco(inf: str) -> bool:
    """True for -cer/-cir verbs with the inchoative -zco 1s present."""
    if inf in _ZCO_EXCEPTIONS or not inf.endswith(("cer", "cir")):
        return False
    before_c = inf[:-3]
    return bool(before_c) and before_c[-1] in _VOWELS


def _takes_c_to_z(inf: str) -> bool:
    """True for -cer/-cir verbs that simply write c as z before o/a."""
    return inf.endswith(("cer", "cir")) and not _takes_zco(inf)


def _has_strong_vowel_stem(stem: str) -> bool:
    """True if ``stem`` ends in a strong vowel, as in leer, creer, caer, oír."""
    return bool(stem) and stem[-1] in "aeoáéó"


def _absorbs_i(stem: str) -> bool:
    """True if ``stem`` swallows the i of an -i- initial ending."""
    return stem.endswith(_I_ABSORBING_STEM_ENDINGS)


def _spelling_adjust_before_back_vowel(inf: str, stem: str) -> str:
    """Adjust a stem for the -o/-a endings (1s present and the subjunctive).

    Spanish keeps the consonant sound constant and moves the spelling:
    coger -> cojo, seguir -> sigo, delinquir -> delinco, vencer -> venzo.
    """
    if inf.endswith(("ger", "gir")) and stem.endswith("g"):
        return stem[:-1] + "j"
    if inf.endswith("guir") and stem.endswith("gu"):
        return stem[:-1]
    if inf.endswith("quir") and stem.endswith("qu"):
        return stem[:-2] + "c"
    if _takes_c_to_z(inf) and stem.endswith("c"):
        return stem[:-1] + "z"
    return stem


def _accent_final_weak_vowel(stem: str) -> str:
    """Write an accent on the stem's final i/u (envi- -> enví-, continu- -> continú-)."""
    if stem.endswith("i"):
        return stem[:-1] + "í"
    if stem.endswith("u"):
        return stem[:-1] + "ú"
    return stem


def _restore_initial_h(stem: str) -> str:
    """Spanish writes a word-initial ue/ie diphthong with a silent h (oler -> huelo)."""
    if stem.startswith(("ue", "ie")):
        return "h" + stem
    return stem


# ---------------------------------------------------------------------------
# The -eír family (reír, sonreír, freír)
#
# These combine the e→i change with a hiatus that has to be written: río but
# reímos, rio but sonrió.  The pattern is regular within the family, so it is
# generated from the prefix before -eír.
# ---------------------------------------------------------------------------

EIR_VERBS: Set[str] = {
    "desleír",
    "engreír",
    "freír",
    "refreír",
    "reír",
    "sofreír",
    "sonreír",
}


def _conjugate_eir(inf: str) -> Dict[str, str]:
    """Build the full table for an -eír verb from its prefix."""
    prefix = inf[:-3]
    forms: Dict[str, str] = {"infinitive": inf}

    present = ("ío", "íes", "íe", "eímos", "eís", "íen")
    preterite = ("eí", "eíste", "io", "eímos", "eísteis", "ieron")
    subjunctive = ("ía", "ías", "ía", "iamos", "iais", "ían")
    for i, person in enumerate(PERSONS):
        forms[f"{person}_present"] = prefix + present[i]
        forms[f"{person}_subjunctive_present"] = prefix + subjunctive[i]
        pret = prefix + preterite[i]
        if i == 2:
            # rio is a monosyllable and takes no accent; sonrió does.
            pret = respell_with_stress(pret, len(pret) - 1)
        forms[f"{person}_preterite"] = pret

    stem = prefix + "e"
    future_stem = prefix + "eir"
    for i, person in enumerate(PERSONS):
        forms[f"{person}_imperfect"] = stem + _ER_IMPERFECT[i]
        forms[f"{person}_future"] = future_stem + _FUTURE[i]
        forms[f"{person}_conditional"] = future_stem + _CONDITIONAL[i]

    forms["2s_imperative"] = prefix + "íe"
    forms["3s_imperative"] = prefix + "ía"
    forms["1p_imperative"] = prefix + "iamos"
    forms["2p_imperative"] = prefix + "eíd"
    forms["3p_imperative"] = prefix + "ían"

    forms["gerund"] = prefix + "iendo"
    forms["past_participle"] = IRREGULAR_PAST_PARTICIPLES.get(inf, prefix + "eído")
    return forms


# ---------------------------------------------------------------------------
# Reflexive (pronominal) verbs
#
# levantarse conjugates as levantar plus a reflexive pronoun: proclitic before
# a finite form (me levanto), enclitic on the infinitive, the gerund and the
# affirmative imperative (levantarse, levantándose, levántate).
# ---------------------------------------------------------------------------

REFLEXIVE_CLITICS: Dict[str, str] = {
    "1s": "me",
    "2s": "te",
    "3s": "se",
    "1p": "nos",
    "2p": "os",
    "3p": "se",
}

_PROCLITIC_TENSES = (
    "present",
    "preterite",
    "imperfect",
    "future",
    "conditional",
    "subjunctive_present",
)

# irse keeps the d of its vosotros imperative: idos, not *ios.
_KEEPS_IMPERATIVE_D = {"irse"}


def is_reflexive(infinitive: str) -> bool:
    """True if ``infinitive`` is a pronominal infinitive such as ``levantarse``."""
    inf = infinitive.lower().strip()
    return inf.endswith("se") and get_verb_class(inf[:-2]) is not None


def _attach_enclitic(form: str, clitic: str, drop_final: int = 0) -> str:
    """Attach ``clitic`` to ``form``, respelling the written accent if needed.

    ``drop_final`` removes that many trailing letters first, for the imperatives
    that lose a consonant before the pronoun (levantad + os → levantaos).  The
    stress is read from the untrimmed form, which is where it actually falls.
    """
    stressed_index = stressed_nucleus(form)
    stem = strip_accents(form)
    if drop_final:
        stem = stem[:-drop_final]
    combined = stem + clitic
    if stressed_index is None:
        return combined
    return respell_with_stress(combined, stressed_index)


def _conjugate_reflexive(inf: str) -> Optional[Dict[str, str]]:
    """Conjugate a pronominal verb from its base verb plus reflexive pronouns."""
    base_forms = conjugate(inf[:-2])
    if base_forms is None:
        return None

    forms: Dict[str, str] = {"infinitive": inf}
    for tense in _PROCLITIC_TENSES:
        for person in PERSONS:
            key = f"{person}_{tense}"
            base_form = base_forms.get(key)
            if base_form:
                forms[key] = f"{REFLEXIVE_CLITICS[person]} {base_form}"

    for person in ("2s", "3s", "3p"):
        forms[f"{person}_imperative"] = _attach_enclitic(
            base_forms[f"{person}_imperative"], REFLEXIVE_CLITICS[person]
        )

    # nosotros drops the -s before -nos: levantemos + nos → levantémonos.
    imperative_1p = base_forms["1p_imperative"]
    forms["1p_imperative"] = _attach_enclitic(
        imperative_1p, "nos", drop_final=1 if imperative_1p.endswith("s") else 0
    )

    # vosotros drops the -d before -os: levantad + os → levantaos, vestid + os
    # → vestíos.
    imperative_2p = base_forms["2p_imperative"]
    drops_d = imperative_2p.endswith("d") and inf not in _KEEPS_IMPERATIVE_D
    forms["2p_imperative"] = _attach_enclitic(imperative_2p, "os", drop_final=1 if drops_d else 0)

    forms["gerund"] = _attach_enclitic(base_forms["gerund"], "se")
    forms["past_participle"] = base_forms["past_participle"]
    return forms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _is_uir_verb(inf: str) -> bool:
    """True for -uir verbs with a consonantal y (construir, huir, incluir).

    Excludes -guir/-quir, where the u is a silent digraph marker (seguir,
    distinguir) and no y is inserted.
    """
    return inf.endswith("uir") and not inf.endswith(("guir", "quir"))


def get_verb_class(infinitive: str) -> Optional[str]:
    """Return 'ar', 'er', or 'ir' based on verb ending, or None."""
    inf = infinitive.lower().strip()
    if inf.endswith("ar"):
        return "ar"
    if inf.endswith("er"):
        return "er"
    if inf.endswith("ir") or inf.endswith("ír"):
        return "ir"
    return None


def get_stem(infinitive: str) -> str:
    """Return the stem by removing the -ar/-er/-ir ending."""
    inf = infinitive.lower().strip()
    if inf.endswith("ír"):
        return inf[:-2]
    return inf[:-2]


def conjugate(infinitive: str) -> Optional[Dict[str, str]]:
    """Conjugate a Spanish verb, returning a dict of form_key → form.

    Form keys match VerbConjugation.ALL_FORMS from langtools.es.types:
      1s_present, 2s_present, ..., 3p_present,
      1s_preterite, ..., 3p_preterite,
      1s_imperfect, ..., 3p_imperfect,
      1s_future, ..., 3p_future,
      1s_conditional, ..., 3p_conditional,
      1s_subjunctive_present, ..., 3p_subjunctive_present,
      2s_imperative, 3s_imperative, 1p_imperative, 2p_imperative, 3p_imperative,
      infinitive, gerund, past_participle

    Returns None if the infinitive is not a recognised Spanish verb form.
    """
    inf = infinitive.lower().strip()
    if is_reflexive(inf):
        return _conjugate_reflexive(inf)

    verb_class = get_verb_class(inf)
    if verb_class is None:
        return None

    if inf in EIR_VERBS:
        return _conjugate_eir(inf)

    forms: Dict[str, str] = {}
    forms["infinitive"] = inf

    # --- Fully irregular verbs (override everything) ---
    if inf in FULLY_IRREGULAR:
        overrides = FULLY_IRREGULAR[inf]
        forms.update(overrides)
        # Fill in future/conditional if not overridden
        fut_stem = IRREGULAR_FUTURE_STEMS.get(inf, inf)
        for tense, endings in [("future", _FUTURE), ("conditional", _CONDITIONAL)]:
            for i, person in enumerate(PERSONS):
                key = f"{person}_{tense}"
                if key not in forms:
                    forms[key] = fut_stem + endings[i]
        # Fill in imperfect if not overridden (regular for estar, dar)
        endings_table = REGULAR_ENDINGS[verb_class]
        for i, person in enumerate(PERSONS):
            key = f"{person}_imperfect"
            if key not in forms:
                stem = get_stem(inf)
                forms[key] = stem + endings_table["imperfect"][i]
        # Fill in preterite from IRREGULAR_PRETERITE if not overridden
        if inf in IRREGULAR_PRETERITE:
            pret_stem, pret_endings = IRREGULAR_PRETERITE[inf]
            for i, person in enumerate(PERSONS):
                key = f"{person}_preterite"
                if key not in forms:
                    form = pret_stem + pret_endings[i]
                    forms[key] = form
        # Imperative / non-finite defaults
        if "gerund" not in forms:
            forms["gerund"] = _make_gerund(inf, verb_class)
        if "past_participle" not in forms:
            forms["past_participle"] = _make_past_participle(inf, verb_class)
        _fill_imperative(forms, inf, verb_class)
        return forms

    stem = get_stem(inf)
    sc_type = STEM_CHANGING_VERBS.get(inf)

    # --- Present indicative ---
    _conjugate_present(forms, inf, stem, verb_class, sc_type)

    # --- Preterite ---
    _conjugate_preterite(forms, inf, stem, verb_class, sc_type)

    # --- Imperfect (always regular except ser/ir/ver) ---
    _conjugate_imperfect(forms, inf, stem, verb_class)

    # --- Future ---
    fut_stem = IRREGULAR_FUTURE_STEMS.get(inf, inf)
    for i, person in enumerate(PERSONS):
        forms[f"{person}_future"] = fut_stem + _FUTURE[i]

    # --- Conditional ---
    for i, person in enumerate(PERSONS):
        forms[f"{person}_conditional"] = fut_stem + _CONDITIONAL[i]

    # --- Subjunctive present ---
    _conjugate_subjunctive_present(forms, inf, stem, verb_class, sc_type)

    # --- Imperative ---
    _fill_imperative(forms, inf, verb_class)

    # --- Non-finite ---
    forms["gerund"] = _make_gerund(inf, verb_class, sc_type)
    pp = IRREGULAR_PAST_PARTICIPLES.get(inf)
    if pp is None:
        pp = _make_past_participle(inf, verb_class)
    forms["past_participle"] = pp

    return forms


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _conjugate_present(
    forms: Dict[str, str],
    inf: str,
    stem: str,
    verb_class: str,
    sc_type: Optional[str],
) -> None:
    endings = REGULAR_ENDINGS[verb_class]["present"]

    # Handle irregular 1s
    irr_1s = IRREGULAR_1S_PRESENT.get(inf)

    is_zco = _takes_zco(inf)
    is_uir = _is_uir_verb(inf)
    is_accented_glide = _stresses_weak_vowel(inf)

    for i, person in enumerate(PERSONS):
        key = f"{person}_present"
        if i == 0 and irr_1s:
            forms[key] = irr_1s
        elif i == 0 and is_zco:
            forms[key] = stem[:-1] + "zco"
        else:
            s = stem
            if sc_type and i in _BOOT_INDICES:
                from_v, to_v = STEM_CHANGE_MAP[sc_type]
                s = _restore_initial_h(_apply_stem_change(stem, from_v, to_v))
            # -uir verbs insert y in the boot (construyo, but construimos)
            if is_uir and i in _BOOT_INDICES:
                s = stem + "y"
            # enviar -> envío, continuar -> continúo: the boot forms break the
            # glide and take the written accent.
            if is_accented_glide and i in _BOOT_INDICES:
                s = _accent_final_weak_vowel(s)
            # The 1s -o ending triggers the same spelling shifts as the
            # subjunctive: cojo, sigo, delinco, venzo.
            if endings[i].startswith("o"):
                s = _spelling_adjust_before_back_vowel(inf, s)
            forms[key] = s + endings[i]


def _conjugate_preterite(
    forms: Dict[str, str],
    inf: str,
    stem: str,
    verb_class: str,
    sc_type: Optional[str],
) -> None:
    # Strong/irregular preterites
    if inf in IRREGULAR_PRETERITE:
        pret_stem, pret_endings = IRREGULAR_PRETERITE[inf]
        for i, person in enumerate(PERSONS):
            form_val = pret_stem + pret_endings[i]
            # hacer 3s: hic + o → hizo (c→z before o)
            if inf == "hacer" and i == 2:
                form_val = "hizo"
            forms[f"{person}_preterite"] = form_val
        return

    # -ucir verbs not explicitly listed
    if inf.endswith("ucir"):
        pret_stem = stem[:-2] + "uj"
        for i, person in enumerate(PERSONS):
            forms[f"{person}_preterite"] = pret_stem + _STRONG_PRET_ENDINGS_J[i]
        return

    endings = REGULAR_ENDINGS[verb_class]["preterite"]

    # -uir verbs: unstressed i → y between vowels in 3s/3p (construyó,
    # construyeron); other persons keep the regular endings.
    if _is_uir_verb(inf):
        for i, person in enumerate(PERSONS):
            if i in (2, 5):
                forms[f"{person}_preterite"] = stem + "y" + endings[i][1:]
            else:
                forms[f"{person}_preterite"] = stem + endings[i]
        return

    # Stems ending in a strong vowel turn the unstressed i of the ending into y
    # in 3s/3p and take a written accent elsewhere: leí, leíste, leyó, leímos,
    # leísteis, leyeron.
    if verb_class in ("er", "ir") and _has_strong_vowel_stem(stem):
        for i, person in enumerate(PERSONS):
            ending = endings[i]
            if i in (2, 5):
                ending = "y" + ending[1:]
            elif ending.startswith("i"):
                ending = "í" + ending[1:]
            forms[f"{person}_preterite"] = stem + ending
        return

    # Stem-changing -ir verbs: e→i or o→u in 3s and 3p preterite
    ir_pret_change: Optional[Tuple[str, str]] = None
    if verb_class == "ir" and sc_type:
        if sc_type in ("e>ie", "e>i"):
            ir_pret_change = ("e", "i")
        elif sc_type in ("o>ue",):
            ir_pret_change = ("o", "u")

    for i, person in enumerate(PERSONS):
        s = stem
        ending = endings[i]
        # Spelling change for 1s -ar preterite
        if i == 0:
            s = _spelling_adjust_preterite_yo(s, verb_class)
        # -ir stem changes in 3s (i=2) and 3p (i=5)
        if ir_pret_change and i in (2, 5):
            s = _apply_stem_change(stem, ir_pret_change[0], ir_pret_change[1])
        # gruñir → gruñó / gruñeron, bullir → bulló / bulleron
        if i in (2, 5) and _absorbs_i(s) and ending.startswith("i"):
            ending = ending[1:]
        forms[f"{person}_preterite"] = s + ending


def _conjugate_imperfect(
    forms: Dict[str, str],
    inf: str,
    stem: str,
    verb_class: str,
) -> None:
    # ver is irregular in imperfect
    if inf == "ver":
        bases = ("veía", "veías", "veía", "veíamos", "veíais", "veían")
        for i, person in enumerate(PERSONS):
            forms[f"{person}_imperfect"] = bases[i]
        return

    endings = REGULAR_ENDINGS[verb_class]["imperfect"]
    for i, person in enumerate(PERSONS):
        forms[f"{person}_imperfect"] = stem + endings[i]


def _conjugate_subjunctive_present(
    forms: Dict[str, str],
    inf: str,
    stem: str,
    verb_class: str,
    sc_type: Optional[str],
) -> None:
    endings = REGULAR_ENDINGS[verb_class]["subjunctive_present"]

    # The subjunctive stem is based on the 1s present indicative
    # For verbs with irregular 1s, derive subjunctive stem from that
    irr_1s = IRREGULAR_1S_PRESENT.get(inf)

    if irr_1s:
        # Drop the -o from 1s to get subjunctive stem
        subj_stem = irr_1s[:-1] if irr_1s.endswith("o") else irr_1s
        for i, person in enumerate(PERSONS):
            forms[f"{person}_subjunctive_present"] = subj_stem + endings[i]
        return

    if _takes_zco(inf):
        # conocer → conozca, traducir → traduzca, florecer → florezca
        subj_stem = stem[:-1] + "zc"
        for i, person in enumerate(PERSONS):
            forms[f"{person}_subjunctive_present"] = subj_stem + endings[i]
        return

    if _is_uir_verb(inf):
        # The y carries through every person: construya, construyamos, ...
        subj_stem = stem + "y"
        for i, person in enumerate(PERSONS):
            forms[f"{person}_subjunctive_present"] = subj_stem + endings[i]
        return

    # Spelling adjustments for regular subjunctive
    if verb_class == "ar":
        adj_stem = _spelling_adjust_ar_subj(stem)
    else:
        adj_stem = _spelling_adjust_before_back_vowel(inf, stem)

    is_accented_glide = _stresses_weak_vowel(inf)

    # Stem-changing verbs in subjunctive:
    # Boot pattern in 1s,2s,3s,3p; nosotros/vosotros keep original stem
    # Exception: -ir e>i verbs change e→i even in 1p/2p subjunctive
    for i, person in enumerate(PERSONS):
        s = adj_stem
        if sc_type and i in _BOOT_INDICES:
            from_v, to_v = STEM_CHANGE_MAP[sc_type]
            # The stem change comes first: jugar → jueg- → juegue, not jugu- →
            # juguee, because the spelling fix depends on the changed stem.
            changed = _apply_stem_change(stem, from_v, to_v)
            if verb_class == "ar":
                changed = _spelling_adjust_ar_subj(changed)
            else:
                changed = _spelling_adjust_before_back_vowel(inf, changed)
            s = _restore_initial_h(changed)
        elif sc_type and verb_class == "ir" and i in (3, 4):
            # 1p/2p subjunctive for -ir stem-changers
            if sc_type in ("e>ie", "e>i"):
                s = _apply_stem_change(adj_stem, "e", "i")
            elif sc_type == "o>ue":
                s = _apply_stem_change(adj_stem, "o", "u")
        if is_accented_glide and i in _BOOT_INDICES:
            s = _accent_final_weak_vowel(s)
        forms[f"{person}_subjunctive_present"] = s + endings[i]


def _fill_imperative(
    forms: Dict[str, str],
    inf: str,
    verb_class: str,
) -> None:
    """Fill imperative forms, deriving from present/subjunctive where possible."""
    # tú affirmative: same as 3s present indicative (for regular verbs)
    if "2s_imperative" not in forms:
        forms["2s_imperative"] = forms.get("3s_present", "")

    # Irregular tú imperatives
    _TU_IMPERATIVES: Dict[str, str] = {
        "decir": "di",
        "hacer": "haz",
        "poner": "pon",
        "salir": "sal",
        "tener": "ten",
        "venir": "ven",
        "oír": "oye",
    }
    if inf in _TU_IMPERATIVES:
        forms["2s_imperative"] = _TU_IMPERATIVES[inf]

    # usted (3s): same as 3s subjunctive present
    if "3s_imperative" not in forms:
        forms["3s_imperative"] = forms.get("3s_subjunctive_present", "")

    # nosotros (1p): same as 1p subjunctive present
    if "1p_imperative" not in forms:
        forms["1p_imperative"] = forms.get("1p_subjunctive_present", "")

    # vosotros (2p): replace final -r of infinitive with -d
    if "2p_imperative" not in forms:
        forms["2p_imperative"] = inf[:-1] + "d"

    # ustedes (3p): same as 3p subjunctive present
    if "3p_imperative" not in forms:
        forms["3p_imperative"] = forms.get("3p_subjunctive_present", "")


def _make_gerund(
    inf: str,
    verb_class: str,
    sc_type: Optional[str] = None,
) -> str:
    """Generate the gerundio."""
    stem = get_stem(inf)

    # -ir stem-changing verbs: e→i or o→u in gerund
    if verb_class == "ir" and sc_type:
        if sc_type in ("e>ie", "e>i"):
            stem = _apply_stem_change(stem, "e", "i")
        elif sc_type == "o>ue":
            stem = _apply_stem_change(stem, "o", "u")

    if verb_class == "ar":
        return stem + "ando"

    # Avoid an unstressed i between vowels: leer → leyendo, oír → oyendo.
    # A stem-final gu/qu is a digraph, not a vowel (seguir → siguiendo).
    if stem and stem[-1] in "aeiouáéíóú" and not stem.endswith(("gu", "qu")):
        return stem + "yendo"

    # gruñir → gruñendo, bullir → bullendo
    if _absorbs_i(stem):
        return stem + "endo"

    return stem + "iendo"


def _make_past_participle(inf: str, verb_class: str) -> str:
    """Generate regular past participle."""
    stem = get_stem(inf)
    if verb_class == "ar":
        return stem + "ado"
    # A strong vowel before the ending makes a hiatus that needs the accent:
    # leer → leído, caer → caído, oír → oído.
    if _has_strong_vowel_stem(stem):
        return stem + "ído"
    return stem + "ido"


def conjugate_safe(infinitive: str) -> Tuple[Dict[str, str], List[str]]:
    """Conjugate a verb and return (forms, warnings).

    Like conjugate() but never returns None — returns an empty dict
    with a warning instead. Also flags verbs not in any irregular table
    that end in patterns suggesting they may be irregular.
    """
    result = conjugate(infinitive)
    warnings: List[str] = []
    if result is None:
        return {}, [f"'{infinitive}' does not appear to be a Spanish verb"]

    inf = infinitive.lower().strip()

    # Warn if the verb may have irregularities beyond the rules applied above.
    known_irregular = (
        inf in FULLY_IRREGULAR
        or inf in IRREGULAR_PRETERITE
        or inf in STEM_CHANGING_VERBS
        or inf in IRREGULAR_1S_PRESENT
        or inf in IRREGULAR_FUTURE_STEMS
        or inf in IRREGULAR_PAST_PARTICIPLES
    )
    if not known_irregular and inf.endswith("iar") and inf not in ACCENTED_IAR_VERBS:
        # cambiar → cambio but enviar → envío; only -iar is lexical.
        warnings.append(f"'{inf}' may stress the weak vowel in its boot forms")

    return result, warnings
