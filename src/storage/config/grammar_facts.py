"""Configuration for grammar facts in the release file pipeline."""

from typing import Dict, Set

# Grammar fact types included in release files, keyed by language code.
# Only these fact types are imported/exported via the release pipeline.
RELEASE_GRAMMAR_FACT_TYPES: Dict[str, Set[str]] = {
    "lt": {"3p_present", "3p_past"},
}
