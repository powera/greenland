"""Report POS-subtype coverage and vocabulary difficulty distribution."""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import func

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend import create_session
from storage.models.schema import Lemma

logger = logging.getLogger(__name__)


def check_subtype_coverage(session: Any, *, min_expected: int = 10) -> Dict[str, Any]:
    """Return POS subtypes grouped above and below a coverage threshold."""
    try:
        subtype_counts = (
            session.query(Lemma.pos_type, Lemma.pos_subtype, func.count(Lemma.id).label("count"))
            .filter(Lemma.pos_subtype.isnot(None), Lemma.pos_subtype != "")
            .group_by(Lemma.pos_type, Lemma.pos_subtype)
            .all()
        )
        well_covered = []
        under_covered = []
        for pos_type, pos_subtype, count in subtype_counts:
            entry = {"pos_type": pos_type, "pos_subtype": pos_subtype, "count": count}
            if count >= min_expected:
                well_covered.append(entry)
            else:
                under_covered.append(entry)
        under_covered.sort(key=lambda entry: entry["count"])
        return {
            "total_subtypes": len(subtype_counts),
            "well_covered_count": len(well_covered),
            "under_covered_count": len(under_covered),
            "well_covered": well_covered,
            "under_covered": under_covered,
            "min_expected_threshold": min_expected,
        }
    except Exception as error:
        logger.error("Error checking subtype coverage: %s", error)
        return {
            "error": str(error),
            "total_subtypes": 0,
            "well_covered_count": 0,
            "under_covered_count": 0,
            "well_covered": [],
            "under_covered": [],
        }


def check_difficulty_level_distribution(session: Any) -> Dict[str, Any]:
    """Return curated lemma counts and imbalance information for levels 1-20."""
    try:
        level_counts = (
            session.query(Lemma.difficulty_level, func.count(Lemma.id).label("count"))
            .filter(Lemma.difficulty_level.isnot(None), Lemma.guid.isnot(None))
            .group_by(Lemma.difficulty_level)
            .order_by(Lemma.difficulty_level)
            .all()
        )
        distribution = {level: count for level, count in level_counts}
        total_words = sum(distribution.values())
        average_per_level = total_words / 20 if total_words > 0 else 0
        gaps = []
        imbalanced = []
        for level in range(1, 21):
            count = distribution.get(level, 0)
            if count == 0:
                gaps.append(level)
            elif average_per_level > 0 and count < average_per_level * 0.5:
                imbalanced.append(
                    {"level": level, "count": count, "expected_avg": average_per_level}
                )
        return {
            "total_words": total_words,
            "distribution": distribution,
            "average_per_level": average_per_level,
            "gaps": gaps,
            "imbalanced": imbalanced,
        }
    except Exception as error:
        logger.error("Error checking difficulty level distribution: %s", error)
        return {
            "error": str(error),
            "total_words": 0,
            "distribution": {},
            "gaps": [],
            "imbalanced": [],
        }


def print_report(report_name: str, results: Dict[str, Any]) -> None:
    """Print one vocabulary distribution report."""
    if "error" in results:
        print(f"Error: {results['error']}")
    elif report_name == "subtypes":
        print(
            f"Under-covered subtypes: {results['under_covered_count']} "
            f"out of {results['total_subtypes']}"
        )
    else:
        print(f"Empty difficulty levels: {len(results['gaps'])}")
        print(f"Imbalanced levels: {len(results['imbalanced'])}")


def main() -> None:
    """Run vocabulary distribution reports from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument("report", choices=("subtypes", "levels", "all"), default="all", nargs="?")
    parser.add_argument("--min-subtype-count", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        results: Dict[str, Any] = {}
        if args.report in ("subtypes", "all"):
            results["subtypes"] = check_subtype_coverage(
                session,
                min_expected=args.min_subtype_count,
            )
        if args.report in ("levels", "all"):
            results["levels"] = check_difficulty_level_distribution(session)
    finally:
        session.close()

    for report_name, report_results in results.items():
        print_report(report_name, report_results)
    if args.output is not None:
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
