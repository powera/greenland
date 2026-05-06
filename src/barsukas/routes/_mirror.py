"""Decorator that records which root-level ``api/`` facade a route mirrors.

Defined here as a standalone copy of the decorator in
``api/_decorator.py`` so the two trees never import from each other. The
precommit check pairs facade and route by the ``_mirrored_route`` /
``_mirrored_method`` attribute values, not by decorator identity.

Edits to a route annotated with :func:`mirrored_facade` must keep the
matching facade in ``api/`` in sync (same path, same query parameters,
same response shape).
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar, cast

RouteFunction = TypeVar("RouteFunction", bound=Callable[..., Any])


def mirrored_facade(route_path: str, method: str) -> Callable[[RouteFunction], RouteFunction]:
    """Annotate a Flask route view with the ``api/`` facade it is mirrored by."""

    def decorator(function: RouteFunction) -> RouteFunction:
        setattr(function, "_mirrored_route", route_path)
        setattr(function, "_mirrored_method", method.upper())
        return cast(RouteFunction, function)

    return decorator
