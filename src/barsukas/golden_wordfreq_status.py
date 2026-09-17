"""Thread-safe loading flag for golden-mode wordfreq data."""

from __future__ import annotations

from threading import Lock


_lock = Lock()
_loading = False


def start_load() -> None:
    """Mark the golden-mode wordfreq load as running."""
    global _loading
    with _lock:
        _loading = True


def complete_load() -> None:
    """Clear the loading flag when the background job exits."""
    global _loading
    with _lock:
        _loading = False


def is_loading() -> bool:
    """Return whether wordfreq-derived data is still being loaded."""
    with _lock:
        return _loading
