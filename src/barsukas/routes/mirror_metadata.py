"""Decorator metadata for Barsukas routes mirrored by top-level api/ wrappers."""

from collections.abc import Callable
from typing import Any, TypeVar, cast

RouteFunction = TypeVar("RouteFunction", bound=Callable[..., Any])


def mirrored_by_api(route_path: str, method: str) -> Callable[[RouteFunction], RouteFunction]:
    """Attach mirror metadata for external api/ wrapper parity checks."""

    def decorator(function: RouteFunction) -> RouteFunction:
        setattr(function, "_mirrored_route", route_path)
        setattr(function, "_mirrored_method", method.upper())
        return cast(RouteFunction, function)

    return decorator
