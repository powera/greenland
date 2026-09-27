"""Spanish lemma-matching hooks for :mod:`langtools.tokenizer`.

``candidate_lemmas`` reverses regular noun/adjective plural and gender
agreement, regular verb conjugation (with stem-change and spelling-change
reversal), enclitic pronouns ("dámelo", "levantándose") and a table of the
common irregular verbs.  Verbs also yield their pronominal lemma ("quedarse"),
since reflexive verbs are stored that way.
"""

from typing import Dict, List, Tuple

from langtools.suffix_rules import (
    CandidateList,
    expand_endings,
    invert_paradigms,
    replace_last,
    strip_accents,
    strip_suffixes,
)

_CONTRACTIONS: Dict[str, Tuple[str, ...]] = {"del": ("de", "el"), "al": ("a", "el")}

_NOMINAL_RULES = expand_endings(
    [
        ("s es", ("",)),  # casas -> casa, flores -> flor
        ("ces", ("z",)),  # luces -> luz
        ("iones", ("ión",)),  # canciones -> canción
        ("ones", ("ón",)),  # ratones -> ratón
        ("eses", ("és",)),  # ingleses -> inglés
        ("anes", ("án",)),  # alemanes -> alemán
        ("ines", ("ín",)),  # jardines -> jardín
        ("a as os", ("o",)),  # bonita/bonitas -> bonito
        ("esa esas", ("és",)),  # francesa -> francés
        ("ora oras", ("or",)),  # trabajadora -> trabajador
        ("mente", ("",)),  # fácilmente -> fácil
        ("amente", ("o", "a")),  # rápidamente -> rápido
        ("ísimo ísima ísimos ísimas", ("o", "e")),  # carísimo -> caro
    ]
)

_AR = ("ar",)
_ER_IR = ("er", "ir")
_ANY = ("ar", "er", "ir")

_VERB_RULES = expand_endings(
    [
        # Present indicative / subjunctive.
        ("o", _ANY),
        ("as a amos áis an", _AR),
        ("es e en", ("er", "ir", "ar")),
        ("emos éis", ("er", "ar")),
        ("imos", ("ir", "er")),  # vivimos; comimos (preterite)
        ("ís", ("ir",)),
        # Preterite.
        ("é aste ó asteis aron", _AR),
        ("í iste ió isteis ieron", _ER_IR),
        # Imperfect.
        ("aba abas ábamos abais aban", _AR),
        ("ía ías íamos íais ían", _ER_IR),
        # Imperfect subjunctive.
        ("ara aras áramos arais aran ase ases ásemos aseis asen", _AR),
        ("iera ieras iéramos ierais ieran iese ieses iésemos ieseis iesen", _ER_IR),
        # Non-finite.
        ("ando", _AR),
        ("iendo yendo", _ER_IR),
        ("ado ada ados adas", _AR),
        ("ido ida idos idas", _ER_IR),
        # Spelling changes that keep the consonant sound.
        ("qué que ques quemos quéis quen", ("car",)),
        ("gué gue gues guemos guéis guen", ("gar",)),
        ("cé ce ces cemos céis cen", ("zar",)),
        ("zco zca zcas zcamos zcáis zcan", ("cer", "cir")),
        ("jo ja jas jamos jáis jan", ("ger", "gir")),
        ("go ga gas gamos gáis gan", ("guir",)),
    ]
)

# Future and conditional endings attach to the whole infinitive.
_FUTURE_ENDINGS = ("é", "ás", "á", "emos", "éis", "án", "ía", "ías", "íamos", "íais", "ían")

_INFINITIVE_ENDINGS = ("ar", "er", "ir", "ír")

_ENCLITICS = ("nos", "los", "las", "les", "me", "te", "se", "os", "lo", "la", "le")

_IRREGULAR = invert_paradigms(
    {
        "ser": "soy eres es somos sois son era eras éramos erais eran fui fuiste fue "
        "fuimos fuisteis fueron sea seas seamos seáis sean fuera fueras fueran "
        "sido siendo sé",
        "ir": "voy vas va vamos vais van iba ibas íbamos ibais iban fui fuiste fue "
        "fuimos fuisteis fueron vaya vayas vayamos vayan ido yendo ve",
        "estar": "estoy estás está están estuve estuviste estuvo estuvimos estuvieron "
        "esté estés estén",
        "haber": "he has ha hay hemos habéis han había habías habíamos habían hubo "
        "haya hayas hayamos hayan habrá habría",
        "tener": "tengo tienes tiene tenemos tienen tuve tuviste tuvo tuvimos tuvieron "
        "tenga tengas tengamos tengan tendré tendrá tendría ten",
        "hacer": "hago haces hace hacemos hacen hice hiciste hizo hicimos hicieron "
        "haga hagas hagamos hagan haré hará haría hecho haz",
        "poder": "puedo puedes puede podemos pueden pude pudiste pudo pudimos pudieron "
        "pueda puedas puedan podré podrá podría pudiendo",
        "decir": "digo dices dice decimos dicen dije dijiste dijo dijimos dijeron "
        "diga digas digamos digan diré dirá diría dicho diciendo di",
        "ver": "veo ves ve vemos veis ven vi viste vio vimos vieron vea veas veamos "
        "vean visto veía veías veíamos veían",
        "dar": "doy das da damos dais dan di diste dio dimos disteis dieron dé des demos den",
        "saber": "sé sabes sabe sabemos saben supe supiste supo supimos supieron sepa "
        "sepas sepamos sepan sabré sabrá sabría",
        "querer": "quiero quieres quiere queremos quieren quise quisiste quiso quisimos "
        "quisieron quiera quieras quieran querré querrá querría",
        "poner": "pongo pones pone ponemos ponen puse pusiste puso pusimos pusieron "
        "ponga pongas pongan pondré pondrá pondría puesto pon",
        "venir": "vengo vienes viene venimos vienen vine viniste vino vinimos vinieron "
        "venga vengas vengan vendré vendrá vendría viniendo ven",
        "salir": "salgo salga salgas salgan saldré saldrá saldría sal",
        "traer": "traigo traje trajiste trajo trajimos trajeron traiga traigan",
        "oír": "oigo oyes oye oímos oyen oyó oyeron oiga oigan",
        "morir": "muerto",
        "escribir": "escrito",
        "abrir": "abierto",
        "volver": "vuelto",
        "romper": "roto",
    }
)


def split_contractions(token: str) -> List[str]:
    """Expand "del"/"al"; return ``[token]`` otherwise."""
    return list(_CONTRACTIONS.get(token, (token,)))


def _is_infinitive(word: str) -> bool:
    return len(word) > 3 and word.endswith(_INFINITIVE_ENDINGS)


def _stem_change_variants(infinitive: str) -> List[str]:
    """Undo boot-verb diphthongs in the stem: quier- -> quer-, pued- -> pod-."""
    stem, ending = infinitive[:-2], infinitive[-2:]
    variants: List[str] = []
    for old, new in (("ie", "e"), ("ue", "o"), ("ue", "u"), ("i", "e")):
        if old in stem:
            variants.append(replace_last(stem, old, new) + ending)
    return variants


def _verb_candidates(word: str) -> List[str]:
    """Infinitives a conjugated form could come from (before stem changes)."""
    infinitives: List[str] = []
    for ending in _FUTURE_ENDINGS:
        if word.endswith(ending) and _is_infinitive(word[: -len(ending)]):
            infinitives.append(word[: -len(ending)])
    infinitives.extend(strip_suffixes(word, _VERB_RULES, min_stem=2))
    expanded: List[str] = []
    for infinitive in infinitives:
        expanded.append(infinitive)
        expanded.extend(_stem_change_variants(infinitive))
    return expanded


def _enclitic_hosts(word: str) -> List[str]:
    """Verb forms left after removing up to two attached object pronouns.

    Only hosts that look verbal are kept -- an infinitive, a gerund, or a form
    that needed a written accent to hold its stress -- so nouns that merely end
    in "-la" or "-se" ("escuela", "clase") are not split.
    """
    hosts: List[str] = []
    current = word
    for _ in range(2):
        clitic = next((c for c in _ENCLITICS if current.endswith(c)), None)
        if clitic is None or len(current) - len(clitic) < 3:
            break
        host = current[: -len(clitic)]
        plain = strip_accents(host)
        if _is_infinitive(plain) or plain.endswith(("ando", "iendo")) or plain != host:
            hosts.append(plain)
        current = host
    return hosts


def candidate_lemmas(token: str) -> List[str]:
    """Guess Spanish dictionary forms for a lowercased surface token."""
    candidates = CandidateList(token, min_length=2)
    candidates.extend(_IRREGULAR.get(token, ()))

    candidates.extend(strip_suffixes(token, _NOMINAL_RULES, min_stem=2))
    # Plural "-es" can move the written stress: jóvenes -> joven.
    if token.endswith("es") and strip_accents(token[:-2]) != token[:-2]:
        candidates.add(strip_accents(token[:-2]))

    verbs = list(_IRREGULAR.get(token, ()))
    verbs.extend(_verb_candidates(token))
    for host in _enclitic_hosts(token):
        if _is_infinitive(host):
            verbs.append(host)
        verbs.extend(_verb_candidates(host))
    verbs = [verb for verb in verbs if _is_infinitive(verb)]
    candidates.extend(verbs)
    # Pronominal verbs are stored with "-se" attached.
    candidates.extend(verb + "se" for verb in verbs)
    return candidates.as_list()
