"""Programmatic English verb conjugation expansion.

English verbs are highly regular in their person/tense inflection: past and
future tenses do not change by person, and present tense only distinguishes
3rd-person singular from the base form.  The only verb that is truly
person-irregular across tenses is "to be".

This module provides :func:`expand_verb_forms` which takes the five canonical
base forms stored in the database (infinitive, 3s_present, past,
past_participle, present_participle) and expands them to the full set of
person/tense forms expected by the ``VERB_FORM_MAPPING`` in
:mod:`langtools.en.llm_forms`, eliminating the need for an LLM call to
produce the remaining forms.
"""

from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Irregular conjugations keyed by infinitive.
#
# Each entry maps every person/tense key used by VERB_FORM_MAPPING to the
# correct surface form.  Only verbs whose person-inflection cannot be derived
# from the five base forms need to appear here.  In practice this is only
# "be" in modern English.
# ---------------------------------------------------------------------------

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


def expand_verb_forms(
    base_forms: Dict[str, str],
    infinitive_override: Optional[str] = None,
) -> Dict[str, str]:
    """Expand five base verb forms into the full person/tense conjugation table.

    Parameters
    ----------
    base_forms:
        Dictionary that should contain (at minimum) these keys:

        * ``infinitive`` – base / bare infinitive (e.g. "walk")
        * ``3s_present`` – 3rd-person singular present (e.g. "walks")
        * ``past`` – simple past (e.g. "walked")
        * ``past_participle`` – past participle (e.g. "walked")
        * ``present_participle`` – present participle / gerund (e.g. "walking")

        If any of the five keys is missing or empty the function will still
        produce as many expanded forms as possible from the remaining data.

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
