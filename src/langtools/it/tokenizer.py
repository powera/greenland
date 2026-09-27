"""Italian lemma-matching hooks for :mod:`langtools.tokenizer`.

``split_contractions`` expands elisions ("l'acqua", "dell'anno") and
articulated prepositions ("della", "nei").  ``candidate_lemmas`` reverses
regular plural/gender agreement, regular verb conjugation, enclitic pronouns
("alzarmi", "dicendolo") and the common irregular verbs; verbs also yield their
reflexive lemma ("svegliarsi"), since reflexive verbs are stored that way.
"""

from typing import Dict, List, Tuple

from langtools.suffix_rules import (
    CandidateList,
    expand_endings,
    invert_paradigms,
    strip_suffixes,
)

# Elided forms, keyed with their apostrophe.
_ELISIONS: Dict[str, Tuple[str, ...]] = {
    "l'": ("lo",),
    "un'": ("una",),
    "c'": ("ci",),
    "d'": ("di",),
    "m'": ("mi",),
    "t'": ("ti",),
    "s'": ("si",),
    "v'": ("vi",),
    "n'": ("ne",),
    "quest'": ("questo",),
    "quell'": ("quello",),
    "bell'": ("bello",),
    "sant'": ("santo",),
    "com'": ("come",),
    "dov'": ("dove",),
    "cos'": ("cosa",),
    "anch'": ("anche",),
    "tutt'": ("tutto",),
}

_PREPOSITION_STEMS: Tuple[Tuple[str, str], ...] = (
    ("di", "de"),
    ("a", "a"),
    ("da", "da"),
    ("in", "ne"),
    ("su", "su"),
)

_ARTICLE_TAILS: Tuple[Tuple[str, str], ...] = (
    ("l", "il"),
    ("llo", "lo"),
    ("lla", "la"),
    ("i", "i"),
    ("gli", "gli"),
    ("lle", "le"),
)


_CONTRACTIONS: Dict[str, Tuple[str, ...]] = {"col": ("con", "il"), "coi": ("con", "i")}
for _preposition, _stem in _PREPOSITION_STEMS:
    for _tail, _article in _ARTICLE_TAILS:
        _CONTRACTIONS[_stem + _tail] = (_preposition, _article)
    # Elided before a vowel: dell', all', nell'.
    _ELISIONS[_stem + "ll'"] = (_preposition, "lo")

_NOMINAL_RULES = expand_endings(
    [
        ("i", ("o", "e", "a")),  # libri -> libro, fiori -> fiore, problemi -> problema
        ("e", ("a", "o")),  # case -> casa, belle -> bella/bello
        ("a", ("o",)),  # bella -> bello
        ("chi", ("co",)),  # tedeschi -> tedesco
        ("che", ("ca",)),  # amiche -> amica
        ("ghi", ("go",)),  # laghi -> lago
        ("ghe", ("ga",)),  # righe -> riga
        ("issimo issima issimi issime", ("o", "e")),  # bellissimo -> bello
        ("amente", ("o",)),  # rapidamente -> rapido
        ("lmente", ("le",)),  # facilmente -> facile
        ("rmente", ("re",)),  # regolarmente -> regolare
        ("emente", ("e",)),  # dolcemente -> dolce
    ]
)

_ARE = ("are",)
_ERE = ("ere",)
_IRE = ("ire",)

_VERB_RULES = expand_endings(
    [
        # Present indicative / subjunctive.
        ("o i", ("are", "ere", "ire")),
        ("iamo", ("are", "ere", "ire")),
        ("a ate ano", _ARE),
        ("e ono", ("ere", "ire")),
        ("ete", _ERE),
        ("ite", _IRE),
        ("iate ino", _ARE),
        ("isco isci isce iscono isca iscano", _IRE),
        # Imperfect.
        ("avo avi ava avamo avate avano", _ARE),
        ("evo evi eva evamo evate evano", _ERE),
        ("ivo ivi iva ivamo ivate ivano", _IRE),
        # Passato remoto.
        ("ai asti ò ammo aste arono", _ARE),
        ("ei esti é è emmo este erono etti ette ettero", _ERE),
        ("ii isti ì immo iste irono", _IRE),
        # Future and conditional: -are verbs switch to -er- here too.
        ("erò erai erà eremo erete eranno", ("are", "ere")),
        ("erei eresti erebbe eremmo ereste erebbero", ("are", "ere")),
        ("irò irai irà iremo irete iranno", _IRE),
        ("irei iresti irebbe iremmo ireste irebbero", _IRE),
        # Imperfect subjunctive.
        ("assi asse assimo assero", _ARE),
        ("essi esse essimo essero", _ERE),
        ("issi isse issimo issero", _IRE),
        # Non-finite.
        ("ando", _ARE),
        ("endo", ("ere", "ire")),
        ("ato ata ati", _ARE),
        ("uto uta uti ute", _ERE),
        ("ito ita iti", _IRE),
    ]
)

# Attached object pronouns, longest first so "glielo" beats "lo".
_ENCLITICS = tuple(
    sorted(
        (
            "glielo gliela glieli gliele gliene melo mela meli mele telo tela teli tele "
            "selo sela seli sele cene sene mene tene vene "
            "mi ti si ci vi lo la li le gli ne"
        ).split(),
        key=len,
        reverse=True,
    )
)

_IRREGULAR = invert_paradigms(
    {
        "essere": "sono sei è siamo siete ero eri era eravamo eravate erano fui fu "
        "fummo furono sarò sarai sarà saremo sarete saranno sarei sarebbe sia siano "
        "fosse fossero stato stata stati state",
        "avere": "ho hai ha abbiamo avete hanno ebbi ebbe ebbero avrò avrà avremo "
        "avranno avrei avrebbe abbia abbiano",
        "andare": "vado vai va vanno vada vadano andrò andrà andrei andrebbe",
        "fare": "faccio fai fa facciamo fate fanno feci fece fecero farò farà farei "
        "farebbe faccia facciano fatto fatta facendo",
        "stare": "sto stai sta stanno stetti stette stettero starò starà stia stiano",
        "dire": "dico dici dice diciamo dite dicono dissi disse dissero dirò dirà dica "
        "dicano detto detta dicendo",
        "potere": "posso puoi può possiamo potete possono potrò potrà potrei potrebbe "
        "possa possano",
        "volere": "voglio vuoi vuole vogliamo volete vogliono volli volle vorrò vorrà "
        "vorrei vorrebbe voglia vogliano",
        "dovere": "devo devi deve dobbiamo dovete devono dovrò dovrà dovrei dovrebbe "
        "debba debbano",
        "venire": "vengo vieni viene veniamo venite vengono venni venne vennero verrò "
        "verrà verrei venga vengano venuto venuta",
        "sapere": "so sai sa sappiamo sapete sanno seppi seppe saprò saprà sappia",
        "dare": "do dai dà diamo date danno diedi diede diedero darò darà dia diano",
        "uscire": "esco esci esce escono esca escano",
        "vedere": "vidi vide videro vedrò vedrà visto vista",
        "prendere": "presi prese presero preso presa",
        "mettere": "misi mise misero messo messa",
        "scrivere": "scrissi scrisse scrissero scritto scritta",
        "leggere": "lessi lesse lessero letto letta",
        "aprire": "aperto aperta",
    }
)


def split_contractions(token: str) -> List[str]:
    """Expand elisions and articulated prepositions."""
    if "'" in token:
        head, _, rest = token.partition("'")
        expansion = _ELISIONS.get(head + "'")
        if expansion is not None:
            return [*expansion, rest] if rest else list(expansion)
        return [token]
    return list(_CONTRACTIONS.get(token, (token,)))


def _is_infinitive(word: str) -> bool:
    return len(word) > 4 and word.endswith(("are", "ere", "ire", "rre"))


def _fix_spelling(infinitive: str) -> List[str]:
    """Undo spelling inserted to keep a hard or soft consonant.

    "cerch-" + "are" -> "cercare"; "mang-" + "are" -> "mangiare" (the "i" of
    "mangiare" drops before endings starting with i/e).
    """
    if infinitive.endswith(("chare", "ghare")):
        return [infinitive[:-5] + infinitive[-5] + "are"]
    if infinitive.endswith(("care", "gare")):
        return [infinitive, infinitive[:-3] + "iare"]
    return [infinitive]


def _verb_candidates(word: str) -> List[str]:
    out: List[str] = []
    for infinitive in strip_suffixes(word, _VERB_RULES, min_stem=2):
        out.extend(_fix_spelling(infinitive))
    return out


def _enclitic_hosts(word: str) -> List[str]:
    """Infinitives / gerunds left after removing an attached pronoun."""
    for clitic in _ENCLITICS:
        if not word.endswith(clitic):
            continue
        host = word[: -len(clitic)]
        if host.endswith(("ar", "er", "ir")) and len(host) > 3:
            # Infinitives drop their final "-e": alzar+mi.
            return [host + "e"]
        if host.endswith(("ando", "endo")):
            return [host]
    return []


def candidate_lemmas(token: str) -> List[str]:
    """Guess Italian dictionary forms for a lowercased surface token."""
    candidates = CandidateList(token, min_length=2)
    candidates.extend(_IRREGULAR.get(token, ()))
    candidates.extend(strip_suffixes(token, _NOMINAL_RULES, min_stem=2))

    verbs: List[str] = list(_IRREGULAR.get(token, ()))
    verbs.extend(_verb_candidates(token))
    for host in _enclitic_hosts(token):
        verbs.append(host)
        verbs.extend(_verb_candidates(host))
    verbs = [verb for verb in verbs if _is_infinitive(verb)]
    candidates.extend(verbs)
    # Reflexive verbs are stored with "-si" replacing the final "-e".
    candidates.extend(verb[:-1] + "si" for verb in verbs)
    return candidates.as_list()
