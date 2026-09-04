"""Pattern expansion for language form configurations.

Given a config dict (from a ``forms_config.py``), the helpers here produce:

* A list of form field names
  (e.g. ``["nominative_singular", "nominative_plural", ...]``)
* A dict mapping form field → enum **value** string
  (e.g. ``{"nominative_singular": "noun/lv_nominative_singular"}``)
* A dict mapping form field → enum **member name**
  (e.g. ``{"nominative_singular": "NOUN_LV_NOMINATIVE_SINGULAR"}``)

These are consumed by ``enums.py`` (dynamic member creation) and
``form_registry.py`` (FORM_SPECS auto-build).
"""

from typing import Any, Dict, List, Tuple


# -- POS prefix used in enum member names and value strings ----------------

_POS_PREFIXES: Dict[str, Tuple[str, str]] = {
    # pos_type → (enum_member_prefix, value_prefix)
    "noun": ("NOUN", "noun"),
    "verb": ("VERB", "verb"),
    "adjective": ("ADJ", "adjective"),
    "adverb": ("ADVERB", "adverb"),
}


def _pos_parts(pos_type: str) -> Tuple[str, str]:
    return _POS_PREFIXES[pos_type]


# -- Pattern expansion -----------------------------------------------------


def expand_fields(config: Dict[str, Any]) -> List[str]:
    """Return the ordered list of form field names for *config*."""
    pattern = config["type"]

    if pattern == "case_number":
        return [f"{case}_{number}" for case in config["cases"] for number in config["numbers"]]

    if pattern == "singular_plural":
        return ["singular", "plural"]

    if pattern == "person_tense":
        fields = [f"{person}_{tense}" for tense in config["tenses"] for person in config["persons"]]
        fields.extend(config.get("extra_forms", []))
        return fields

    if pattern == "tense_only":
        return list(config["tenses"])

    if pattern == "case_number_gender":
        fields = [
            f"{case}_{number}_{gender}"
            for case in config["cases"]
            for number in config["numbers"]
            for gender in config["genders"]
        ]
        # Degree (comparative/superlative) is a separate axis from case, and
        # crossing the two would multiply the table by three for forms that are
        # mostly rare.  A language that needs degree lists the slots it actually
        # needs in ``extra_forms`` instead -- see lt/forms_config.py.
        fields.extend(config.get("extra_forms", []))
        return fields

    if pattern == "degree":
        return list(config["forms"])

    if pattern == "explicit":
        return list(config["forms"])

    if pattern == "base_only":
        return ["base"]

    raise ValueError(f"Unknown pattern type: {pattern!r}")


def expand_enum_values(config: Dict[str, Any], lang_code: str, pos_type: str) -> Dict[str, str]:
    """Map each form field to its enum *value* string.

    Example: ``"nominative_singular"`` → ``"noun/lv_nominative_singular"``
    """
    _, val_prefix = _pos_parts(pos_type)
    lc = lang_code.lower()
    return {field: f"{val_prefix}/{lc}_{field}" for field in expand_fields(config)}


def expand_enum_names(config: Dict[str, Any], lang_code: str, pos_type: str) -> Dict[str, str]:
    """Map each form field to its enum *member name*.

    Example: ``"nominative_singular"`` → ``"NOUN_LV_NOMINATIVE_SINGULAR"``
    """
    member_prefix, _ = _pos_parts(pos_type)
    uc = lang_code.upper()
    return {field: f"{member_prefix}_{uc}_{field.upper()}" for field in expand_fields(config)}


def get_all_enum_pairs(
    config: Dict[str, Any], lang_code: str, pos_type: str
) -> List[Tuple[str, str]]:
    """Return ``(member_name, value_string)`` pairs for every form."""
    names = expand_enum_names(config, lang_code, pos_type)
    values = expand_enum_values(config, lang_code, pos_type)
    fields = expand_fields(config)
    return [(names[f], values[f]) for f in fields]
