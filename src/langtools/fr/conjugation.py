"""Rule-based French verb conjugation.

Generates conjugations mechanically for regular French verbs based on
their infinitive ending (-er, -ir, -re), with hard-coded forms for
common irregular verbs and automatic handling of compound verbs
(e.g. comprendre = com + prendre).

Regular patterns handled:
  - First group (-er): parler, with orthographic adjustments for
    -ger (manger), -cer (commencer), and -yer (payer/nettoyer)
  - Second group (-ir with -iss-): finir, choisir, etc.
  - Third group (-re regular): vendre, attendre, etc.

Note: Some -ir verbs belong to the third group (e.g. partir, dormir)
and do NOT follow the -iss- pattern.  These are included in the
irregular verbs table.  If an -ir verb is not in the table, the
second-group (-iss-) rules are applied, which may be incorrect for
third-group -ir verbs.

Usage:
    from langtools.fr.conjugation import conjugate

    result, success = conjugate("parler")
    if success:
        print(result.forms["1s_present"])  # "parle"
        print(result.forms["3p_future"])   # "parleront"
"""

from typing import Dict, List, Optional, Tuple

from langtools.fr.types import VerbConjugation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PERSONS = ["1s", "2s", "3s", "1p", "2p", "3p"]

# Standard endings by tense
_PRESENT_ER = ["e", "es", "e", "ons", "ez", "ent"]
_PRESENT_IR2 = ["is", "is", "it", "issons", "issez", "issent"]
_PRESENT_RE = ["s", "s", "", "ons", "ez", "ent"]
_IMPERFECT = ["ais", "ais", "ait", "ions", "iez", "aient"]
_FUTURE = ["ai", "as", "a", "ons", "ez", "ont"]

# Indices in _PERSONS where the present-tense ending is "silent"
# (relevant for -yer stem change: y -> i before silent endings)
_SILENT_PRESENT_INDICES = {0, 1, 2, 5}  # je, tu, il/elle, ils/elles

# ---------------------------------------------------------------------------
# Helpers to assemble form dictionaries
# ---------------------------------------------------------------------------


def _make_forms(
    present: List[str],
    imperfect: List[str],
    future: List[str],
    pp_m: str,
    pp_f: str,
) -> Dict[str, str]:
    """Assemble the 20-form dictionary expected by VerbConjugation."""
    forms: Dict[str, str] = {}
    for i, person in enumerate(_PERSONS):
        forms[f"{person}_present"] = present[i]
        forms[f"{person}_impf"] = imperfect[i]
        forms[f"{person}_future"] = future[i]
    forms["pc_m"] = pp_m
    forms["pc_f"] = pp_f
    return forms


def _future_from_stem(stem: str) -> List[str]:
    return [stem + e for e in _FUTURE]


def _imperfect_from_stem(stem: str) -> List[str]:
    return [stem + e for e in _IMPERFECT]


# ---------------------------------------------------------------------------
# Regular conjugation helpers
# ---------------------------------------------------------------------------


def _conjugate_er(infinitive: str) -> Dict[str, str]:
    """First-group (-er) conjugation with -ger / -cer / -yer adjustments."""
    stem = infinitive[:-2]

    is_ger = stem.endswith("g")
    is_cer = stem.endswith("c")
    is_yer = stem.endswith("y")

    # -- present --
    present: List[str] = []
    for i, ending in enumerate(_PRESENT_ER):
        s = stem
        if is_yer and i in _SILENT_PRESENT_INDICES:
            s = stem[:-1] + "i"
        elif is_ger and ending.startswith("o"):
            s = stem + "e"  # mangeons
        elif is_cer and ending.startswith("o"):
            s = stem[:-1] + "ç"  # commençons
        present.append(s + ending)

    # -- imperfect --
    imperfect: List[str] = []
    for ending in _IMPERFECT:
        s = stem
        if is_ger and ending.startswith("a"):
            s = stem + "e"  # mangeais
        elif is_cer and ending.startswith("a"):
            s = stem[:-1] + "ç"  # commençais
        # -yer: y stays before pronounced imperfect endings
        imperfect.append(s + ending)

    # -- future (stem = full infinitive; -yer: y -> i) --
    future_stem = infinitive
    if is_yer:
        future_stem = infinitive[:-3] + "ier"  # payer -> paier
    future = _future_from_stem(future_stem)

    # -- past participle --
    pp_m = stem + "é"
    pp_f = stem + "ée"

    return _make_forms(present, imperfect, future, pp_m, pp_f)


def _conjugate_ir(infinitive: str) -> Dict[str, str]:
    """Second-group (-ir with -iss-) conjugation."""
    stem = infinitive[:-2]  # fin- from finir

    present = [stem + e for e in _PRESENT_IR2]
    imperfect = _imperfect_from_stem(stem + "iss")
    future = _future_from_stem(infinitive)
    pp_m = stem + "i"
    pp_f = stem + "ie"

    return _make_forms(present, imperfect, future, pp_m, pp_f)


def _conjugate_re(infinitive: str) -> Dict[str, str]:
    """Regular third-group (-re) conjugation (e.g. vendre)."""
    stem = infinitive[:-2]  # vend- from vendre

    present = [stem + e for e in _PRESENT_RE]
    imperfect = _imperfect_from_stem(stem)
    future_stem = infinitive[:-1]  # vendr- (drop final e)
    future = _future_from_stem(future_stem)
    pp_m = stem + "u"
    pp_f = stem + "ue"

    return _make_forms(present, imperfect, future, pp_m, pp_f)


# ---------------------------------------------------------------------------
# Irregular verbs — compact representation
# ---------------------------------------------------------------------------
# Each entry stores:
#   present   : 6-element list [1s, 2s, 3s, 1p, 2p, 3p]
#   future_stem: stem for the future tense (+ ai/as/a/ons/ez/ont)
#   pp        : (masculine, feminine) past participle
#   impf_stem : optional override; when absent, derived from present[3]
#               by stripping the final "-ons"

_IrregDict = Dict[str, Dict[str, object]]

_IRREGULAR_DATA: _IrregDict = {
    # ── être / avoir ─────────────────────────────────────────────
    "être": {
        "present": ["suis", "es", "est", "sommes", "êtes", "sont"],
        "future_stem": "ser",
        "pp": ("été", "été"),
        "impf_stem": "ét",
    },
    "avoir": {
        "present": ["ai", "as", "a", "avons", "avez", "ont"],
        "future_stem": "aur",
        "pp": ("eu", "eue"),
    },
    # ── aller ────────────────────────────────────────────────────
    "aller": {
        "present": ["vais", "vas", "va", "allons", "allez", "vont"],
        "future_stem": "ir",
        "pp": ("allé", "allée"),
    },
    # ── faire ────────────────────────────────────────────────────
    "faire": {
        "present": ["fais", "fais", "fait", "faisons", "faites", "font"],
        "future_stem": "fer",
        "pp": ("fait", "faite"),
    },
    # ── -oir verbs ───────────────────────────────────────────────
    "pouvoir": {
        "present": ["peux", "peux", "peut", "pouvons", "pouvez", "peuvent"],
        "future_stem": "pourr",
        "pp": ("pu", "pu"),
    },
    "vouloir": {
        "present": ["veux", "veux", "veut", "voulons", "voulez", "veulent"],
        "future_stem": "voudr",
        "pp": ("voulu", "voulue"),
    },
    "devoir": {
        "present": ["dois", "dois", "doit", "devons", "devez", "doivent"],
        "future_stem": "devr",
        "pp": ("dû", "due"),
    },
    "savoir": {
        "present": ["sais", "sais", "sait", "savons", "savez", "savent"],
        "future_stem": "saur",
        "pp": ("su", "sue"),
    },
    "recevoir": {
        "present": ["reçois", "reçois", "reçoit", "recevons", "recevez", "reçoivent"],
        "future_stem": "recevr",
        "pp": ("reçu", "reçue"),
    },
    "voir": {
        "present": ["vois", "vois", "voit", "voyons", "voyez", "voient"],
        "future_stem": "verr",
        "pp": ("vu", "vue"),
    },
    "prévoir": {
        "present": ["prévois", "prévois", "prévoit", "prévoyons", "prévoyez", "prévoient"],
        "future_stem": "prévoir",
        "pp": ("prévu", "prévue"),
    },
    # ── -ire verbs ───────────────────────────────────────────────
    "dire": {
        "present": ["dis", "dis", "dit", "disons", "dites", "disent"],
        "future_stem": "dir",
        "pp": ("dit", "dite"),
    },
    "écrire": {
        "present": ["écris", "écris", "écrit", "écrivons", "écrivez", "écrivent"],
        "future_stem": "écrir",
        "pp": ("écrit", "écrite"),
    },
    "lire": {
        "present": ["lis", "lis", "lit", "lisons", "lisez", "lisent"],
        "future_stem": "lir",
        "pp": ("lu", "lue"),
    },
    "conduire": {
        "present": [
            "conduis",
            "conduis",
            "conduit",
            "conduisons",
            "conduisez",
            "conduisent",
        ],
        "future_stem": "conduir",
        "pp": ("conduit", "conduite"),
    },
    # ── -re verbs (irregular) ────────────────────────────────────
    "prendre": {
        "present": ["prends", "prends", "prend", "prenons", "prenez", "prennent"],
        "future_stem": "prendr",
        "pp": ("pris", "prise"),
    },
    "mettre": {
        "present": ["mets", "mets", "met", "mettons", "mettez", "mettent"],
        "future_stem": "mettr",
        "pp": ("mis", "mise"),
    },
    "connaître": {
        "present": [
            "connais",
            "connais",
            "connaît",
            "connaissons",
            "connaissez",
            "connaissent",
        ],
        "future_stem": "connaîtr",
        "pp": ("connu", "connue"),
    },
    "naître": {
        "present": ["nais", "nais", "naît", "naissons", "naissez", "naissent"],
        "future_stem": "naîtr",
        "pp": ("né", "née"),
    },
    "vivre": {
        "present": ["vis", "vis", "vit", "vivons", "vivez", "vivent"],
        "future_stem": "vivr",
        "pp": ("vécu", "vécue"),
    },
    "boire": {
        "present": ["bois", "bois", "boit", "buvons", "buvez", "boivent"],
        "future_stem": "boir",
        "pp": ("bu", "bue"),
    },
    "croire": {
        "present": ["crois", "crois", "croit", "croyons", "croyez", "croient"],
        "future_stem": "croir",
        "pp": ("cru", "crue"),
    },
    # ── -ir verbs (third group — NOT second group -iss-) ─────────
    "venir": {
        "present": ["viens", "viens", "vient", "venons", "venez", "viennent"],
        "future_stem": "viendr",
        "pp": ("venu", "venue"),
    },
    "tenir": {
        "present": ["tiens", "tiens", "tient", "tenons", "tenez", "tiennent"],
        "future_stem": "tiendr",
        "pp": ("tenu", "tenue"),
    },
    "partir": {
        "present": ["pars", "pars", "part", "partons", "partez", "partent"],
        "future_stem": "partir",
        "pp": ("parti", "partie"),
    },
    "sortir": {
        "present": ["sors", "sors", "sort", "sortons", "sortez", "sortent"],
        "future_stem": "sortir",
        "pp": ("sorti", "sortie"),
    },
    "dormir": {
        "present": ["dors", "dors", "dort", "dormons", "dormez", "dorment"],
        "future_stem": "dormir",
        "pp": ("dormi", "dormie"),
    },
    "sentir": {
        "present": ["sens", "sens", "sent", "sentons", "sentez", "sentent"],
        "future_stem": "sentir",
        "pp": ("senti", "sentie"),
    },
    "servir": {
        "present": ["sers", "sers", "sert", "servons", "servez", "servent"],
        "future_stem": "servir",
        "pp": ("servi", "servie"),
    },
    "mourir": {
        "present": ["meurs", "meurs", "meurt", "mourons", "mourez", "meurent"],
        "future_stem": "mourr",
        "pp": ("mort", "morte"),
    },
    "courir": {
        "present": ["cours", "cours", "court", "courons", "courez", "courent"],
        "future_stem": "courr",
        "pp": ("couru", "courue"),
    },
    "ouvrir": {
        "present": ["ouvre", "ouvres", "ouvre", "ouvrons", "ouvrez", "ouvrent"],
        "future_stem": "ouvrir",
        "pp": ("ouvert", "ouverte"),
    },
    "couvrir": {
        "present": ["couvre", "couvres", "couvre", "couvrons", "couvrez", "couvrent"],
        "future_stem": "couvrir",
        "pp": ("couvert", "couverte"),
    },
    "offrir": {
        "present": ["offre", "offres", "offre", "offrons", "offrez", "offrent"],
        "future_stem": "offrir",
        "pp": ("offert", "offerte"),
    },
    "souffrir": {
        "present": ["souffre", "souffres", "souffre", "souffrons", "souffrez", "souffrent"],
        "future_stem": "souffrir",
        "pp": ("souffert", "soufferte"),
    },
    # ── envoyer (irregular future) ───────────────────────────────
    "envoyer": {
        "present": ["envoie", "envoies", "envoie", "envoyons", "envoyez", "envoient"],
        "future_stem": "enverr",
        "pp": ("envoyé", "envoyée"),
    },
}

# ---------------------------------------------------------------------------
# Compound verbs — (prefix, base_infinitive)
# The conjugated forms are prefix + base_form for every cell.
# Only verbs that reliably follow this pattern are listed here.
# ---------------------------------------------------------------------------

_COMPOUND_VERBS: Dict[str, Tuple[str, str]] = {
    # venir family
    "revenir": ("re", "venir"),
    "devenir": ("de", "venir"),
    "parvenir": ("par", "venir"),
    "prévenir": ("pré", "venir"),
    "survenir": ("sur", "venir"),
    "intervenir": ("inter", "venir"),
    "convenir": ("con", "venir"),
    # tenir family
    "retenir": ("re", "tenir"),
    "obtenir": ("ob", "tenir"),
    "maintenir": ("main", "tenir"),
    "appartenir": ("appar", "tenir"),
    "contenir": ("con", "tenir"),
    "soutenir": ("sou", "tenir"),
    "entretenir": ("entre", "tenir"),
    # prendre family
    "reprendre": ("re", "prendre"),
    "comprendre": ("com", "prendre"),
    "apprendre": ("ap", "prendre"),
    "surprendre": ("sur", "prendre"),
    "entreprendre": ("entre", "prendre"),
    # mettre family
    "permettre": ("per", "mettre"),
    "admettre": ("ad", "mettre"),
    "remettre": ("re", "mettre"),
    "soumettre": ("sou", "mettre"),
    "promettre": ("pro", "mettre"),
    "commettre": ("com", "mettre"),
    "transmettre": ("trans", "mettre"),
    # faire family
    "défaire": ("dé", "faire"),
    "refaire": ("re", "faire"),
    # dire family (only redire; contredire/interdire differ in 2p)
    "redire": ("re", "dire"),
    # écrire family
    "décrire": ("dé", "écrire"),
    "réécrire": ("ré", "écrire"),
    # lire family
    "relire": ("re", "lire"),
    "élire": ("é", "lire"),
    # voir family (NOT prévoir — its future is regular)
    "revoir": ("re", "voir"),
    # vivre family
    "survivre": ("sur", "vivre"),
    "revivre": ("re", "vivre"),
    # naître family
    "renaître": ("re", "naître"),
    # courir family
    "parcourir": ("par", "courir"),
    "secourir": ("se", "courir"),
    "concourir": ("con", "courir"),
    # ouvrir / couvrir family
    "rouvrir": ("r", "ouvrir"),
    "découvrir": ("dé", "couvrir"),
    "recouvrir": ("re", "couvrir"),
    # envoyer family
    "renvoyer": ("r", "envoyer"),
    # conduire family
    "reconduire": ("re", "conduire"),
    # connaître family
    "reconnaître": ("re", "connaître"),
    # recevoir family
    "apercevoir": ("aper", "recevoir"),
    "concevoir": ("con", "recevoir"),
    # partir / sortir / dormir / sentir / servir
    "repartir": ("re", "partir"),
    "ressortir": ("res", "sortir"),
    "endormir": ("en", "dormir"),
    "rendormir": ("ren", "dormir"),
    "ressentir": ("res", "sentir"),
    "consentir": ("con", "sentir"),
    "desservir": ("des", "servir"),
}

# ---------------------------------------------------------------------------
# Expanding irregular / compound data into full form dicts
# ---------------------------------------------------------------------------


def _impf_stem_for(entry: Dict[str, object]) -> str:
    """Return the imperfect stem for an irregular verb entry.

    Uses the explicit ``impf_stem`` override when present; otherwise
    derives it from the nous-present form by stripping *-ons*.
    """
    override = entry.get("impf_stem")
    if isinstance(override, str):
        return override
    present = entry["present"]
    assert isinstance(present, list)
    nous: str = present[3]
    if nous.endswith("ons"):
        return nous[:-3]
    return nous  # pragma: no cover – safety fallback


def _expand_irregular(entry: Dict[str, object]) -> Dict[str, str]:
    """Expand a compact irregular-verb entry into 20 forms."""
    present = entry["present"]
    assert isinstance(present, list)
    future_stem = entry["future_stem"]
    assert isinstance(future_stem, str)
    pp = entry["pp"]
    assert isinstance(pp, tuple)
    pp_m: str = pp[0]
    pp_f: str = pp[1]

    impf_stem = _impf_stem_for(entry)
    return _make_forms(
        present,
        _imperfect_from_stem(impf_stem),
        _future_from_stem(future_stem),
        pp_m,
        pp_f,
    )


def _expand_compound(prefix: str, base_entry: Dict[str, object]) -> Dict[str, str]:
    """Expand a compound verb by prefixing every form of its base."""
    present = base_entry["present"]
    assert isinstance(present, list)
    future_stem = base_entry["future_stem"]
    assert isinstance(future_stem, str)
    pp = base_entry["pp"]
    assert isinstance(pp, tuple)

    compound_present = [prefix + f for f in present]
    impf_stem = prefix + _impf_stem_for(base_entry)
    compound_future_stem = prefix + future_stem
    pp_m = prefix + pp[0]
    pp_f = prefix + pp[1]

    return _make_forms(
        compound_present,
        _imperfect_from_stem(impf_stem),
        _future_from_stem(compound_future_stem),
        pp_m,
        pp_f,
    )


# ---------------------------------------------------------------------------
# Pre-built lookup table (populated once at import time)
# ---------------------------------------------------------------------------

_IRREGULAR_FORMS: Dict[str, Dict[str, str]] = {}

for _verb, _entry in _IRREGULAR_DATA.items():
    _IRREGULAR_FORMS[_verb] = _expand_irregular(_entry)

for _verb, (_prefix, _base) in _COMPOUND_VERBS.items():
    if _base in _IRREGULAR_DATA:
        _IRREGULAR_FORMS[_verb] = _expand_compound(_prefix, _IRREGULAR_DATA[_base])

# clean up module-level loop variables
del _verb, _entry, _prefix, _base

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def conjugate(infinitive: str) -> Tuple[VerbConjugation, bool]:
    """Conjugate a French verb using rule-based logic.

    Returns ``(VerbConjugation, True)`` on success, or
    ``(VerbConjugation(word=infinitive), False)`` when the verb
    cannot be conjugated (unrecognised ending, etc.).

    The function checks, in order:
      1. Hard-coded irregular and compound verbs
      2. Regular first-group  (-er)
      3. Regular second-group (-ir, with -iss-)
      4. Regular third-group  (-re)

    For -ir verbs not in the irregular table, second-group rules are
    applied.  Third-group -ir verbs (e.g. *partir*) must be in the
    irregular table to be conjugated correctly.
    """
    verb = infinitive.strip()
    if not verb:
        return VerbConjugation(word=infinitive), False

    # 1. Irregular / compound lookup
    if verb in _IRREGULAR_FORMS:
        return (
            VerbConjugation(
                word=verb,
                forms=_IRREGULAR_FORMS[verb],
                confidence=1.0,
                notes="irregular",
            ),
            True,
        )

    # 2. Regular -er
    if verb.endswith("er") and len(verb) > 2:
        return (
            VerbConjugation(
                word=verb,
                forms=_conjugate_er(verb),
                confidence=1.0,
                notes="regular -er",
            ),
            True,
        )

    # 3. Regular -ir (second group, with -iss-)
    if verb.endswith("ir") and len(verb) > 2:
        return (
            VerbConjugation(
                word=verb,
                forms=_conjugate_ir(verb),
                confidence=0.8,
                notes="regular -ir (assumed second group)",
            ),
            True,
        )

    # 4. Regular -re
    if verb.endswith("re") and len(verb) > 2:
        return (
            VerbConjugation(
                word=verb,
                forms=_conjugate_re(verb),
                confidence=0.8,
                notes="regular -re",
            ),
            True,
        )

    return VerbConjugation(word=verb), False


def is_known_irregular(infinitive: str) -> bool:
    """Return True if the verb is in the irregular / compound table."""
    return infinitive.strip() in _IRREGULAR_FORMS


def list_irregular_verbs() -> List[str]:
    """Return a sorted list of all irregular and compound verbs handled."""
    return sorted(_IRREGULAR_FORMS.keys())
