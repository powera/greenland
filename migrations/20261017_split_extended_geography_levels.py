#!/usr/bin/env python3
"""Split extended geography level 1031 into 1031/1032/1033, as 231-233 are split.

1031 keeps the countries and territories, 1032 takes their people, origin
adjectives and the ethnic groups, and 1033 the languages.  This names the three
levels and moves the senses still stored at 1031 that the geography catalog
now places at 1032 or 1033 (Mongolian, Igbo and Assamese, from the first
catalog import).  Run it before scripts/wordlists/import_geography_catalog.py.

Makes no LLM call.  Defaults to a rolled-back preview; pass --apply to commit,
after a backup:

  PYTHONPATH=src python -m storage.backup create --label split-geo-levels

Safe to rerun: a level already named something other than this migration's old
default keeps its name, and a sense already at its catalog level is left alone.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.curriculum_level import get_curriculum_level, set_curriculum_level
from storage.crud.operation_log import FieldChange, log_field_changes
from storage.models.schema import Lemma
from words.difficulty.geography_catalog import find_sense

SOURCE = "migration/20261017-split-extended-geography-levels"
OLD_LEVEL = 1031

# level -> (name, the earlier default name it may replace)
LEVEL_NAMES: dict[int, tuple[str, Optional[str]]] = {
    1031: ("Extended Countries", "Extended Countries, Languages and Ethnicities"),
    1032: ("Extended Nationalities and Ethnicities", None),
    1033: ("Extended Languages", None),
}


def name_levels(session: Session) -> int:
    """Name the three levels, keeping any name a person gave them."""
    named = 0
    for level, (name, replaceable) in LEVEL_NAMES.items():
        existing = get_curriculum_level(session, level)
        current = (existing.name or "").strip() if existing is not None else ""
        if current and current != replaceable:
            continue
        set_curriculum_level(
            session,
            level,
            name,
            cefr=existing.cefr if existing else None,
            prerequisites=(
                json.loads(existing.prerequisites) if existing and existing.prerequisites else ()
            ),
            extra=json.loads(existing.extra) if existing and existing.extra else None,
            notes=existing.notes if existing else None,
            source=SOURCE,
        )
        named += 1
    return named


def move_senses(session: Session) -> list[tuple[Lemma, int]]:
    """Move catalog senses at 1031 to their catalog level."""
    moves: list[tuple[Lemma, int]] = []
    for lemma in session.query(Lemma).filter(Lemma.difficulty_level == OLD_LEVEL).all():
        sense = find_sense(lemma)
        if sense is None or sense.base_level == OLD_LEVEL:
            continue
        lemma.difficulty_level = sense.base_level
        log_field_changes(
            session,
            source=SOURCE,
            operation_type="lemma_update",
            entity_guid=lemma.guid,
            lemma_id=lemma.id,
            changes=[FieldChange("difficulty_level", OLD_LEVEL, sense.base_level)],
        )
        moves.append((lemma, sense.base_level))
    return moves


def migrate(config: DataSourceConfig, *, apply: bool = False) -> int:
    """Preview or commit both steps in one transaction; returns senses moved."""
    session = create_session(config)
    try:
        named = name_levels(session)
        moves = move_senses(session)
        for lemma, level in moves:
            print(
                f"{lemma.guid}: {lemma.lemma_text} ({lemma.pos_type}/{lemma.pos_subtype})"
                f" {OLD_LEVEL} -> {level}"
            )
        if apply:
            session.commit()
        else:
            session.rollback()
        print(
            f"{'Named' if apply else 'Would name'} {named} levels;"
            f" {'moved' if apply else 'would move'} {len(moves)} senses."
        )
        return len(moves)
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    parser.add_argument(
        "--apply", action="store_true", help="Commit the changes (default: rolled-back preview)"
    )
    args = parser.parse_args()
    migrate(
        DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path),
        apply=args.apply,
    )


if __name__ == "__main__":
    main()
