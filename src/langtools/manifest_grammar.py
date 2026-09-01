"""Helpers for language-specific WireWord manifest grammar metadata."""

from __future__ import annotations

from importlib import util
from pathlib import Path
from types import ModuleType
from typing import Any, Optional

from langtools.dialect_overrides import get_base_language
from langtools.person_labels import get_person_labels


def _load_manifest_module(language_code: str) -> ModuleType:
    langtools_spec = util.find_spec("langtools")
    if langtools_spec is None or not langtools_spec.submodule_search_locations:
        raise NotImplementedError("Could not locate langtools package")

    # A dialect shares its parent's grammar, so it reads the parent's manifest
    # metadata: zh-tw conjugates exactly as zh does.
    base_language = get_base_language(language_code)
    langtools_root = Path(next(iter(langtools_spec.submodule_search_locations)))
    manifest_path = langtools_root / base_language / "manifest.py"
    if not manifest_path.exists():
        raise NotImplementedError(f"No manifest metadata module for language '{language_code}'")

    module_name = f"langtools_dynamic_{base_language}_manifest"
    spec = util.spec_from_file_location(module_name, manifest_path)
    if spec is None or spec.loader is None:
        raise NotImplementedError(
            f"Could not load manifest metadata for language '{language_code}'"
        )

    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_manifest_conjugation_config(language_code: str) -> Optional[dict[str, Any]]:
    """Return manifest grammar config for a target language, if available."""
    if not language_code:
        raise ValueError("language_code must be non-empty")

    try:
        module = _load_manifest_module(language_code)
    except NotImplementedError:
        return None

    getter = getattr(module, "get_conjugation_manifest_config", None)
    if not callable(getter):
        return None

    config = getter()
    if not isinstance(config, dict):
        return None

    tense_data = config.get("tenses")
    has_person_tenses = (
        any(
            isinstance(tense_entry, dict) and tense_entry.get("has_persons")
            for tense_entry in tense_data
        )
        if isinstance(tense_data, list)
        else False
    )

    person_labels = get_person_labels(language_code)
    if has_person_tenses and person_labels:
        merged_config = dict(config)
        merged_config["person_labels"] = person_labels
        return merged_config

    return config
