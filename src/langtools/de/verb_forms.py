#!/usr/bin/python3

"""Language-specific verb-form benchmark config for German."""


def get_verb_forms_config() -> dict:
    """Return German-specific core slots and prompt guidance."""
    return {
        "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
        "core_slots": [
            {"key": "present", "kind": "person_map"},
            {"key": "perfect", "kind": "person_map"},
            {"key": "future_i", "kind": "person_map"},
            {"key": "preterite", "kind": "person_map"},
        ],
        "extra_slots": ["partizip_ii"],
        "prompt_note": (
            "- Use German tense names and keys exactly as specified: present, perfect, future_i, preterite.\n"
            "- For person-mapped slots, always return keys 1s, 2s, 3s, 1p, 2p, 3p (not arrays).\n"
            "- perfect must be auxiliary + infinitive/participle as appropriate for the lemma.\n"
            "- Include partizip_ii in extra_forms for every verb.\n"
            "- Do not invent optional categories (e.g., passive, Konjunktiv, future_ii) unless explicitly requested elsewhere."
        ),
    }
