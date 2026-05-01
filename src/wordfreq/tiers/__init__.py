"""Tier system for lemma-level difficulty annotations from external sources.

Tier sources (Cambridge YLE, CEFR, etc.) annotate lemmas with a named tier
within an ordered scale. Each source supplies an importer that conforms to
``TierImporter`` and is run via ``runner.run_import``.
"""

from wordfreq.tiers.base import (
    ResolveResult,
    ResolveStatus,
    TierEntry,
    TierImporter,
)
from wordfreq.tiers.bootstrap import (
    BOOTSTRAP_TIER_DEFINITIONS,
    bootstrap_tier_definitions,
)
from wordfreq.tiers.runner import ImportReport, run_import

__all__ = [
    "BOOTSTRAP_TIER_DEFINITIONS",
    "ImportReport",
    "ResolveResult",
    "ResolveStatus",
    "TierEntry",
    "TierImporter",
    "bootstrap_tier_definitions",
    "run_import",
]
