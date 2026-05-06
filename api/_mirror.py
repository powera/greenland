"""Utilities for declaring Barsukas route mirroring in API facades."""

from collections.abc import Callable
from typing import Any, TypeVar, cast

FacadeFunction = TypeVar("FacadeFunction", bound=Callable[..., Any])


def mirrored_route(route_path: str, method: str) -> Callable[[FacadeFunction], FacadeFunction]:
    """Annotate a facade function with the Barsukas route it mirrors."""

    def decorator(function: FacadeFunction) -> FacadeFunction:
        setattr(function, "_mirrored_route", route_path)
        setattr(function, "_mirrored_method", method.upper())
        return cast(FacadeFunction, function)

    return decorator
