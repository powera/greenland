"""WireWord manifest grammar metadata for lt."""

from __future__ import annotations

from typing import Any


_CONJUGATION_CONFIG: dict[str, Any] = {
    "tenses": [
        {
            "id": "past",
            "label": "Past Tense",
            "order": 1,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Simple past forms used in everyday speech.",
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
        {
            "id": "conditional",
            "label": "Conditional Mood",
            "order": 4,
            "has_persons": True,
            "person_slots": ["1s", "2s", "3s", "1p", "2p", "3p"],
            "description": "Conditional forms such as 'would eat'.",
        },
        {
            "id": "imperative",
            "label": "Imperative",
            "order": 5,
            "has_persons": True,
            "person_slots": ["2s", "2p"],
            "description": "Command forms, usually second person only.",
        },
    ]
}


def get_conjugation_manifest_config() -> dict[str, Any]:
    """Return language-specific conjugation metadata for WireWord manifests."""
    return _CONJUGATION_CONFIG
