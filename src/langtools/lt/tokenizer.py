"""Lithuanian lemma-matching hooks for :mod:`langtools.tokenizer`.

Lithuanian running text rarely shows a bare lemma: nouns and adjectives carry
seven cases in two numbers, and verbs conjugate for person, tense and mood with
reflexive "-si" attached and negation "ne-" fused on.  ``candidate_lemmas``
reverses the regular declension classes (-as, -is/-ys, -ias, -us, -ius, -a,
-ia, -ė, i-stems, -uo), adjective agreement and comparison, adverbs in
"-(i)ai", and verb forms back to the "-ti" / "-tis" infinitive.

Verb stems differ between infinitive, present and past ("rašyti" / "rašo" /
"rašė"), and the present stem alone does not say which infinitive class it came
from, so each stripped stem is offered with every common infinitive suffix.
"""

from typing import List

from langtools.lt.utils import remove_stress_marks
from langtools.suffix_rules import (
    CandidateList,
    expand_endings,
    invert_paradigms,
    replace_last,
    strip_suffixes,
)

_NOMINAL_RULES = expand_endings(
    [
        # -as (vyras, geras): o ui ą u e ai ų ams us ais uose; adjectives am ame i iems.
        ("o u e ams ais am ame", ("as",)),
        ("ui", ("as", "us", "is")),
        ("ą", ("as", "a")),
        ("ai", ("as", "a", "us")),
        ("ų", ("as", "a", "ė", "us", "is", "uo")),
        ("us", ("as",)),
        ("uose", ("as", "us", "is")),
        ("i iems", ("as", "us", "is")),
        # -is / -ys / -ias (brolis, žodis, kelias): io iui į iu yje y iai ių iams ius iais iuose.
        ("io iu", ("is", "ys", "ias", "ius")),
        ("iui iams iais iuose", ("is", "ys", "ias", "ius", "us")),
        ("į yje y", ("is", "ys")),
        ("ių", ("is", "ys", "ius", "ias", "ia", "ė", "us")),
        ("ius", ("is", "ys", "ias")),
        ("iai", ("is", "ys", "ias", "ius", "ia", "us")),
        # -a (ranka): os ai ą a oje os ų oms as omis ose.
        ("os oje oms omis ose", ("a", "as")),
        ("as", ("a",)),
        # -ia (vyšnia, gražus fem.): ios iai ią ia ioje ioms ias iomis iose.
        ("ios ią ioje ioms iomis iose", ("ia", "ė", "us", "is")),
        ("ias", ("ia",)),
        ("iam iame", ("us",)),  # gražiam, gražiame
        # -ė (upė): ės ei ę e ėje ėms es ėmis ėse.
        ("ės ei ę ėje ėms es ėmis ėse", ("ė",)),
        ("e", ("ė",)),
        # -us / -ius (sūnus, gražus): aus umi uje ūs ums umis; iaus iumi iuje.
        ("aus umi uje ūs ums umis", ("us",)),
        ("iaus iumi iuje", ("ius",)),
        # i-stems (naktis, širdis): ies imi ys ims imis yse.
        ("ies imi ims imis yse", ("is",)),
        ("ys", ("is",)),
        # -uo (akmuo, vanduo): ens enį eniui eniu enyje enys enų enims enimis enyse.
        ("ens enį eniui eniu enyje enys enų enims enimis enyse", ("uo",)),
        # Adverbs from adjectives: gerai -> geras, gražiai -> gražus; geriau.
        ("iau", ("as", "us")),
    ]
)

# Comparative "-esn-" and superlative "-iaus-" sit between stem and ending:
# geresnis, geresnio, gražiausias, gražiausios.
_COMPARISON_INFIXES = ("esn", "iaus")

_INFINITIVE_SUFFIXES = ("ti", "yti", "ėti", "oti")

_VERB_RULES = expand_endings(
    [
        # Present: dirba/dirbu/dirbi/dirbame/dirbate, myli/myliu, rašo/rašau.
        ("a u ame ate am at", _INFINITIVE_SUFFIXES),
        ("i ime ite im it iu ia iame iate", _INFINITIVE_SUFFIXES),
        ("o au ai ome ote om ot", _INFINITIVE_SUFFIXES),
        # Past: dirbo, rašė/rašėme/rašėte, mylėjo, dirbau, rašiau.
        ("ė ėme ėte ėm ėt iau ei", _INFINITIVE_SUFFIXES),
        ("ėjo ėjau ėjai ėjome ėjote", ("ėti",)),
        # -uoti / -auti verbs: dainuoja, dainavo, keliauja.
        ("uoja uoju uoji uojame uojate", ("uoti",)),
        ("avo avau avai avome avote", ("uoti", "auti")),
        ("auja auju auji aujame aujate", ("auti",)),
        ("oja oju oji ojame ojate", ("oti",)),
        ("ėja ėju ėji ėjame ėjate", ("ėti",)),
        ("ija iju iji ijame ijate", ("yti", "ti")),
        # Future: dirbs, rašys, kalbės, dirbsiu, dirbsime.
        ("s siu si sime site sim sit", ("ti",)),
        # Frequentative past: dirbdavo.
        ("davo davau davai davome davote", ("ti",)),
        # Conditional: dirbtų, dirbčiau, dirbtume.
        ("tų čiau tum tume tumėte tumėm tumei tute", ("ti",)),
        # Imperative: dirbk, dirbkite, dirbkime.
        ("k kite kime kit kim", ("ti",)),
        # Participles and gerunds: dirbdamas, parašytas, dirbęs, dirbant.
        ("damas dama dami damos", ("ti",)),
        ("tas ta ti tos tą tus to", ("ti",)),
        ("ęs usi ę", ("ti",)),
        ("ant ančio antis", ("ti", "ėti")),
        ("int inčio intis", ("ėti", "yti")),
    ]
)

# Verbal prefixes.  Every matching prefix is tried ("pra-" and "pa-" both match
# "pramatė"); the lookup decides which reading names a stored verb.
_VERB_PREFIXES = tuple("api ati at ap iš į nu pa par pra pri per su už be".split())

_REFLEXIVE_ENDINGS = (
    # (reflexive ending, non-reflexive ending): mokausi -> mokau, juokiasi -> juokia.
    ("uosi", "u"),
    ("iesi", "i"),
    ("amės", "ame"),
    ("atės", "ate"),
    ("omės", "ome"),
    ("otės", "ote"),
    ("imės", "ime"),
    ("itės", "ite"),
    ("ėmės", "ėme"),
    ("ėtės", "ėte"),
    ("kitės", "kite"),
    ("si", ""),
)

_IRREGULAR = invert_paradigms(
    {
        "būti": "esu esi yra esame esate buvo buvau buvai buvome buvote bus būsiu "
        "būsi būsime būtų buvęs buvusi nėra nesu nebuvo nebus",
        "eiti": "einu eini eina einame einate ėjo ėjau ėjai ėjome eis eisiu eik eikite "
        "einant ėjęs",
        "duoti": "duodu duodi duoda duodame davė daviau davei davėme duos duok",
        "imti": "imu imi ima ėmė ėmiau ims imk",
        "gauti": "gaunu gauni gauna gavo gavau gaus",
        "dėti": "dedu dedi deda dėjo",
        "reikėti": "reikia reikėjo reikės",
        "galėti": "galiu gali galime galite galėjo galės",
        "norėti": "noriu nori norime norite norėjo norės",
        "turėti": "turiu turi turime turite turėjo turės",
        "žinoti": "žinau žinai žino žinome žinote žinojo žinos",
        "matyti": "matau matai mato matome matote matė mačiau matys",
        "gyventi": "gyvenu gyveni gyvena gyvename gyveno",
        "valgyti": "valgau valgai valgo valgome valgė valgys",
        "gerti": "geriu geri geria geriame gėrė gėriau gers",
        "sakyti": "sakau sakai sako sakome sakė sakiau sakys",
        "daryti": "darau darai daro darome darė dariau darys",
        "žmogus": "žmogaus žmogui žmogų žmogumi žmoguje žmonės žmonių žmonėms žmones "
        "žmonėmis žmonėse",
        "sesuo": "sesers seseriai seserį seseria seseryje seserys seserų",
        "duktė": "dukters dukteriai dukterį dukteria dukteryje dukterys dukterų",
    }
)


def _depalatalize(candidate: str) -> List[str]:
    """Undo palatalization before -i- endings: kačių -> katė, žodžio -> žodis."""
    variants: List[str] = []
    if "dž" in candidate:
        variants.append(replace_last(candidate, "dž", "d"))
    if "č" in candidate:
        variants.append(replace_last(candidate, "č", "t"))
    return variants


def _nominal_candidates(word: str) -> List[str]:
    out = strip_suffixes(word, _NOMINAL_RULES, min_stem=2)
    for infix in _COMPARISON_INFIXES:
        index = word.rfind(infix)
        if index >= 2:
            stem = word[:index]
            # geresnis -> geras; gražiausias -> gražus (the "i" belongs to -iaus-).
            out.extend([stem + "as", stem + "us", stem + "is"])
    return out


def _verb_candidates(word: str) -> List[str]:
    verbs = strip_suffixes(word, _VERB_RULES, min_stem=2)
    verbs.extend(lemma for lemma in _IRREGULAR.get(word, ()) if lemma.endswith("ti"))
    out: List[str] = []
    for verb in verbs:
        if not verb.endswith("ti") or len(verb) <= 3:
            continue
        # A t/d stem turns to s before the infinitive "-ti": jautė -> jausti,
        # vedė -> vesti.
        if verb.endswith(("tti", "dti")):
            out.append(verb[:-3] + "sti")
        out.append(verb)
    return out


def _reflexive_candidates(word: str) -> List[str]:
    """Reflexive infinitives ("-tis") behind a reflexive form ("mokausi")."""
    out: List[str] = []
    for reflexive, plain in _REFLEXIVE_ENDINGS:
        if word.endswith(reflexive) and len(word) - len(reflexive) >= 3:
            base = word[: -len(reflexive)] + plain
            out.extend(verb + "s" for verb in _verb_candidates(base))
            if base.endswith("ti"):
                out.append(base + "s")
    return out


def _prefixed_verb_candidates(word: str) -> List[str]:
    """Verbs behind a prefixed form, with and without the prefix.

    Reflexive prefixed verbs carry "-si-" after the prefix instead of "-s" at
    the end (nusipirko -> nusipirkti), and the unprefixed verb is offered too
    because the dictionary often stores only the simplex (nupirko -> pirkti).
    """
    out: List[str] = []
    for prefix in _VERB_PREFIXES:
        rest = word[len(prefix) :]
        if not word.startswith(prefix) or len(rest) < 4:
            continue
        reflexive = rest.startswith("si") and len(rest) >= 6
        inner = rest[2:] if reflexive else rest
        for verb in _verb_candidates(inner):
            out.append(prefix + ("si" if reflexive else "") + verb)
            out.append(verb)
    return out


def candidate_lemmas(token: str) -> List[str]:
    """Guess Lithuanian dictionary forms for a lowercased surface token."""
    word = remove_stress_marks(token)
    candidates = CandidateList(token, min_length=2)
    if word != token:
        candidates.add(word)
    candidates.extend(_IRREGULAR.get(word, ()))

    for candidate in _nominal_candidates(word):
        candidates.add(candidate)
        candidates.extend(_depalatalize(candidate))

    # Negation is written onto the verb: nedirba -> dirba -> dirbti.
    forms = [word]
    if word.startswith("ne") and len(word) >= 5:
        forms.append(word[2:])
    for form in forms:
        candidates.extend(_IRREGULAR.get(form, ()))
        verbs = _verb_candidates(form) + _reflexive_candidates(form)
        verbs.extend(_prefixed_verb_candidates(form))
        for verb in verbs:
            candidates.add(verb)
            candidates.extend(_depalatalize(verb))
    return candidates.as_list()
