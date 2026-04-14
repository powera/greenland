#!/usr/bin/python3

"""Helpers for loading Barsukas UI strings from namespaced JSON files."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, cast

SUPPORTED_UI_LANGS = frozenset({"en", "lt"})
_STRINGS_ROOT = Path(__file__).resolve().parents[3] / "strings" / "barsukas"
_LEGACY_NAMESPACE_ALIASES = {
    "linguistics": "common.linguistics",
    "parts_of_speech": "common.linguistics",
    "pagination": "common.pagination",
}


def _namespace_path_from_string(namespace: str) -> Path:
    return _STRINGS_ROOT.joinpath(*namespace.split("."))


def _discover_namespaces() -> list[str]:
    namespace_set: set[str] = set()
    for json_path in _STRINGS_ROOT.rglob("en.json"):
        namespace_dir = json_path.parent
        try:
            relative_parts = namespace_dir.relative_to(_STRINGS_ROOT).parts
        except ValueError:
            continue
        if not relative_parts:
            continue
        namespace_set.add(".".join(relative_parts))
    return sorted(namespace_set)


@lru_cache(maxsize=64)
def _load_namespace_file(namespace: str, ui_lang: str) -> Dict[str, Any]:
    """Load one namespace JSON file with English fallback."""
    if ui_lang not in SUPPORTED_UI_LANGS:
        ui_lang = "en"

    namespace_root = _namespace_path_from_string(namespace)
    namespace_path = namespace_root / f"{ui_lang}.json"
    fallback_path = namespace_root / "en.json"

    if namespace_path.exists():
        with namespace_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
            return cast(Dict[str, Any], loaded)

    if fallback_path.exists():
        with fallback_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
            return cast(Dict[str, Any], loaded)

    return {}


def load_barsukas_strings(namespace: str, ui_lang: str) -> Dict[str, Any]:
    """Public helper for route handlers to fetch namespace strings."""
    return _load_namespace_file(namespace=namespace, ui_lang=ui_lang)


@lru_cache(maxsize=8)
def load_all_barsukas_strings(ui_lang: str) -> Dict[str, Dict[str, Any]]:
    """Load all Barsukas string namespaces for a UI language."""
    if ui_lang not in SUPPORTED_UI_LANGS:
        ui_lang = "en"

    namespaces = _discover_namespaces()
    strings_by_namespace = {
        namespace: _load_namespace_file(namespace=namespace, ui_lang=ui_lang)
        for namespace in namespaces
    }
    for alias, target in _LEGACY_NAMESPACE_ALIASES.items():
        if alias not in strings_by_namespace and target in strings_by_namespace:
            strings_by_namespace[alias] = strings_by_namespace[target]

    for namespace in namespaces:
        if "." not in namespace:
            continue
        parent_name, child_name = namespace.rsplit(".", 1)
        parent_namespace = strings_by_namespace.get(parent_name)
        child_namespace = strings_by_namespace.get(namespace)
        if parent_namespace is None or child_namespace is None:
            continue
        existing_child = parent_namespace.get(child_name)
        if isinstance(existing_child, dict):
            existing_child.update(child_namespace)
        else:
            parent_namespace[child_name] = child_namespace
    return strings_by_namespace


class _StringPathNode:
    """Lazy accessor object used by Jinja for LSTR/SSTR paths."""

    def __init__(
        self,
        resolver: "StringAccessor",
        segments: Optional[Sequence[str]] = None,
    ) -> None:
        self._resolver = resolver
        self._segments = tuple(segments or ())

    def __getattr__(self, name: str) -> "_StringPathNode":
        return _StringPathNode(self._resolver, (*self._segments, name))

    def get(self, default: str = "") -> str:
        """Resolve current path with optional default."""
        return self._resolver.resolve(self._segments, default=default)

    def __str__(self) -> str:
        return self._resolver.resolve(self._segments, default="")


class StringAccessor:
    """Template accessor for legacy STRINGS namespaces and new LSTR/SSTR paths."""

    def __init__(
        self,
        strings_by_namespace: Dict[str, Dict[str, Any]],
        mode: str,
        default_module: str = "common",
    ) -> None:
        self._strings_by_namespace = strings_by_namespace
        self._mode = mode
        self._default_module = default_module

    def __getattr__(self, name: str) -> _StringPathNode:
        return _StringPathNode(self, (name,))

    def resolve(self, segments: Sequence[str], default: str = "") -> str:
        """Resolve a dotted path to a string value.

        Modes:
        - lstr: default shared namespace with CURRENT/OTHER support.
        - sstr: explicit namespace required (first segment).
        """
        if not segments:
            return default

        if self._mode == "lstr":
            return self._resolve_lstr(segments, default=default)

        if self._mode == "sstr":
            return self._resolve_sstr(segments, default=default)

        return default

    def _resolve_lstr(self, segments: Sequence[str], default: str = "") -> str:
        head = segments[0]

        if head == "CURRENT":
            key = ".".join(segments[1:])
            return self._get_value(self._default_module, key, default=default)

        if head == "OTHER" and len(segments) >= 3:
            namespace = segments[1]
            key = ".".join(segments[2:])
            return self._get_value(namespace, key, default=default)

        if head in self._strings_by_namespace and len(segments) >= 2:
            key = ".".join(segments[1:])
            return self._get_value(head, key, default=default)

        key = ".".join(segments)
        return self._get_value("common", key, default=default)

    def _resolve_sstr(self, segments: Sequence[str], default: str = "") -> str:
        if len(segments) < 2:
            return default

        namespace = segments[0]
        key = ".".join(segments[1:])
        return self._get_value(namespace, key, default=default)

    def _get_value(self, namespace: str, key: str, default: str = "") -> str:
        namespace_strings = self._strings_by_namespace.get(namespace, {})
        value = namespace_strings.get(key, default)
        if value is None:
            return default
        return str(value)


def create_lstr_accessor(
    strings_by_namespace: Dict[str, Dict[str, Any]], default_module: str
) -> StringAccessor:
    """Create accessor for short lemma-like strings (LSTR)."""
    return StringAccessor(strings_by_namespace, mode="lstr", default_module=default_module)


def create_sstr_accessor(
    strings_by_namespace: Dict[str, Dict[str, Any]], default_module: str
) -> StringAccessor:
    """Create accessor for sentence strings (SSTR)."""
    return StringAccessor(strings_by_namespace, mode="sstr", default_module=default_module)
