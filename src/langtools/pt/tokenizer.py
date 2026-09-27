"""Portuguese lemma-matching hooks for :mod:`langtools.tokenizer`.

``split_contractions`` expands preposition + article/demonstrative fusions
("do", "na", "pelo", "neste") and hyphenated clitics ("levantou-se").
``candidate_lemmas`` reverses regular plural/gender agreement, regular verb
conjugation and the common irregular verbs; verbs also yield their pronominal
lemma ("levantar-se"), since reflexive verbs are stored that way.
"""

from typing import Dict, List, Tuple

from langtools.suffix_rules import (
    CandidateList,
    expand_endings,
    invert_paradigms,
    strip_suffixes,
)


def _build_contractions() -> Dict[str, Tuple[str, ...]]:
    table: Dict[str, Tuple[str, ...]] = {
        "ao": ("a", "o"),
        "aos": ("a", "os"),
        "à": ("a", "a"),
        "às": ("a", "as"),
        "num": ("em", "um"),
        "numa": ("em", "uma"),
        "nuns": ("em", "uns"),
        "numas": ("em", "umas"),
        "dum": ("de", "um"),
        "duma": ("de", "uma"),
        "pelo": ("por", "o"),
        "pela": ("por", "a"),
        "pelos": ("por", "os"),
        "pelas": ("por", "as"),
    }
    for article in ("o", "a", "os", "as"):
        table["d" + article] = ("de", article)
        table["n" + article] = ("em", article)
    for demonstrative in (
        "este esta estes estas isto esse essa esses essas isso "
        "aquele aquela aqueles aquelas aquilo ele ela eles elas"
    ).split():
        table["d" + demonstrative] = ("de", demonstrative)
        table["n" + demonstrative] = ("em", demonstrative)
    return table


_CONTRACTIONS = _build_contractions()

# Clitic pronouns written after a hyphen ("chama-se", "diga-me").
_HYPHEN_CLITICS = frozenset(
    "se me te nos vos o a os as lo la los las no na nos nas lhe lhes".split()
)

_NOMINAL_RULES = expand_endings(
    [
        ("s es", ("",)),  # casas -> casa, flores -> flor
        ("ões ães ãos", ("ão",)),  # canções -> canção
        ("ais", ("al",)),  # animais -> animal
        ("éis", ("el",)),  # papéis -> papel
        ("eis", ("il", "el")),  # fáceis -> fácil
        ("óis", ("ol",)),  # anzóis -> anzol
        ("uis", ("ul",)),
        ("is", ("il",)),  # funis -> funil
        ("ns", ("m",)),  # homens -> homem
        ("a as os", ("o",)),  # bonita -> bonito
        ("esa esas eses", ("ês",)),  # portuguesa -> português
        ("ora oras", ("or",)),  # professora -> professor
        ("mente", ("",)),  # facilmente -> fácil (accent lost; see below)
        ("amente", ("o", "a")),  # rapidamente -> rápido (ditto)
    ]
)

_AR = ("ar",)
_ER_IR = ("er", "ir")

_VERB_RULES = expand_endings(
    [
        # Present indicative / subjunctive.
        ("o", ("ar", "er", "ir")),
        ("as a amos ais am", _AR),
        ("es e em", ("er", "ir", "ar")),
        ("emos eis", ("er", "ar")),
        ("imos is", ("ir",)),
        # Preterite.
        ("ei aste ou astes aram", _AR),
        ("i", _ER_IR),
        ("este eu estes eram", ("er",)),
        ("iste iu istes iram", ("ir",)),
        # Imperfect.
        ("ava avas ávamos áveis avam", _AR),
        ("ia ias íamos íeis iam", _ER_IR),
        # Imperfect subjunctive.
        ("asse asses ássemos ásseis assem", _AR),
        ("esse esses êssemos êsseis essem", ("er",)),
        ("isse isses íssemos ísseis issem", ("ir",)),
        # Non-finite.
        ("ando", _AR),
        ("endo", ("er",)),
        ("indo", ("ir",)),
        ("ado ada ados adas", _AR),
        ("ido ida idos idas", _ER_IR),
        # Spelling changes that keep the consonant sound.
        ("quei que ques quem", ("car",)),
        ("guei gue gues guem", ("gar",)),
        ("cei ce ces cem", ("çar",)),
        ("ço ça ças çamos çam", ("cer", "çar")),
        ("jo ja jas jamos jam", ("ger", "gir")),
    ]
)

# Future and conditional endings attach to the whole infinitive.
_FUTURE_ENDINGS = ("ei", "ás", "á", "emos", "eis", "ão", "ia", "ias", "íamos", "íeis", "iam")

_INFINITIVE_ENDINGS = ("ar", "er", "ir", "or")

_IRREGULAR = invert_paradigms(
    {
        "ser": "sou és é somos são era eras éramos eram fui foi fomos foram seja "
        "sejam fosse fossem sido sendo",
        "ir": "vou vais vai vamos vão ia iam fui foi fomos foram vá vão fosse fossem ido",
        "estar": "estou está estás estão estive esteve estivemos estiveram esteja estejam",
        "ter": "tenho tens tem temos têm tinha tinham tive teve tivemos tiveram tenha "
        "tenham tido",
        "haver": "há hei havia houve haja",
        "fazer": "faço faz fazemos fazem fiz fez fizemos fizeram faça façam farei fará "
        "faria feito",
        "poder": "posso pode podemos podem pude pôde pudemos puderam possa possam",
        "dizer": "digo diz dizemos dizem disse dissemos disseram diga digam direi dirá "
        "diria dito",
        "ver": "vejo vê vemos veem vi viu vimos viram veja vejam visto",
        "vir": "venho vens vem vimos vêm vim veio viemos vieram venha venham vindo",
        "dar": "dou dás dá damos dão dei deu demos deram dê deem",
        "saber": "sei sabe sabemos sabem soube souberam saiba saibam",
        "querer": "quero quer queremos querem quis quiseram queira queiram",
        "pôr": "ponho põe pomos põem pus pôs puseram ponha posto",
        "trazer": "trago traz trouxe trouxeram traga trarei trará",
        "escrever": "escrito",
        "abrir": "aberto",
    }
)


def split_contractions(token: str) -> List[str]:
    """Expand fused prepositions and hyphenated clitics."""
    if token in _CONTRACTIONS:
        return list(_CONTRACTIONS[token])
    if "-" in token:
        parts = token.split("-")
        if len(parts) > 1 and all(part in _HYPHEN_CLITICS for part in parts[1:]) and parts[0]:
            return parts
    return [token]


def _is_infinitive(word: str) -> bool:
    return len(word) > 2 and word.endswith(_INFINITIVE_ENDINGS)


def candidate_lemmas(token: str) -> List[str]:
    """Guess Portuguese dictionary forms for a lowercased surface token."""
    candidates = CandidateList(token, min_length=2)
    candidates.extend(_IRREGULAR.get(token, ()))
    candidates.extend(strip_suffixes(token, _NOMINAL_RULES, min_stem=2))

    verbs: List[str] = []
    for ending in _FUTURE_ENDINGS:
        if token.endswith(ending) and _is_infinitive(token[: -len(ending)]):
            verbs.append(token[: -len(ending)])
    verbs.extend(strip_suffixes(token, _VERB_RULES, min_stem=2))
    verbs.extend(lemma for lemma in _IRREGULAR.get(token, ()) if _is_infinitive(lemma))
    verbs = [verb for verb in verbs if _is_infinitive(verb)]
    candidates.extend(verbs)
    # Pronominal verbs are stored with a hyphenated "-se".
    candidates.extend(verb + "-se" for verb in verbs)
    return candidates.as_list()
