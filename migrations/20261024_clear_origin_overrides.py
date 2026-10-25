#!/usr/bin/env python3
"""Leave origin adjectives at their base levels by clearing language overrides.

Preview by default; --apply takes a minor backup before changing the database.
Safe to rerun. Country, person and language entries are untouched.
"""

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.backup import create_backup
from storage.crud.operation_log import log_entity_operation
from storage.models.schema import Lemma, LemmaDifficultyOverride


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db-path")
    args = parser.parse_args()
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)
    with create_session(config) as session:
        rows = (
            session.query(Lemma, LemmaDifficultyOverride)
            .join(LemmaDifficultyOverride, LemmaDifficultyOverride.lemma_id == Lemma.id)
            .filter(Lemma.pos_type == "adjective", Lemma.pos_subtype == "origin")
            .all()
        )
        print(f"{len(rows)} overrides across {len({lemma.id for lemma, _ in rows})} adjectives")
        for lemma, override in rows:
            print(
                f"{lemma.guid} {lemma.lemma_text} [{override.language_code}]: "
                f"{override.difficulty_level} -> base {lemma.difficulty_level}"
            )
        if not args.apply or not rows:
            return
        print(f"Minor backup: {create_backup(config, 'origin-overrides')}")
        for lemma, override in rows:
            log_entity_operation(
                session,
                source="migration/clear-origin-overrides",
                operation_type="lemma_difficulty_override_delete",
                entity_guid=lemma.guid,
                lemma_id=lemma.id,
                fact={
                    "language_code": override.language_code,
                    "old_value": override.difficulty_level,
                    "new_value": None,
                    "base_level": lemma.difficulty_level,
                },
            )
            session.delete(override)
        session.commit()
        print(f"Cleared {len(rows)} overrides.")


if __name__ == "__main__":
    main()
