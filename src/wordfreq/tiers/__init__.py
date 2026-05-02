"""Tier system for lemma-level difficulty annotations from external sources.

Tier sources (Cambridge YLE, CEFR, etc.) annotate lemmas with a named tier
within an ordered scale. Each source supplies an importer that conforms to
``TierImporter`` and is run via ``runner.run_import``.
"""

from wordfreq.tiers.base import TierEntry, TierImporter
from wordfreq.tiers.basic_english import BasicEnglishImporter
from wordfreq.tiers.bootstrap import (
    BOOTSTRAP_TIER_DEFINITIONS,
    bootstrap_tier_definitions,
)
from wordfreq.tiers.cambridge_yle import CambridgeYleImporter
from wordfreq.tiers.cefr import CefrImporter
from wordfreq.tiers.runner import ImportReport, reconcile_external_annotations, run_import

__all__ = [
    "BOOTSTRAP_TIER_DEFINITIONS",
    "BasicEnglishImporter",
    "CambridgeYleImporter",
    "CefrImporter",
    "ImportReport",
    "TierEntry",
    "TierImporter",
    "bootstrap_tier_definitions",
    "reconcile_external_annotations",
    "run_import",
]
