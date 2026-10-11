#!/usr/bin/env python3
"""Add reviewed missing geography senses without LLMs or translation guesses.

Defaults to a rollback-only preview. Use --apply after reviewing the plan and
making a WAL-safe SQLite backup. Existing GUIDs, translations and overrides are
preserved. Add --set-base-levels to normalize existing reviewed geography base
levels to 231/1031; the country level manager handles language-specific promotion.
"""

import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.lemma import add_lemma
from storage.crud.curriculum_level import get_curriculum_level, set_curriculum_level
from storage.crud.operation_log import FieldChange, log_entity_operation, log_field_changes
from storage.models.schema import Lemma
from storage.utils.guid import run_lemma_write
from words.difficulty.geography_catalog import GEOGRAPHY_SENSES, GeographySense, find_sense
from words.difficulty.country_word_priorities import COUNTRY_NAMES

SOURCE = "migration/20261009-geography-senses"


def add_missing_senses(
    session: Session, senses: tuple[GeographySense, ...] = GEOGRAPHY_SENSES
) -> list[Lemma]:
    """Stage additions atomically; reject ambiguous existing senses for review."""
    additions: list[Lemma] = []
    for sense in senses:
        matches = (
            session.query(Lemma)
            .filter(
                Lemma.lemma_text.in_((sense.lemma_text, *sense.aliases)),
                Lemma.pos_type == sense.pos_type,
                Lemma.pos_subtype == sense.pos_subtype,
            )
            .all()
        )
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous existing geography sense: {sense.lemma_text} ({sense.pos_subtype})"
            )
        if matches:
            continue
        lemma = add_lemma(
            session,
            lemma_text=sense.lemma_text,
            definition_text=sense.definition,
            pos_type=sense.pos_type,
            pos_subtype=sense.pos_subtype,
            difficulty_level=sense.base_level,
            notes="Reviewed geography starter inventory; translations require separate review.",
        )
        lemma.disambiguation = (
            "language" if sense.pos_subtype == "communication_information" else sense.pos_subtype
        )
        log_entity_operation(
            session,
            source=SOURCE,
            operation_type="lemma_create",
            entity_guid=lemma.guid,
            lemma_id=lemma.id,
            fact={
                "lemma_text": lemma.lemma_text,
                "pos_subtype": lemma.pos_subtype,
                "difficulty_level": lemma.difficulty_level,
            },
        )
        additions.append(lemma)
    return additions


def ensure_level_names(session: Session) -> int:
    """Fill missing names while preserving all existing metadata and translations."""
    updated = 0
    for level, default_name in (
        (231, "Countries"),
        (232, "Nationalities and Ethnicities"),
        (233, "Languages"),
        (1031, "Extended Countries, Languages and Ethnicities"),
    ):
        existing = get_curriculum_level(session, level)
        if existing is not None and existing.name and existing.name.strip():
            continue
        set_curriculum_level(
            session,
            level,
            default_name,
            cefr=existing.cefr if existing else None,
            prerequisites=(
                json.loads(existing.prerequisites) if existing and existing.prerequisites else ()
            ),
            extra=json.loads(existing.extra) if existing and existing.extra else None,
            notes=existing.notes if existing else None,
            source=SOURCE,
        )
        updated += 1
    return updated


def normalize_base_levels(session: Session) -> list[tuple[Lemma, int | None, int]]:
    """Normalize reviewed base levels; never touch per-language overrides."""
    changes: list[tuple[Lemma, int | None, int]] = []
    for lemma in session.query(Lemma).order_by(Lemma.id).all():
        sense = find_sense(lemma)
        if sense is not None:
            target_level = sense.base_level
        elif (
            lemma.pos_type == "noun"
            and lemma.pos_subtype == "region"
            and lemma.lemma_text in COUNTRY_NAMES
        ):
            target_level = 231
        else:
            continue
        if lemma.difficulty_level == target_level:
            continue
        old_level = lemma.difficulty_level
        lemma.difficulty_level = target_level
        log_field_changes(
            session,
            source=SOURCE,
            operation_type="lemma_update",
            entity_guid=lemma.guid,
            lemma_id=lemma.id,
            changes=[FieldChange("difficulty_level", old_level, target_level)],
        )
        changes.append((lemma, old_level, target_level))
    return changes


def migrate(config: DataSourceConfig, *, apply: bool = False, set_base_levels: bool = False) -> int:
    """Preview or commit the complete set in a single transaction."""
    session = create_session(config)

    def write_all() -> tuple[int, int, int]:
        additions = add_missing_senses(session)
        updates = normalize_base_levels(session) if set_base_levels else []
        named_levels = ensure_level_names(session) if set_base_levels else 0
        for lemma in additions:
            print(
                f"{lemma.guid}: {lemma.lemma_text} ({lemma.pos_type}/{lemma.pos_subtype}) -> {lemma.difficulty_level}"
            )
        for updated_lemma, old_level, new_level in updates:
            print(
                f"{updated_lemma.guid}: {updated_lemma.lemma_text} base level {old_level} -> {new_level}"
            )
        return len(additions), len(updates), named_levels

    try:
        # New lemmas take GUIDs, so the set is written under the lemma write lock.
        added, updated, named_levels = run_lemma_write(session, write_all, commit=apply)
        print(f"{'Added' if apply else 'Would add'} {added} senses.")
        print(f"{'Updated' if apply else 'Would update'} {updated} existing base levels.")
        print(f"{'Named' if apply else 'Would name'} {named_levels} curriculum levels.")
        return added
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    parser.add_argument(
        "--apply", action="store_true", help="Commit additions (default: rollback preview)"
    )
    parser.add_argument(
        "--set-base-levels",
        action="store_true",
        help="Also normalize reviewed existing geography base levels to 231/1031",
    )
    args = parser.parse_args()
    migrate(
        DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path),
        apply=args.apply,
        set_base_levels=args.set_base_levels,
    )


if __name__ == "__main__":
    main()
