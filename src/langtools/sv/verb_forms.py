#!/usr/bin/python3

"""Language-specific verb-form benchmark config for Swedish."""


def get_verb_forms_config() -> dict:
    """Return Swedish-specific core slots and prompt guidance."""
    return {
        "person_slots": [],
        "core_slots": [
            {"key": "infinitive", "kind": "string"},
            {"key": "present", "kind": "string"},
            {"key": "preterite", "kind": "string"},
            {"key": "supine", "kind": "string"},
            {"key": "imperative", "kind": "string"},
        ],
        "prompt_note": (
            "- Swedish verbs do not conjugate by person; provide one canonical form for each required slot."
        ),
    }
