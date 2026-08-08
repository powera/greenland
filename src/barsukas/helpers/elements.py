"""Presenters for rendering any linguistic element through the shared views.

Barsukas historically reached for concrete model attributes - ``phrase.label``,
``name.name_text``, ``phrase.difficulty_level`` - so each element type needed its
own list table and identity card even though they displayed the same five facts.
The ``storage.elements`` protocols now give every element a common surface, so
these helpers project any element into the shape the ``elements/`` templates
consume, and the templates stop knowing which table a row came from.

Nothing here imports a concrete model. A new element type becomes renderable by
satisfying the protocols in :mod:`storage.elements.interfaces`, not by editing
this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from storage.elements.interfaces import Element, LanguageValue


@dataclass(frozen=True)
class ElementRow:
    """One row of a shared element list table.

    The route supplies ``detail_url`` because URL construction needs a blueprint
    endpoint, which is a Barsukas concern rather than a storage one.
    """

    element_id: int
    element_type: str
    display_text: str
    detail_url: Optional[str]
    guid: Optional[str]
    level: Optional[int]
    verified: Optional[bool]


def _optional_attr(element: Element, attribute_name: str) -> Any:
    """Read an optional protocol member, returning None when unimplemented.

    The element protocols are deliberately composable: an element may be a
    ``GuidElement`` without being a ``LeveledElement``. A shared table still
    wants one column layout, so a missing member renders as an em dash rather
    than raising.
    """
    return getattr(element, attribute_name, None)


def build_element_row(element: Element, detail_url: Optional[str] = None) -> ElementRow:
    """Project one element into a shared list row."""
    level = _optional_attr(element, "level")
    verified = _optional_attr(element, "verified")
    guid = _optional_attr(element, "guid")
    return ElementRow(
        element_id=int(_optional_attr(element, "id")),
        element_type=element.element_type,
        display_text=element.display_text,
        detail_url=detail_url,
        guid=str(guid) if guid is not None else None,
        level=int(level) if level is not None else None,
        verified=bool(verified) if verified is not None else None,
    )


def build_element_rows(
    elements: Sequence[Element],
    detail_urls: Optional[Mapping[int, str]] = None,
) -> list[ElementRow]:
    """Project a page of elements into shared list rows.

    ``detail_urls`` maps element id to its detail page. Ids absent from the
    mapping render as plain text, which is what a not-yet-viewable element type
    should do.
    """
    url_by_id = detail_urls or {}
    return [
        build_element_row(element, url_by_id.get(int(_optional_attr(element, "id"))))
        for element in elements
    ]


def group_language_values(
    values: Sequence[LanguageValue],
) -> dict[str, list[LanguageValue]]:
    """Group language values by language code, preserving their given order.

    Grouping is always many-per-language even for element types whose storage
    constrains them to one. Single-value types then render a one-item list
    instead of needing a second template, and multi-value types (idiom
    equivalents) need no special case.
    """
    grouped: dict[str, list[LanguageValue]] = {}
    for value in values:
        grouped.setdefault(value.language_code, []).append(value)
    return grouped
