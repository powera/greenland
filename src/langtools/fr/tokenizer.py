"""French lemma-matching hooks for :mod:`langtools.tokenizer`.

``split_contractions`` expands elisions ("l'homme", "qu'il"), fused articles
("du", "aux") and inverted-subject hyphenation ("a-t-il", "dis-moi").
``candidate_lemmas`` reverses regular plural/gender agreement, regular verb
conjugation for the three groups and the common irregular verbs; verbs also
yield their pronominal lemma ("se lever", "s'asseoir"), since reflexive verbs
are stored that way.
"""

from typing import Dict, List, Tuple

from langtools.suffix_rules import (
    CandidateList,
    expand_endings,
    invert_paradigms,
    replace_last,
    strip_suffixes,
)

_ELISIONS: Dict[str, str] = {
    "l'": "le",
    "d'": "de",
    "j'": "je",
    "m'": "me",
    "t'": "te",
    "s'": "se",
    "n'": "ne",
    "c'": "ce",
    "qu'": "que",
    "jusqu'": "jusque",
    "lorsqu'": "lorsque",
    "puisqu'": "puisque",
    "quoiqu'": "quoique",
}

_CONTRACTIONS: Dict[str, Tuple[str, ...]] = {
    "au": ("à", "le"),
    "aux": ("à", "les"),
    "du": ("de", "le"),
    "des": ("de", "les"),
}

# Pronouns that may follow a verb after a hyphen ("dit-elle", "prends-le").
_HYPHEN_PRONOUNS = frozenset(
    "je tu il elle on nous vous ils elles moi toi lui leur le la les en y ce t".split()
)

_NOMINAL_RULES = expand_endings(
    [
        ("s x", ("",)),  # chats -> chat, jeux -> jeu
        ("e es", ("",)),  # grande -> grand
        ("aux", ("al", "ail")),  # chevaux -> cheval, travaux -> travail
        ("ive ives", ("if",)),  # active -> actif
        ("euse euses", ("eux", "eur")),  # heureuse -> heureux
        ("rice rices", ("eur",)),  # actrice -> acteur
        ("enne ennes", ("en",)),  # ancienne -> ancien
        ("onne onnes", ("on",)),  # bonne -> bon
        ("elle elles", ("el", "eau")),  # cruelle -> cruel, belle -> beau
        ("ette ettes", ("et",)),  # muette -> muet
        ("ère ères", ("er",)),  # première -> premier
        ("sse sses", ("s",)),  # grosse -> gros
        ("che ches", ("c",)),  # blanche -> blanc
        ("ement", ("e", "")),  # lentement -> lente/lent
        ("eusement", ("eux",)),  # heureusement -> heureux
        ("ément", ("é", "e")),  # énormément -> énorme
        ("amment", ("ant",)),  # constamment -> constant
        ("emment", ("ent",)),  # récemment -> récent
    ]
)

_VERB_RULES = expand_endings(
    [
        # First group (-er).
        ("e es", ("er",)),
        ("ent ons ez", ("er", "re", "ir")),
        ("ais ait aient ions iez", ("er", "re")),
        ("é ée és ées", ("er",)),
        ("ant", ("er", "re")),
        ("ai as a âmes âtes èrent asse assent ât", ("er",)),
        # Spelling that keeps a soft g/c or reflects a stem vowel change.
        ("geons geais geait geaient geant geâmes", ("ger",)),
        ("çons çais çait çaient çant çâmes", ("cer",)),
        ("elle elles ellent", ("eler",)),
        ("ette ettes ettent", ("eter",)),
        ("oie oies oient", ("oyer",)),
        ("uie uies uient", ("uyer",)),
        ("aie aies aient", ("ayer",)),
        # Second group (-ir, finir).
        ("is it i ie ies", ("ir",)),
        ("issons issez issent isse isses issions issiez", ("ir",)),
        ("issais issait issaient issant", ("ir",)),
        ("îmes îtes irent", ("ir", "re")),
        # Third group (-re, -oir).
        ("ds d", ("dre",)),  # vends/vend -> vendre
        ("u ue us ues", ("re", "oir", "ir")),  # vendu, voulu, venu
    ]
)

# Future and conditional endings attach to the infinitive ("-re" loses its e).
_FUTURE_ENDINGS = ("ai", "as", "a", "ons", "ez", "ont", "ais", "ait", "ions", "iez", "aient")

_IRREGULAR = invert_paradigms(
    {
        "être": "suis es est sommes êtes sont étais était étions étiez étaient fus fut "
        "furent serai sera serons seront serais serait seraient sois soit soyons soient "
        "été étant",
        "avoir": "ai as a avons avez ont avais avait avions aviez avaient eus eut eurent "
        "aurai aura aurons auront aurais aurait auraient aie aies ait ayons aient eu "
        "ayant",
        "aller": "vais vas va allons allez vont irai ira irons iront irais irait aille aillent",
        "faire": "fais fait faisons faites font faisais faisait fis fit firent ferai "
        "fera ferons feront ferais ferait fasse fassent",
        "dire": "dis dit disons dites disent disais disait dirent dise",
        "pouvoir": "peux peut pouvons pouvez peuvent pouvais pouvait pus put pourrai "
        "pourra pourrais pourrait puisse puissent pu",
        "vouloir": "veux veut voulons voulez veulent voulais voulait voudrai voudra "
        "voudrais voudrait veuille voulu",
        "savoir": "sais sait savons savez savent savais savait sus sut saurai saura "
        "saurais saurait sache sachent su sachant",
        "voir": "vois voit voyons voyez voient voyais voyait vis vit virent verrai verra "
        "verrais verrait voie vu vue",
        "venir": "viens vient venons venez viennent venais venait vins vint viendrai "
        "viendra viendrais viendrait vienne venu venue",
        "devoir": "dois doit devons devez doivent devais devait dus dut devrai devra "
        "devrais devrait doive dû due",
        "prendre": "prends prend prenons prenez prennent prenais prenait pris prit "
        "prendrai prendra prenne pris prise",
        "mettre": "mets met mettons mettez mettent mis mit mise",
        "asseoir": "assieds assied asseyons asseyez asseyent assis assise assises",
        "falloir": "faut fallait faudra faudrait fallu",
        "naître": "né née nés nées",
        "mourir": "meurt meurent mort morte",
        "ouvrir": "ouvert ouverte",
        "écrire": "écris écrit écrivons écrivez écrivent écrite",
        "lire": "lis lit lisons lisez lisent lu lue",
        "boire": "bois boit buvons buvez boivent bu",
    }
)


def split_contractions(token: str) -> List[str]:
    """Expand elisions, fused articles and hyphenated subject pronouns."""
    if "'" in token:
        head, _, rest = token.partition("'")
        expansion = _ELISIONS.get(head + "'")
        if expansion is not None:
            return [expansion, *split_contractions(rest)] if rest else [expansion]
        return [token]
    if token in _CONTRACTIONS:
        return list(_CONTRACTIONS[token])
    if "-" in token:
        parts = token.split("-")
        if parts[0] and len(parts) > 1 and all(part in _HYPHEN_PRONOUNS for part in parts[1:]):
            # The euphonic "t" of "a-t-il" is not a word.
            return [parts[0], *(part for part in parts[1:] if part != "t")]
    return [token]


def _is_infinitive(word: str) -> bool:
    return len(word) > 2 and word.endswith(("er", "ir", "re", "oir"))


def _stem_vowel_variants(infinitive: str) -> List[str]:
    """Undo the stressed-stem grave accent: lève -> lever, préfère -> préférer."""
    stem = infinitive[:-2]
    if "è" not in stem:
        return []
    ending = infinitive[-2:]
    return [replace_last(stem, "è", "e") + ending, replace_last(stem, "è", "é") + ending]


def _reflexive(infinitive: str) -> str:
    if infinitive[:1] in "aeiouyhéèêâîô":
        return "s'" + infinitive
    return "se " + infinitive


def candidate_lemmas(token: str) -> List[str]:
    """Guess French dictionary forms for a lowercased surface token."""
    candidates = CandidateList(token, min_length=2)
    candidates.extend(_IRREGULAR.get(token, ()))
    candidates.extend(strip_suffixes(token, _NOMINAL_RULES, min_stem=2))

    verbs: List[str] = list(_IRREGULAR.get(token, ()))
    for ending in _FUTURE_ENDINGS:
        stem = token[: -len(ending)]
        if token.endswith(ending) and len(stem) > 2 and stem.endswith("r"):
            verbs.append(stem if stem.endswith(("er", "ir")) else stem + "e")
    verbs.extend(strip_suffixes(token, _VERB_RULES, min_stem=2))
    expanded: List[str] = []
    for verb in verbs:
        if _is_infinitive(verb):
            expanded.append(verb)
            expanded.extend(_stem_vowel_variants(verb))
    candidates.extend(expanded)
    candidates.extend(_reflexive(verb) for verb in expanded)
    return candidates.as_list()
