"""The ``concept.seed.wikidata_query`` stage of concept creation."""

from typing import Optional

from storage.wikidata import WikidataConceptSeed, fetch_wikidata_concept_seed

STAGE_NAME: str = "concept.seed.wikidata_query"


def query_wikidata_seed(
    qid: str, *, include_regional_wikis: bool = False
) -> Optional[WikidataConceptSeed]:
    """Resolve one normalized Wikidata Q-id into a concept seed.

    Network access is intentionally isolated in this stage so callers can test
    validation, generation, and persistence without making Wikimedia calls.
    """
    return fetch_wikidata_concept_seed(qid, include_regional_wikis=include_regional_wikis)
