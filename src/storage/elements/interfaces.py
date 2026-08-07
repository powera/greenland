"""Composable interfaces shared by Greenland's linguistic element types.

The protocols are intentionally independent of SQLAlchemy and Flask. ORM
models satisfy them structurally by exposing the relevant properties; a model
does not need to inherit from a common mapped base beyond the one it already
uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class ElementRef:
    """A backend-local reference to a stored element."""

    element_type: str
    element_id: int


@dataclass(frozen=True)
class LanguageValue:
    """Read-only projection of text associated with a language."""

    id: int
    language_code: str
    text: str
    value_kind: str
    verified: bool
    status: str | None = None
    status_note: str | None = None


class Element(Protocol):
    """The smallest common view of a linguistic element."""

    @property
    def element_type(self) -> str: ...

    @property
    def display_text(self) -> str: ...


class WordElement(Element, Protocol):
    """An element representing exactly one lexical word/headword."""

    @property
    def word_text(self) -> str: ...


class MultiwordElement(Element, Protocol):
    """An element representing a reusable multiword expression."""

    @property
    def expression_text(self) -> str: ...


class GuidElement(Element, Protocol):
    """An element that participates in Greenland's GUID namespaces."""

    @property
    def guid(self) -> str | None: ...


class VerifiableElement(Element, Protocol):
    """An element that can be marked as human-verified."""

    @property
    def verified(self) -> bool: ...


class LeveledElement(Element, Protocol):
    """An element with a learner-facing or computed difficulty level."""

    @property
    def level(self) -> int | None: ...


class LanguageValueElement(Element, Protocol):
    """An element exposing language-associated text through a common view."""

    @property
    def language_values(self) -> Sequence[LanguageValue]: ...


class CompositeElement(Element, Protocol):
    """An element composed from references to other elements."""

    @property
    def children(self) -> Sequence[ElementRef]: ...
