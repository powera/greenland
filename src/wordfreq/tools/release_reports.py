"""
Reports for analyzing data in data/release directory.

Usage:
    from wordfreq.tools.release_reports import (
        report_by_level,
        report_by_subtype,
    )

    # Get counts by trakaido level, grouped by pos_type and pos_subtype
    level_report = report_by_level()

    # Get counts by pos_subtype
    subtype_report = report_by_subtype()
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Iterator, Optional


def _get_release_dir() -> Path:
    """Get the data/release/lemmas directory path."""
    # Navigate from src/wordfreq/tools to repo root
    repo_root = Path(__file__).parent.parent.parent.parent
    return repo_root / "data" / "release" / "lemmas"


def _iter_all_lemmas(release_dir: Optional[Path] = None) -> Iterator[dict[str, Any]]:
    """Iterate over all lemmas in the release directory."""
    if release_dir is None:
        release_dir = _get_release_dir()

    for jsonl_file in release_dir.rglob("base.jsonl"):
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


def report_by_level(release_dir: Optional[Path] = None) -> dict:
    """
    Report word counts by trakaido level, showing groups (pos_type/pos_subtype).

    Returns a dict structured as:
    {
        level: {
            "total": count,
            "by_pos_type": {
                pos_type: {
                    "total": count,
                    "subtypes": {subtype: count, ...}
                }
            }
        }
    }

    Levels: -1 means excluded, 1-20 are active levels.
    """
    # Structure: level -> pos_type -> subtype -> count
    data: DefaultDict[Optional[int], DefaultDict[str, DefaultDict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )

    for lemma in _iter_all_lemmas(release_dir):
        level = lemma.get("difficulty_level")
        pos_type = lemma.get("pos_type", "unknown")
        pos_subtype = lemma.get("pos_subtype", "unknown")

        data[level][pos_type][pos_subtype] += 1

    # Build structured report
    report = {}
    for level in sorted(data.keys(), key=lambda x: (x is None, x or 0)):
        level_data = data[level]
        level_total = 0
        by_pos_type = {}

        for pos_type in sorted(level_data.keys()):
            subtypes = level_data[pos_type]
            pos_total = sum(subtypes.values())
            level_total += pos_total
            by_pos_type[pos_type] = {
                "total": pos_total,
                "subtypes": dict(sorted(subtypes.items())),
            }

        report[level] = {
            "total": level_total,
            "by_pos_type": by_pos_type,
        }

    return report


def report_by_subtype(release_dir: Optional[Path] = None) -> dict:
    """
    Report total word counts by pos_subtype.

    Returns a dict structured as:
    {
        pos_type: {
            "total": count,
            "subtypes": {
                subtype: count,
                ...
            }
        }
    }
    """
    # Structure: pos_type -> subtype -> count
    data: DefaultDict[str, DefaultDict[str, int]] = defaultdict(lambda: defaultdict(int))

    for lemma in _iter_all_lemmas(release_dir):
        pos_type = lemma.get("pos_type", "unknown")
        pos_subtype = lemma.get("pos_subtype", "unknown")
        data[pos_type][pos_subtype] += 1

    # Build structured report
    report = {}
    for pos_type in sorted(data.keys()):
        subtypes = data[pos_type]
        report[pos_type] = {
            "total": sum(subtypes.values()),
            "subtypes": dict(sorted(subtypes.items())),
        }

    return report


def print_level_report(report: Optional[dict] = None) -> None:
    """Print a formatted level report to stdout."""
    if report is None:
        report = report_by_level()

    print("=" * 60)
    print("WORDS BY TRAKAIDO LEVEL")
    print("=" * 60)

    grand_total = sum(level_data["total"] for level_data in report.values())

    for level, level_data in report.items():
        level_str = str(level) if level is not None else "None"
        if level == -1:
            level_str = "-1 (excluded)"

        print(f"\nLevel {level_str}: {level_data['total']} words")
        print("-" * 40)

        for pos_type, pos_data in level_data["by_pos_type"].items():
            print(f"  {pos_type}: {pos_data['total']}")
            for subtype, count in pos_data["subtypes"].items():
                print(f"    - {subtype}: {count}")

    print("\n" + "=" * 60)
    print(f"GRAND TOTAL: {grand_total} words")
    print("=" * 60)


def print_subtype_report(report: Optional[dict] = None) -> None:
    """Print a formatted subtype report to stdout."""
    if report is None:
        report = report_by_subtype()

    print("=" * 60)
    print("WORDS BY SUBTYPE")
    print("=" * 60)

    grand_total = sum(pos_data["total"] for pos_data in report.values())

    for pos_type, pos_data in report.items():
        print(f"\n{pos_type}: {pos_data['total']} total")
        print("-" * 40)
        for subtype, count in pos_data["subtypes"].items():
            print(f"  {subtype}: {count}")

    print("\n" + "=" * 60)
    print(f"GRAND TOTAL: {grand_total} words")
    print("=" * 60)
