"""Helpers for language-specific grammatical person labels and pronoun metadata."""

from __future__ import annotations

from importlib import util
from pathlib import Path
from types import ModuleType
from typing import Optional, TypedDict

from langtools.dialect_overrides import get_base_language


class PersonPronounEntry(TypedDict):
    """Metadata for pronouns used by a grammatical person slot.

    Attributes:
        pronouns: Pronoun forms valid for the slot.
        has_multiple: True when the slot has multiple valid pronouns.
        is_ambiguous: True when at least one pronoun in this slot is shared with
            another person slot (for example English ``you`` in both 2s and 2p).
    """

    pronouns: list[str]
    has_multiple: bool
    is_ambiguous: bool


class PronounVariant(TypedDict):
    """A pronoun form with optional variation metadata.

    Attributes:
        text: Surface pronoun text.
        variation: Optional coarse variation category (for example
            ``"regional"``, ``"gender"``, ``"register"``).
        note: Optional human-readable detail for the variation.
    """

    text: str
    variation: str
    note: str


def _load_pronouns_module(language_code: str) -> ModuleType:
    langtools_spec = util.find_spec("langtools")
    if langtools_spec is None or not langtools_spec.submodule_search_locations:
        raise NotImplementedError("Could not locate langtools package")

    # A dialect shares its parent's grammar, so it shares the parent's module:
    # there is no langtools/zh-tw/ and there should not be one.
    base_language = get_base_language(language_code)
    langtools_root = Path(next(iter(langtools_spec.submodule_search_locations)))
    pronouns_path = langtools_root / base_language / "pronouns.py"
    if not pronouns_path.exists():
        raise NotImplementedError(f"No pronouns module for language '{language_code}'")

    module_name = f"langtools_dynamic_{base_language}_pronouns"
    spec = util.spec_from_file_location(module_name, pronouns_path)
    if spec is None or spec.loader is None:
        raise NotImplementedError(f"Could not load pronouns for language '{language_code}'")

    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_pronoun_metadata(
    pronouns_by_person: dict[str, list[str]],
) -> dict[str, PersonPronounEntry]:
    pronoun_to_slots: dict[str, set[str]] = {}
    for person_slot, pronouns in pronouns_by_person.items():
        for pronoun in pronouns:
            pronoun_to_slots.setdefault(pronoun, set()).add(person_slot)

    metadata: dict[str, PersonPronounEntry] = {}
    for person_slot, pronouns in pronouns_by_person.items():
        is_slot_ambiguous = any(
            len(pronoun_to_slots.get(pronoun, set())) > 1 for pronoun in pronouns
        )
        metadata[person_slot] = {
            "pronouns": pronouns,
            "has_multiple": len(pronouns) > 1,
            "is_ambiguous": is_slot_ambiguous,
        }

    return metadata


def _build_pronouns_by_person_from_variants(
    variants_by_person: dict[str, list[PronounVariant]],
) -> dict[str, list[str]]:
    pronouns_by_person: dict[str, list[str]] = {}
    for person_slot, variants in variants_by_person.items():
        pronoun_texts = [variant["text"] for variant in variants if variant.get("text")]
        if pronoun_texts:
            pronouns_by_person[person_slot] = pronoun_texts
    return pronouns_by_person


def get_person_pronoun_variants(
    language_code: str,
) -> Optional[dict[str, list[PronounVariant]]]:
    """Return pronoun variants by person slot for a language, if defined."""
    if not language_code:
        raise ValueError("language_code must be non-empty")

    try:
        module = _load_pronouns_module(language_code)
    except NotImplementedError:
        return None

    variants_getter = getattr(module, "get_subject_pronoun_variants_by_person", None)
    if not callable(variants_getter):
        return None

    variants = variants_getter()
    if not isinstance(variants, dict):
        return None
    return variants


def get_person_pronoun_data(language_code: str) -> Optional[dict[str, PersonPronounEntry]]:
    """Return pronoun metadata by person slot for a language, if defined."""
    if not language_code:
        raise ValueError("language_code must be non-empty")

    try:
        module = _load_pronouns_module(language_code)
    except NotImplementedError:
        return None

    variants_by_person = get_person_pronoun_variants(language_code)
    if variants_by_person:
        pronouns_by_person = _build_pronouns_by_person_from_variants(variants_by_person)
        return _build_pronoun_metadata(pronouns_by_person)

    # Preferred API: per-language files expose raw pronoun lists and this helper
    # computes has_multiple/is_ambiguous consistently.
    list_getter = getattr(module, "get_subject_pronouns_by_person", None)
    if callable(list_getter):
        pronouns_by_person = list_getter()
        if isinstance(pronouns_by_person, dict):
            return _build_pronoun_metadata(pronouns_by_person)

    # Backward-compatible fallback for older language modules.
    metadata_getter = getattr(module, "get_person_pronoun_data", None)
    if not callable(metadata_getter):
        return None

    metadata = metadata_getter()
    if not isinstance(metadata, dict):
        return None
    return metadata


def get_person_labels(language_code: str) -> Optional[dict[str, str]]:
    """Return display labels for grammatical person slots, if defined."""
    pronoun_data = get_person_pronoun_data(language_code)
    if pronoun_data is None:
        return None

    labels: dict[str, str] = {}
    for person_slot, entry in pronoun_data.items():
        pronouns = entry.get("pronouns", [])
        if not pronouns:
            continue
        labels[person_slot] = "/".join(pronouns)

    if not labels:
        return None
    return labels
