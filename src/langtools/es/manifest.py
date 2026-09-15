"""WireWord manifest grammar metadata for es and its storage dialect es-419.

Both varieties expose the same three tenses over the same six person slots.
The 2p slot is the one that differs: Peninsular Spanish conjugates it for
vosotros (habláis), Latin American Spanish for ustedes (hablan).  The slot is
kept in both so a client can lay the two out side by side; the pronoun label
that comes with it says which one is meant.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from langtools.es.conjugation import uses_ustedes

_CONJUGATION_CONFIG: dict[str, Any] = {
    "tenses": [
        {
            "id": "past",
            "label": "Past Tense",
            "order": 1,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Simple past forms used in core conjugation activities.",
        },
        {
            "id": "pres",
            "label": "Present Tense",
            "order": 2,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Present indicative conjugations.",
        },
        {
            "id": "fut",
            "label": "Future Tense",
            "order": 3,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Future tense conjugations.",
        },
    ]
}


_USTEDES_SLOT_NOTE = (
    "The 2p slot is the ustedes form, which is identical to the 3p form; "
    "Latin American Spanish has no vosotros."
)


def get_conjugation_manifest_config(language_code: str = "es") -> dict[str, Any]:
    """Return language-specific conjugation metadata for WireWord manifests."""
    if not uses_ustedes(language_code):
        return _CONJUGATION_CONFIG

    config = deepcopy(_CONJUGATION_CONFIG)
    for tense in config["tenses"]:
        tense["description"] = f"{tense['description']} {_USTEDES_SLOT_NOTE}"
    config["second_person_plural"] = "ustedes"
    return config
