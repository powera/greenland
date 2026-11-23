#!/usr/bin/env python3
"""Tag curriculum levels with use-case themes and content flags.

First pass at the picker hints for the extra levels, from each level's name and
words (the release files as of 2026-11-23):

* themes -- travel, school (a high-school class: textbook topics, school
  subjects, classroom language), daily-life, work, heritage (family and
  cultural life with relatives), most relevant first.  Abstract and advanced
  bins ("Describing Qualities 5", "Thinking and Influence Verbs") are left
  untagged on purpose: nothing suggests them for a goal.
* content flags -- only units where the content *is* the topic.  A unit with
  one incidental word (a lone "cigarette" in Everyday Objects 3) is not
  flagged; that needs a word-level flag the schema does not have yet.

A level that already has themes (or flags) is left alone, so curator edits in
Barsukas win and the migration is safe to rerun.  Each level's English name is
checked; a renamed level is skipped with a warning rather than tagged blind.

Preview by default (changes are rolled back).  --apply takes a minor backup
and commits.

    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20261123_tag_level_themes.py
    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20261123_tag_level_themes.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.backup import create_backup
from storage.crud.curriculum_level import get_curriculum_level, patch_curriculum_level

SOURCE = "migration/20261123-level-themes"

# level -> (expected English name, themes most relevant first)
THEMES: Dict[int, Tuple[str, List[str]]] = {
    100: ("Feelings and Reactions", ["school", "daily-life"]),
    102: ("Grandchildren, Nieces, Nephews and Parents-in-Law", ["heritage", "school"]),
    109: ("Kitchen and Household Appliances", ["daily-life"]),
    114: ("Public Buildings", ["travel", "daily-life"]),
    115: ("More Places in Town", ["travel", "daily-life"]),
    119: ("Furniture", ["daily-life", "school"]),
    120: ("Parts of Buildings", ["daily-life"]),
    125: ("More Animals", ["school"]),
    130: ("Wild and Domestic Animals", ["school"]),
    133: ("Health and Body", ["travel", "daily-life", "school"]),
    134: ("Health Care and Recovery", ["travel", "daily-life"]),
    135: ("Nature and Landscape", ["travel", "school"]),
    136: ("Reactions and Emotional Expression", ["daily-life", "heritage"]),
    140: ("Technology and Computers", ["work", "school"]),
    162: ("Measurement and Amounts", ["school"]),
    165: ("Plants and Growth", ["school"]),
    170: ("Plants and Growth 2", ["school"]),
    172: ("Drinks", ["travel", "daily-life"]),
    175: ("Having and Giving", ["daily-life"]),
    176: ("Money, Payments and Agreements", ["daily-life", "travel", "work"]),
    179: ("Materials and Substances", ["school"]),
    180: ("Materials and Substances 2", ["school"]),
    184: ("Materials and Substances 3", ["school"]),
    185: ("Electronics and Devices", ["daily-life", "work"]),
    190: ("Clothing and Accessories 2", ["daily-life", "school"]),
    194: ("Everyday Objects 2", ["daily-life"]),
    195: ("Household and Useful Objects", ["daily-life"]),
    199: ("Everyday Objects 3", ["daily-life"]),
    200: ("Everyday Objects 4", ["daily-life", "travel"]),
    205: ("Tools and Equipment", ["daily-life", "work"]),
    210: ("Vehicles 2", ["travel", "school"]),
    215: ("Holidays and Events", ["heritage", "daily-life", "travel", "school"]),
    216: ("Appointments, Services and Scheduling", ["travel", "daily-life", "work"]),
    219: ("Landforms and Natural Features", ["travel", "school"]),
    220: ("Periods and Times", ["daily-life"]),
    224: ("Units and Measurements", ["travel", "school", "daily-life"]),
    225: ("Time and Duration", ["daily-life"]),
    226: ("Prepositions of Time and Measure", ["school"]),
    231: ("Countries", ["travel", "school"]),
    232: ("Nationalities and Ethnicities", ["travel", "school", "heritage"]),
    233: ("Languages", ["travel", "school"]),
    235: ("World Cities", ["travel"]),
    240: ("U.S. States", ["school"]),
    245: ("Countries and Continents", ["travel", "school"]),
    249: ("Regions and Directions", ["travel"]),
    250: ("Position and Direction Adverbs", ["travel", "daily-life"]),
    254: ("World Geography and Places", ["travel", "school"]),
    255: ("Roads and Routes", ["travel", "daily-life"]),
    260: ("Everyday Activities 2", ["daily-life"]),
    264: ("Sports and Leisure Activities", ["daily-life", "travel"]),
    266: ("Sports and Leisure Activities 2", ["daily-life", "school"]),
    278: ("Farming and Livestock", ["heritage"]),
    279: ("Food and Cooking 2", ["daily-life", "travel", "school"]),
    281: ("Religions and Beliefs", ["heritage"]),
    295: ("Writing and Communication", ["school", "work"]),
    296: ("Work and Employment", ["work"]),
    299: ("Government and Society", ["school"]),
    300: ("Life, Risk and Well-Being", ["daily-life"]),
    302: ("More Family Relations", ["heritage", "school"]),
    303: ("More Complex Feelings", ["daily-life", "school"]),
    304: ("Linking Clauses", ["school"]),
    305: ("Jobs 2", ["work", "school"]),
    309: ("Groups and Communities", ["school"]),
    310: ("People and Roles 2", ["school"]),
    311: ("Jobs 3", ["work"]),
    312: ("Relationships and Social Interaction", ["daily-life", "heritage"]),
    314: ("Chemistry and Elements", ["school"]),
    315: ("Names and Forms of Address", ["heritage", "travel"]),
    318: ("Describing Qualities 2", ["school"]),
    319: ("Everyday Action Verbs", ["daily-life"]),
    329: ("Academic Fields and Ideas", ["school"]),
    330: ("Arts and Creative Works", ["school"]),
    340: ("Biology and Living Things", ["school"]),
    341: ("Digital Information and Access", ["daily-life", "work"]),
    359: ("Personality Traits 2", ["school", "daily-life"]),
    380: ("Math and Quantities 2", ["school"]),
    381: ("Science, Technology and Materials", ["school"]),
    400: ("Writing and Communication 2", ["work"]),
    405: ("Sports and Competition", ["school", "daily-life"]),
    406: ("Board Games", ["daily-life"]),
    409: ("Food and Ingredients 3", ["daily-life", "travel"]),
    410: ("Food and Ingredients 4", ["daily-life", "travel"]),
    415: ("Everyday Action Verbs 2", ["daily-life"]),
    421: ("Law, Government and Society", ["work"]),
    429: ("Time and Historical Periods", ["school"]),
    440: ("Language and Everyday Documents", ["travel", "daily-life", "work"]),
    445: ("Sports and Movement", ["daily-life"]),
    450: ("Illnesses and Medicines", ["travel", "daily-life"]),
    460: ("Letters, Numbers and Symbols", ["school"]),
    475: ("Managing and Changing", ["work"]),
    480: ("Speaking and Explaining", ["work"]),
    481: ("Formal Communication and Influence Verbs", ["work"]),
    485: ("Official Communication Verbs", ["work"]),
    486: ("Legal Documents", ["work"]),
    490: ("Numbers and Ordinals 2", ["school"]),
    1091: ("Ingredients, Herbs and Seasonings", ["daily-life"]),
    1092: ("Cooking Methods and Preparation", ["daily-life"]),
    1093: ("Baking, Pastry and Desserts", ["daily-life"]),
    1094: ("Kitchen Equipment and Recipe Measures", ["daily-life"]),
    1305: ("Clothing, Textiles and Personal Appearance", ["daily-life"]),
    1306: ("People, Family and Forms of Address", ["heritage"]),
    1307: ("Work, Services and Practical Administration", ["work"]),
    1309: ("Leisure, Hospitality and Social Occasions", ["daily-life", "travel"]),
}

# level -> (expected English name, content flags)
CONTENT_FLAGS: Dict[int, Tuple[str, List[str]]] = {
    172: ("Drinks", ["drugs"]),
    204: ("Weapons and Combat", ["weapons"]),
    1011: ("Anatomy and Body Systems", ["explicit-anatomy"]),
    1038: ("War and Diplomacy", ["weapons"]),
    1065: ("Religion and Society II", ["sexual"]),
    1070: ("Legal Terms and Proceedings", ["sexual"]),
}


def _apply_field(
    session: Session, field: str, table: Dict[int, Tuple[str, List[str]]]
) -> Tuple[int, int, List[str]]:
    """Set ``field`` on each listed level that has none.  Returns (set, kept, warnings)."""
    changed = kept = 0
    warnings: List[str] = []
    for level, (expected_name, values) in table.items():
        row = get_curriculum_level(session, level)
        if row is None:
            warnings.append(f"{level} ({expected_name!r}): no metadata row")
            continue
        if row.name != expected_name:
            warnings.append(f"{level}: named {row.name!r}, expected {expected_name!r}; skipped")
            continue
        current = row.get_themes() if field == "themes" else row.get_content_flags()
        if current:
            kept += 1
            continue
        print(f"{level}: {field} = {values}  ({row.name})")
        patch_curriculum_level(session, level, source=SOURCE, **{field: values})
        changed += 1
    return changed, kept, warnings


def migrate(config: DataSourceConfig, *, apply: bool = False) -> None:
    """Tag the listed levels; roll back unless ``apply``."""
    if apply:
        print(f"Minor backup: {create_backup(config, label='level-themes')}")
    session = create_session(config)
    try:
        for field, table in (("themes", THEMES), ("content_flags", CONTENT_FLAGS)):
            changed, kept, warnings = _apply_field(session, field, table)
            for warning in warnings:
                print(f"  warning: {warning}")
            print(
                f"{field}: {changed} level(s) set, {kept} already tagged"
                + ("" if apply else " (preview)")
            )
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
