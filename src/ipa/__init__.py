"""IPA utilities package."""

from ipa.normalization import (
    are_ipa_equivalent,
    is_ipa_levenshtein_match,
    normalize_ipa,
    weighted_similarity_ratio,
)

__all__ = [
    "normalize_ipa",
    "weighted_similarity_ratio",
    "are_ipa_equivalent",
    "is_ipa_levenshtein_match",
]
