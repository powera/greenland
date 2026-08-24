#!/usr/bin/python3

"""Lookup helpers for language-specific verb-form benchmark layouts."""

from importlib import import_module
from typing import Any, Dict, List, TypedDict

from langtools.dialect_overrides import get_base_language


class VerbFormSlot(TypedDict):
    """Definition for one required slot in a verb-form response."""

    key: str
    kind: str


DEFAULT_PERSON_SLOTS = ["1s", "2s", "3s", "1p", "2p", "3p"]
DEFAULT_CORE_SLOTS: List[VerbFormSlot] = [
    {"key": "present", "kind": "person_map"},
    {"key": "past", "kind": "person_map"},
    {"key": "future", "kind": "person_map"},
]


def _default_config() -> Dict[str, Any]:
    return {
        "person_slots": list(DEFAULT_PERSON_SLOTS),
        "core_slots": [dict(slot) for slot in DEFAULT_CORE_SLOTS],
        "extra_slots": [],
        "prompt_note": "",
    }


def _sanitize_config(raw: Any) -> Dict[str, Any]:
    config = _default_config()
    if not isinstance(raw, dict):
        return config

    raw_persons = raw.get("person_slots")
    if isinstance(raw_persons, list):
        person_slots = [slot for slot in raw_persons if isinstance(slot, str) and slot.strip()]
        if person_slots or raw_persons == []:
            config["person_slots"] = person_slots

    raw_core = raw.get("core_slots")
    if isinstance(raw_core, list):
        core_slots: List[VerbFormSlot] = []
        for entry in raw_core:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            kind = entry.get("kind")
            if not isinstance(key, str) or not key.strip():
                continue
            if kind not in {"person_map", "string"}:
                continue
            core_slots.append({"key": key, "kind": kind})
        if core_slots:
            config["core_slots"] = core_slots

    raw_extra = raw.get("extra_slots")
    if isinstance(raw_extra, list):
        extra_slots = [slot for slot in raw_extra if isinstance(slot, str) and slot.strip()]
        if extra_slots or raw_extra == []:
            config["extra_slots"] = extra_slots

    prompt_note = raw.get("prompt_note")
    if isinstance(prompt_note, str):
        config["prompt_note"] = prompt_note

    return config


def get_language_verb_forms_config(language_code: str) -> Dict[str, Any]:
    """Return per-language verb-form benchmark config with sane defaults."""
    # Dialects share their parent's verb system, so resolve pt-br -> pt first.
    normalized = get_base_language(language_code)
    if not normalized:
        return _default_config()

    try:
        module = import_module(f"langtools.{normalized}.verb_forms")
    except ModuleNotFoundError:
        return _default_config()

    getter = getattr(module, "get_verb_forms_config", None)
    if callable(getter):
        return _sanitize_config(getter())

    return _default_config()
