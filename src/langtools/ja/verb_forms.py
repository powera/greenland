#!/usr/bin/python3

"""Language-specific verb-form benchmark config for Japanese."""


def get_verb_forms_config() -> dict:
    """Return Japanese-specific core slots and prompt guidance."""
    return {
        "person_slots": [],
        "core_slots": [
            {"key": "dictionary", "kind": "string"},
            {"key": "masu_present", "kind": "string"},
            {"key": "masu_past", "kind": "string"},
            {"key": "nai", "kind": "string"},
            {"key": "te", "kind": "string"},
            {"key": "ta", "kind": "string"},
            {"key": "potential", "kind": "string"},
            {"key": "volitional", "kind": "string"},
        ],
        "prompt_note": (
            "- For Japanese, use Japanese conjugation categories (dictionary, masu, nai, te, ta, potential, "
            "volitional) rather than person-based paradigms."
        ),
    }
