"""Decorator that records which Barsukas route a facade function mirrors.

The decorator only attaches metadata; it does not perform any HTTP work.
A precommit check reads ``_mirrored_route`` and ``_mirrored_method`` from each
facade and verifies that a matching Flask route exists on the Barsukas side.

The Barsukas side defines its own (separate) decorator under
``src/barsukas/routes/_mirror.py`` that sets the same attribute names so the
precommit check can pair them up by route+method without either tree
importing the other.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

FacadeFunction = TypeVar("FacadeFunction", bound=Callable[..., Any])


def mirrored_route(route_path: str, method: str) -> Callable[[FacadeFunction], FacadeFunction]:
    """Annotate a facade function with the Barsukas route it mirrors."""

    def decorator(function: FacadeFunction) -> FacadeFunction:
        setattr(function, "_mirrored_route", route_path)
        setattr(function, "_mirrored_method", method.upper())
        return cast(FacadeFunction, function)

    return decorator
