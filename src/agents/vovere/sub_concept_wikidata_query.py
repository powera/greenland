#!/usr/bin/env python3
"""Populate one sub-concept category from a simple Wikidata SPARQL query.

This is intentionally a starter tool: it supports a few common "what is this
Q-id?" patterns (instance-of/subclass trees, optional country constraint, and
minimum sitelink counts), then files the resulting Q-ids through the same
sub-concept service used by Barsukas and Voveraite.

Examples:
    PYTHONPATH=src python src/agents/vovere/sub_concept_wikidata_query.py \
        --category geography_river --class-qid Q4022 --yes
    PYTHONPATH=src python src/agents/vovere/sub_concept_wikidata_query.py \
        --category media_tv_episode --preset media_tv_episode --limit 500 --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Add src directory to path (this file lives at src/agents/vovere/)
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend import create_session as create_backend_session
from storage.backend.config import DataSourceConfig
from concepts.sub_concepts import file_sub_concept_from_qid
from storage.models.concept import ALL_SUB_CONCEPT_CATEGORIES
from storage.wikidata import normalize_qid, query_wikidata_sparql

logger = logging.getLogger(__name__)


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


class SubConceptWikidataQueryAgent:
    """Query Wikidata and file matching Q-ids as sub-concepts."""

    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        if config.debug:
            logger.setLevel(logging.DEBUG)

    def query_qids(self, sparql: str) -> List[str]:
        """Run a SPARQL query and return Q-ids from a ``?item`` binding."""
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

    def file_qids(self, qids: List[str], category: str) -> None:
        """File Q-ids into a category using the configured storage backend."""
        session = create_backend_session(self.config)
        try:
            for qid in qids:
                result = file_sub_concept_from_qid(session, qid, category)
                logger.info(
                    "%s [%s] %s%s",
                    result.status.upper(),
                    result.qid,
                    result.title,
                    f" - {result.detail}" if result.detail else "",
                )
        finally:
            session.close()


def _qid_uri(qid: str) -> str:
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
    """Build a simple SPARQL query for common Wikidata class patterns."""
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


def _load_sparql_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate a sub-concept category from a Wikidata SPARQL query."
    )
    parser.add_argument("--category", required=True, choices=ALL_SUB_CONCEPT_CATEGORIES)
    parser.add_argument(
        "--preset",
        choices=sorted(PRESET_CLASS_QIDS),
        help="Use a built-in class Q-id for a known sub-concept category.",
    )
    parser.add_argument(
        "--class-qid",
        help="Wikidata class Q-id to query (overrides the preset's class Q-id).",
    )
    parser.add_argument(
        "--pattern",
        choices=("direct-instance", "instance-tree", "subclass-tree"),
        default="instance-tree",
        help="Common SPARQL pattern to use with --class-qid/--preset.",
    )
    parser.add_argument(
        "--country-qid",
        help="Optional country Q-id constraint via wdt:P17 (e.g. Q183 for Germany).",
    )
    parser.add_argument("--min-sitelinks", type=int, default=250)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--sparql-file", help="Use a bespoke SPARQL file instead of a class query.")
    add_common_args(parser)
    add_backend_args(parser)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
    )

    class_qid = args.class_qid or (PRESET_CLASS_QIDS.get(args.preset) if args.preset else None)
    if args.sparql_file:
        sparql = _load_sparql_file(args.sparql_file)
    elif class_qid:
        sparql = build_class_query(
            class_qid=class_qid,
            pattern=args.pattern,
            country_qid=args.country_qid,
            min_sitelinks=args.min_sitelinks,
            limit=args.limit,
        )
    else:
        parser.error("Provide --preset, --class-qid, or --sparql-file.")

    config = get_data_source_config(args)
    agent = SubConceptWikidataQueryAgent(config)
    logger.info("Querying Wikidata for %s", args.category)
    qids = agent.query_qids(sparql)
    logger.info("Found %d Q-id(s)", len(qids))
    for qid in qids[:20]:
        logger.info("MATCH %s", qid)
    if len(qids) > 20:
        logger.info("...and %d more", len(qids) - 20)

    if args.dry_run:
        logger.info("Dry run; not filing sub-concepts.")
        return 0

    if not args.yes:
        confirm = input(f"\nFile {len(qids)} Q-id(s) as {args.category!r}? [y/N]: ")
        if confirm.strip().lower() != "y":
            logger.info("Aborted.")
            return 0

    agent.file_qids(qids, args.category)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
