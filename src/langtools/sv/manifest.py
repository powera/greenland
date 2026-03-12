"""WireWord manifest grammar metadata for sv."""

from __future__ import annotations

from typing import Any


_CONJUGATION_CONFIG: dict[str, Any] = {
    "tenses": [
        {
            "id": "infinitive",
            "label": "Infinitive",
            "order": 1,
            "has_persons": False,
            "person_slots": [],
            "description": "Dictionary form used with modal/future auxiliaries.",
        },
        {
            "id": "present",
            "label": "Presens",
            "order": 2,
            "has_persons": False,
            "person_slots": [],
            "description": "Present tense form shared across grammatical persons.",
        },
        {
            "id": "preterite",
            "label": "Preteritum",
            "order": 3,
            "has_persons": False,
            "person_slots": [],
            "description": "Past tense form shared across grammatical persons.",
        },
        {
            "id": "supine",
            "label": "Supinum",
            "order": 4,
            "has_persons": False,
            "person_slots": [],
            "description": "Supine form used with har/hade for perfect constructions.",
        },
        {
            "id": "imperative",
            "label": "Imperativ",
            "order": 5,
            "has_persons": False,
            "person_slots": [],
            "description": "Command form.",
        },
    ]
}


def get_conjugation_manifest_config() -> dict[str, Any]:
    """Return language-specific conjugation metadata for WireWord manifests."""
    return _CONJUGATION_CONFIG
