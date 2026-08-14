"""Concept seed acquisition and Q-id intake.

Only the seed-query stage is re-exported here: :mod:`concepts.seed.qids` builds
on :mod:`concepts.pipeline`, which imports this package, so importing it eagerly
would be circular. Import it directly instead::

    from concepts.seed.qids import create_concepts_from_qids
"""

from concepts.seed.wikidata_query import (
    PRESET_CLASS_QIDS,
    build_class_query,
    query_class_qids,
    query_wikidata_seed,
)

__all__ = [
    "PRESET_CLASS_QIDS",
    "build_class_query",
    "query_class_qids",
    "query_wikidata_seed",
]
