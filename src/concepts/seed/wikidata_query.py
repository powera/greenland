"""The ``concept.seed.wikidata_query`` stage of concept creation.

Two kinds of Wikidata lookup live here:

* :func:`query_wikidata_seed` resolves one known Q-id into a concept seed, and
* :func:`build_class_query` / :func:`query_class_qids` *discover* Q-ids by
  class, which is how a sub-concept category is populated in bulk.

Network access is intentionally isolated in this stage so callers can test
validation, generation, and persistence without making Wikimedia calls.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from storage.wikidata import (
    WikidataConceptSeed,
    fetch_wikidata_concept_seed,
    normalize_qid,
    query_wikidata_sparql,
)

STAGE_NAME: str = "concept.seed.wikidata_query"

__all__ = [
    "PRESET_CLASS_QIDS",
    "STAGE_NAME",
    "build_class_query",
    "query_class_qids",
    "query_wikidata_seed",
]

# Wikidata class Q-ids that populate a known sub-concept category. These are
# starter defaults: the class is the "what is this?" anchor of the query, and a
# caller can always override it with an explicit class Q-id or a bespoke SPARQL
# file.
PRESET_CLASS_QIDS: Dict[str, str] = {
    "geography_administrative_division": "Q56061",
    "geography_airport": "Q1248784",
    "geography_building": "Q41176",
    "geography_city": "Q515",
    "geography_island": "Q23442",
    "geography_lake": "Q23397",
    "geography_mountain": "Q8502",
    "geography_mountain_range": "Q46831",
    "geography_protected_area": "Q473972",
    "geography_railway_station": "Q55488",
    "geography_river": "Q4022",
    "geography_road": "Q34442",
    "geography_town": "Q3957",
    "geography_village": "Q532",
    "media_album": "Q482994",
    "media_book": "Q571",
    "media_comic": "Q1004",
    "media_film": "Q11424",
    "media_game": "Q7889",
    "media_song": "Q7366",
    "media_tv_episode": "Q1983062",
    "media_tv_season": "Q3464665",
    "sports_team": "Q12973014",
}


def query_wikidata_seed(
    qid: str, *, include_regional_wikis: bool = False
) -> Optional[WikidataConceptSeed]:
    """Resolve one normalized Wikidata Q-id into a concept seed."""
    return fetch_wikidata_concept_seed(qid, include_regional_wikis=include_regional_wikis)


def _qid_uri(qid: str) -> str:
    """Return the ``wd:`` SPARQL prefix form of a Q-id."""
    normalized_qid = normalize_qid(qid)
    if normalized_qid is None:
        raise ValueError(f"Invalid Q-id: {qid!r}")
    return f"wd:{normalized_qid}"


def build_class_query(
    *,
    class_qid: str,
    pattern: str,
    country_qid: Optional[str],
    min_sitelinks: int,
    limit: int,
) -> str:
    """Build a SPARQL query for a common Wikidata class pattern.

    Args:
        class_qid: The class Q-id every match must be typed against.
        pattern: One of ``direct-instance`` (``wdt:P31``), ``instance-tree``
            (``wdt:P31/wdt:P279*``), or ``subclass-tree`` (``wdt:P279*``).
        country_qid: Optional country constraint applied via ``wdt:P17``.
        min_sitelinks: Minimum sitelink count, a rough notability floor.
        limit: Maximum number of rows to request.

    Returns:
        A SPARQL query selecting ``?item`` ordered by descending sitelinks.

    Raises:
        ValueError: If a supplied Q-id is not a valid Q-id.
    """
    class_uri = _qid_uri(class_qid)
    if pattern == "direct-instance":
        type_clause = f"?item wdt:P31 {class_uri} ."
    elif pattern == "instance-tree":
        type_clause = f"?item wdt:P31/wdt:P279* {class_uri} ."
    else:
        type_clause = f"?item wdt:P279* {class_uri} ."

    country_clause = ""
    if country_qid:
        country_clause = f"?item wdt:P17 {_qid_uri(country_qid)} ."

    return f"""
SELECT ?item ?itemLabel ?sitelinks WHERE {{
  {type_clause}
  {country_clause}
  ?item wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sitelinks})
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY DESC(?sitelinks)
LIMIT {limit}
""".strip()


def query_class_qids(sparql: str) -> List[str]:
    """Run a SPARQL query and return the Q-ids bound to ``?item``.

    Args:
        sparql: A query selecting an ``?item`` binding.

    Returns:
        Normalized Q-ids, in result order.

    Raises:
        RuntimeError: If the Wikidata endpoint never answered.
    """
    data = query_wikidata_sparql(sparql)
    if data is None:
        raise RuntimeError("Wikidata SPARQL query failed after retries")
    qids: List[str] = []
    for binding in data.get("results", {}).get("bindings", []):
        item_uri = binding.get("item", {}).get("value", "")
        qid = normalize_qid(item_uri.rsplit("/", 1)[-1])
        if qid is not None:
            qids.append(qid)
    return qids
