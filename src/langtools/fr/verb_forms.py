#!/usr/bin/python3

"""Language-specific verb-form benchmark config for French."""


def get_verb_forms_config() -> dict:
    """Return French-specific core slots and prompt guidance."""
    return {
        "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
        "core_slots": [
            {"key": "present", "kind": "person_map"},
            {"key": "imparfait", "kind": "person_map"},
            {"key": "passe_compose", "kind": "person_map"},
            {"key": "futur_simple", "kind": "person_map"},
        ],
        "prompt_note": (
            "- For French, include distinct imparfait and passé composé paradigms instead of a "
            "single generic past tense."
        ),
    }

