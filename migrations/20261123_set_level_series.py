#!/usr/bin/env python3
"""Record series and volume on the existing multi-volume curriculum levels.

``curriculum_levels.series`` / ``volume`` are now the one place a topic split
over several levels is recorded (``quality.curriculum_volumes`` used to keep
its own list).  This sets them for:

* the five families that list held, which word placement treats as
  interchangeable volumes (shared CEFR and subject-boundary notes); and
* the numbered levels whose volume 1 exists under the bare name;
* numbered levels whose volume 1 is a core level (the series starts at the
  first extra level instead);
* advanced and "II" continuations that their notes name.

Single numbered levels with no partner outside the core (Clothing and
Accessories 2, Vehicles 2, Personality Traits 2, ...) stay standalone.

Each level's current English name is checked first, so a renamed or
renumbered level stops the run rather than joining the wrong series.

Preview by default (changes are rolled back).  --apply takes a minor backup
and commits.  Safe to rerun: levels already in the right series are skipped,
and one already in a *different* series stops the run.

    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20261123_set_level_series.py
    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20261123_set_level_series.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.backup import create_backup
from storage.crud.curriculum_level import (
    get_curriculum_level,
    patch_curriculum_level,
    validate_curriculum_levels,
)

SOURCE = "migration/20261123-level-series"

# series slug -> [(level, expected English name)] in volume order.
SERIES: Dict[str, List[Tuple[int, str]]] = {
    # The former quality.curriculum_volumes.VOLUME_FAMILIES.
    "advanced-character-thought-feelings": [
        (1300, "Advanced Character, Thought and Feelings"),
        (1310, "Advanced Character, Thought and Feelings 2"),
        (1311, "Advanced Character, Thought and Feelings 3"),
    ],
    "advanced-actions-change-movement": [
        (1301, "Advanced Actions, Change and Movement"),
        (1320, "Advanced Actions, Change and Movement 2"),
        (1321, "Advanced Actions, Change and Movement 3"),
    ],
    "figurative-language-imagery": [
        (1182, "Figurative Language and Imagery"),
        (1330, "Figurative Language and Imagery 2"),
    ],
    "adverbs": [(105, "Adverbs"), (324, "Adverbs 2")],
    "advanced-adverbs": [(1340, "Advanced Adverbs"), (1341, "Advanced Adverbs 2")],
    # Numbered levels whose first volume exists under the bare name.
    "advanced-medicines": [
        (1140, "Advanced Medicines"),
        (1150, "Advanced Medicines 2"),
        (1160, "Advanced Medicines 3"),
    ],
    "events-and-processes": [
        (196, "Events and Processes"),
        (285, "Events and Processes 2"),
        (289, "Events and Processes 3"),
        (290, "Events and Processes 4"),
        (476, "Events and Processes 5"),
    ],
    "everyday-action-verbs": [(319, "Everyday Action Verbs"), (415, "Everyday Action Verbs 2")],
    "materials-and-substances": [
        (179, "Materials and Substances"),
        (180, "Materials and Substances 2"),
        (184, "Materials and Substances 3"),
    ],
    "plants-and-growth": [(165, "Plants and Growth"), (170, "Plants and Growth 2")],
    "sports-and-leisure-activities": [
        (264, "Sports and Leisure Activities"),
        (266, "Sports and Leisure Activities 2"),
    ],
    "writing-and-communication": [
        (295, "Writing and Communication"),
        (400, "Writing and Communication 2"),
    ],
    # Numbered levels whose first volume is a core level (Jobs and Places in
    # Town, Activities and Everyday Objects, ...): the series starts at the
    # first extra level, so finishing the late core is not a hard gate.  The
    # volume number is the order within the series, not the number in the name.
    "jobs": [(305, "Jobs 2"), (311, "Jobs 3")],
    "everyday-objects": [
        (194, "Everyday Objects 2"),
        (199, "Everyday Objects 3"),
        (200, "Everyday Objects 4"),
    ],
    "describing-qualities": [
        (318, "Describing Qualities 2"),
        (320, "Describing Qualities 3"),
        (355, "Describing Qualities 4"),
        (430, "Describing Qualities 5"),
        (469, "Describing Qualities 6"),
    ],
    "everyday-concepts": [(274, "Everyday Concepts 3"), (275, "Everyday Concepts 4")],
    "food-and-ingredients": [(409, "Food and Ingredients 3"), (410, "Food and Ingredients 4")],
    "food-and-cooking": [
        (279, "Food and Cooking 2"),
        (1090, "Food and Cooking 3"),
        (1095, "Food and Cooking 4"),
    ],
    # Same topic under a slightly different first name.
    "abstract-concepts": [(221, "Abstract Ideas and Concepts"), (270, "Abstract Concepts 2")],
    "regions-and-locations": [(249, "Regions and Directions"), (350, "Regions and Locations 2")],
    # Advanced continuations, as their notes say ("a continuation of 100").
    "feelings-and-reactions": [
        (100, "Feelings and Reactions"),
        (1350, "Advanced Feelings and Reactions"),
    ],
    "ideas-roles-results": [
        (222, "Ideas, Roles and Results"),
        (1351, "Advanced Ideas, Roles and Results"),
    ],
    "describing-qualifying-words": [
        (106, "Describing and Qualifying Words"),
        (1352, "Advanced Describing and Qualifying Words"),
    ],
    # Topic-band "II" units, each noted as a continuation of the first.
    "biology-and-anatomy": [
        (1010, "Advanced Biology and Anatomy"),
        (1015, "Biology and Anatomy II"),
    ],
    "geography-and-migration": [
        (1020, "Advanced Geography and Migration"),
        (1025, "Geography and Migration II"),
    ],
    "industrial-technology": [
        (1040, "Industrial Technology and Processes"),
        (1045, "Industrial Technology and Processes II"),
    ],
    "religion-and-society": [
        (1060, "Religion and Social Theory"),
        (1065, "Religion and Society II"),
    ],
    "legal-terms": [
        (1070, "Legal Terms and Proceedings"),
        (1075, "Legal Terms and Proceedings II"),
    ],
    "linguistics": [(1110, "Linguistics and Language"), (1115, "Linguistics and Language II")],
}


def migrate(config: DataSourceConfig, *, apply: bool = False) -> None:
    """Set series/volume on the listed levels; roll back unless ``apply``."""
    if apply:
        print(f"Minor backup: {create_backup(config, label='level-series')}")
    session = create_session(config)
    try:
        changed = skipped = 0
        for series, members in SERIES.items():
            for volume, (level, expected_name) in enumerate(members, start=1):
                row = get_curriculum_level(session, level)
                if row is None:
                    raise ValueError(f"Level {level} ({expected_name!r}) has no metadata row")
                if row.name != expected_name:
                    raise ValueError(
                        f"Level {level} is named {row.name!r}, expected {expected_name!r}"
                    )
                if row.series == series and row.volume == volume:
                    skipped += 1
                    continue
                if row.series is not None:
                    raise ValueError(
                        f"Level {level} is already volume {row.volume} of {row.series!r}"
                    )
                print(f"{level}: {series} volume {volume}  ({row.name})")
                patch_curriculum_level(session, level, source=SOURCE, series=series, volume=volume)
                changed += 1
        problems = validate_curriculum_levels(session)
        for problem in problems:
            print(f"  warning: {problem}")
        print(f"{changed} level(s) set, {skipped} already set" + ("" if apply else " (preview)"))
        if apply:
            session.commit()
        else:
            session.rollback()
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db-path")
    args = parser.parse_args()
    migrate(DataSourceConfig(sqlite_path=args.db_path), apply=args.apply)


if __name__ == "__main__":
    main()
