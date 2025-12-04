"""Lemma display and UI helper functions for Barsukas."""

from wordfreq.storage.queries.lemma import get_difficulty_stats


# Re-export for backwards compatibility and convenience
# Routes can import from here for UI-related helpers
__all__ = ["get_difficulty_stats"]
