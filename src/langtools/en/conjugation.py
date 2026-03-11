"""Programmatic English verb conjugation expansion.

English verbs are highly regular in their person/tense inflection: past and
future tenses do not change by person, and present tense only distinguishes
3rd-person singular from the base form.  The only verb that is truly
person-irregular across tenses is "to be".

This module provides :func:`expand_verb_forms` which takes the canonical
base forms stored in the database and expands them to the full set of
person/tense forms expected by the ``VERB_FORM_MAPPING`` in
:mod:`langtools.en.llm_forms`, eliminating the need for an LLM call to
produce the remaining forms.

Only three base forms truly require LLM / Wiktionary data: ``infinitive``,
``past``, and ``past_participle``.  The ``3s_present`` and
``present_participle`` are generated from the infinitive via spelling rules
when not supplied explicitly.
"""

from typing import Dict, Optional, TypedDict

from langtools.en.utils import generate_3s_present, generate_past_tense, generate_present_participle

# ---------------------------------------------------------------------------
# Irregular conjugations keyed by infinitive.
#
# Each entry maps every person/tense key used by VERB_FORM_MAPPING to the
# correct surface form.  Only verbs whose person-inflection cannot be derived
# from the base forms need to appear here.
# ---------------------------------------------------------------------------


class IrregularBaseForms(TypedDict, total=False):
    """Base forms for irregular verbs needing mechanical overrides."""

    past: str
    past_participle: str
    third_singular_present: str
    present_participle: str


def _build_uniform_irregular_conjugation(
    infinitive: str, forms: IrregularBaseForms
) -> Dict[str, str]:
    """Build a full person/tense table for a non-"be" irregular verb."""
    past = forms["past"]
    past_participle = forms.get("past_participle", past)
    third_singular_present = forms.get("third_singular_present", generate_3s_present(infinitive))
    present_participle = forms.get("present_participle", generate_present_participle(infinitive))
    future_form = f"will {infinitive}"

    return {
        "infinitive": infinitive,
        "1s_present": infinitive,
        "2s_present": infinitive,
        "3s_present": third_singular_present,
        "1p_present": infinitive,
        "2p_present": infinitive,
        "3p_present": infinitive,
        "1s_past": past,
        "2s_past": past,
        "3s_past": past,
        "1p_past": past,
        "2p_past": past,
        "3p_past": past,
        "1s_future": future_form,
        "2s_future": future_form,
        "3s_future": future_form,
        "1p_future": future_form,
        "2p_future": future_form,
        "3p_future": future_form,
        "2s_imp": infinitive,
        "2p_imp": infinitive,
        "present_participle": present_participle,
        "past_participle": past_participle,
    }


IRREGULAR_CONJUGATIONS: Dict[str, Dict[str, str]] = {
    "be": {
        "infinitive": "be",
        "1s_present": "am",
        "2s_present": "are",
        "3s_present": "is",
        "1p_present": "are",
        "2p_present": "are",
        "3p_present": "are",
        "1s_past": "was",
        "2s_past": "were",
        "3s_past": "was",
        "1p_past": "were",
        "2p_past": "were",
        "3p_past": "were",
        "1s_future": "will be",
        "2s_future": "will be",
        "3s_future": "will be",
        "1p_future": "will be",
        "2p_future": "will be",
        "3p_future": "will be",
        "2s_imp": "be",
        "2p_imp": "be",
        "present_participle": "being",
        "past_participle": "been",
    },
}

IRREGULAR_BASE_FORMS: Dict[str, IrregularBaseForms] = {
    "begin": {"past": "began", "past_participle": "begun"},
    "break": {"past": "broke", "past_participle": "broken"},
    "bring": {"past": "brought"},
    "build": {"past": "built"},
    "buy": {"past": "bought"},
    "choose": {"past": "chose", "past_participle": "chosen"},
    "come": {"past": "came", "past_participle": "come"},
    "do": {"past": "did", "past_participle": "done", "third_singular_present": "does"},
    "drink": {"past": "drank", "past_participle": "drunk"},
    "drive": {"past": "drove", "past_participle": "driven"},
    "eat": {"past": "ate", "past_participle": "eaten"},
    "fall": {"past": "fell", "past_participle": "fallen"},
    "find": {"past": "found"},
    "fly": {"past": "flew", "past_participle": "flown"},
    "forget": {"past": "forgot", "past_participle": "forgotten"},
    "get": {"past": "got", "past_participle": "gotten"},
    "give": {"past": "gave", "past_participle": "given"},
    "go": {"past": "went", "past_participle": "gone"},
    "have": {"past": "had", "third_singular_present": "has"},
    "know": {"past": "knew", "past_participle": "known"},
    "make": {"past": "made"},
    "read": {"past": "read", "past_participle": "read"},
    "run": {"past": "ran", "past_participle": "run"},
    "say": {"past": "said"},
    "see": {"past": "saw", "past_participle": "seen"},
    "speak": {"past": "spoke", "past_participle": "spoken"},
    "take": {"past": "took", "past_participle": "taken"},
    "think": {"past": "thought"},
    "write": {"past": "wrote", "past_participle": "written"},
    "arise": {"past": "arose", "past_participle": "arisen"},
    "awake": {"past": "awoke", "past_participle": "awoken"},
    "bear": {"past": "bore", "past_participle": "borne"},
    "beat": {"past": "beat", "past_participle": "beaten"},
    "become": {"past": "became", "past_participle": "become"},
    "bend": {"past": "bent"},
    "bet": {"past": "bet", "past_participle": "bet"},
    "bind": {"past": "bound"},
    "bite": {"past": "bit", "past_participle": "bitten"},
    "bleed": {"past": "bled"},
    "blow": {"past": "blew", "past_participle": "blown"},
    "breed": {"past": "bred"},
    "broadcast": {"past": "broadcast", "past_participle": "broadcast"},
    "burst": {"past": "burst", "past_participle": "burst"},
    "catch": {"past": "caught"},
    "cling": {"past": "clung"},
    "cost": {"past": "cost", "past_participle": "cost"},
    "creep": {"past": "crept"},
    "cut": {"past": "cut", "past_participle": "cut"},
    "deal": {"past": "dealt"},
    "dig": {"past": "dug"},
    "draw": {"past": "drew", "past_participle": "drawn"},
    "dream": {"past": "dreamt"},
    "feed": {"past": "fed"},
    "feel": {"past": "felt"},
    "fight": {"past": "fought"},
    "freeze": {"past": "froze", "past_participle": "frozen"},
    "hang": {"past": "hung"},
    "hear": {"past": "heard"},
    "hide": {"past": "hid", "past_participle": "hidden"},
    "hit": {"past": "hit", "past_participle": "hit"},
    "hold": {"past": "held"},
    "hurt": {"past": "hurt", "past_participle": "hurt"},
    "keep": {"past": "kept"},
    "kneel": {"past": "knelt"},
    "lead": {"past": "led"},
    "lean": {"past": "leant"},
    "leave": {"past": "left"},
    "lend": {"past": "lent"},
    "let": {"past": "let", "past_participle": "let"},
    "lie": {"past": "lay", "past_participle": "lain"},
    "light": {"past": "lit"},
    "lose": {"past": "lost"},
    "mean": {"past": "meant"},
    "meet": {"past": "met"},
    "mistake": {"past": "mistook", "past_participle": "mistaken"},
    "pay": {"past": "paid"},
    "prove": {"past": "proved", "past_participle": "proven"},
    "put": {"past": "put", "past_participle": "put"},
    "quit": {"past": "quit", "past_participle": "quit"},
    "ride": {"past": "rode", "past_participle": "ridden"},
    "ring": {"past": "rang", "past_participle": "rung"},
    "rise": {"past": "rose", "past_participle": "risen"},
    "seek": {"past": "sought"},
    "sell": {"past": "sold"},
    "send": {"past": "sent"},
    "set": {"past": "set", "past_participle": "set"},
    "shake": {"past": "shook", "past_participle": "shaken"},
    "shine": {"past": "shone"},
    "shoot": {"past": "shot"},
    "show": {"past": "showed", "past_participle": "shown"},
    "shut": {"past": "shut", "past_participle": "shut"},
    "sing": {"past": "sang", "past_participle": "sung"},
    "sink": {"past": "sank", "past_participle": "sunk"},
    "sit": {"past": "sat", "past_participle": "sat"},
    "sleep": {"past": "slept"},
    "slide": {"past": "slid", "past_participle": "slid"},
    "smell": {"past": "smelt"},
    "spend": {"past": "spent"},
    "spin": {"past": "spun"},
    "split": {"past": "split", "past_participle": "split"},
    "spread": {"past": "spread", "past_participle": "spread"},
    "stand": {"past": "stood"},
    "steal": {"past": "stole", "past_participle": "stolen"},
    "stick": {"past": "stuck"},
}


for irregular_infinitive, irregular_forms in IRREGULAR_BASE_FORMS.items():
    IRREGULAR_CONJUGATIONS[irregular_infinitive] = _build_uniform_irregular_conjugation(
        irregular_infinitive,
        irregular_forms,
    )


def expand_verb_forms(
    base_forms: Dict[str, str],
    infinitive_override: Optional[str] = None,
) -> Dict[str, str]:
    """Expand base verb forms into the full person/tense conjugation table.

    Only three base forms genuinely require LLM / Wiktionary data:
    ``infinitive``, ``past``, and ``past_participle``.  The other two
    (``3s_present`` and ``present_participle``) are derived from the
    infinitive via spelling rules when not supplied.

    Parameters
    ----------
    base_forms:
        Dictionary keyed by form name.  Required for full output:

        * ``infinitive`` – base / bare infinitive (e.g. "walk")
        * ``past`` – simple past (e.g. "walked")
        * ``past_participle`` – past participle (e.g. "walked")

        Optional (generated from infinitive when absent):

        * ``3s_present`` – 3rd-person singular present (e.g. "walks")
        * ``present_participle`` – present participle / gerund (e.g. "walking")

        If any key is missing or empty the function will still produce as
        many expanded forms as possible from the remaining data.

    infinitive_override:
        If provided, used as the infinitive instead of ``base_forms["infinitive"]``.
        Useful when calling from a context where the lemma text is available but
        not yet in the dict.

    Returns
    -------
    Dict[str, str]
        A dictionary whose keys match those used by
        ``langtools.en.llm_forms.VERB_FORM_MAPPING`` (23 keys total).
        Empty-string values are omitted.
    """
    infinitive = infinitive_override or base_forms.get("infinitive", "")
    third_sg = base_forms.get("3s_present", "")
    past = base_forms.get("past", "")
    past_part = base_forms.get("past_participle", "")
    pres_part = base_forms.get("present_participle", "")

    # Check for hard-coded irregular verbs first.
    if infinitive.lower() in IRREGULAR_CONJUGATIONS:
        return dict(IRREGULAR_CONJUGATIONS[infinitive.lower()])

    # Generate 3s_present and present_participle from the infinitive when
    # not explicitly provided.
    if infinitive and not third_sg:
        third_sg = generate_3s_present(infinitive)
    if infinitive and not pres_part:
        pres_part = generate_present_participle(infinitive)
    if infinitive and not past:
        past = generate_past_tense(infinitive)
    if past and not past_part:
        past_part = past

    result: Dict[str, str] = {}

    # --- Infinitive & participles (pass through) ---
    if infinitive:
        result["infinitive"] = infinitive
    if pres_part:
        result["present_participle"] = pres_part
    if past_part:
        result["past_participle"] = past_part

    # --- Present tense ---
    # All persons except 3s use the bare infinitive.
    if infinitive:
        result["1s_present"] = infinitive
        result["2s_present"] = infinitive
        result["1p_present"] = infinitive
        result["2p_present"] = infinitive
        result["3p_present"] = infinitive
    if third_sg:
        result["3s_present"] = third_sg

    # --- Past tense ---
    # All persons share the same past form in English (except "be").
    if past:
        result["1s_past"] = past
        result["2s_past"] = past
        result["3s_past"] = past
        result["1p_past"] = past
        result["2p_past"] = past
        result["3p_past"] = past

    # --- Future tense ---
    # "will" + infinitive for all persons.
    if infinitive:
        future_form = "will " + infinitive
        result["1s_future"] = future_form
        result["2s_future"] = future_form
        result["3s_future"] = future_form
        result["1p_future"] = future_form
        result["2p_future"] = future_form
        result["3p_future"] = future_form

    # --- Imperative ---
    # Uses the bare infinitive for both singular and plural.
    if infinitive:
        result["2s_imp"] = infinitive
        result["2p_imp"] = infinitive

    return result
