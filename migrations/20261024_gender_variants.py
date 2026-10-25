#!/usr/bin/env python3
"""Preview the narrow cousin/actor/German-person migration; --apply after review.

Preview opens SQLite with mode=ro, bypassing schema initialization. Applying
backs up through storage.backup (major by default; --backup-tier can override),
adds the nullable variant gender column, then runs all data edits transactionally.
No release files are edited. Export them through the ordinary release pipeline
only after reviewing the database changes.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from storage.backend.config import BackendType, DataSourceConfig
from storage.backup import create_backup, database_path
from storage.backend.sqlite_pragmas import apply_sqlite_pragmas
from storage.crud.operation_log import FieldChange, log_field_changes
from storage.models.schema import Lemma, LemmaDifficultyOverride
from words.gender_variants import (
    COUSIN_GUID,
    COUSIN_MERGES,
    COUNTERPART_SEEDS,
    SOURCE,
    add_counterpart_seeds,
    merge_cousin,
)


def preview(config: DataSourceConfig) -> Dict[str, Any]:
    """Read the real database without initializing, altering, or writing it."""
    connection = sqlite3.connect(database_path(config).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        records: Dict[str, Any] = {}
        for guid in (COUSIN_GUID, *(guid for guid, _ in COUSIN_MERGES), "N36_047", "N33_005"):
            row = connection.execute(
                "SELECT id,guid,lemma_text,pos_type,pos_subtype,difficulty_level,disambiguation "
                "FROM lemmas WHERE guid=?",
                (guid,),
            ).fetchone()
            if row is None:
                records[guid] = None
                continue
            record = dict(row)
            record["translations"] = [
                dict(translation)
                for translation in connection.execute(
                    "SELECT language_code,translation FROM lemma_translations WHERE lemma_id=?",
                    (row["id"],),
                )
            ]
            record["grammar_facts"] = [
                dict(fact)
                for fact in connection.execute(
                    "SELECT language_code,fact_type,fact_value FROM grammar_facts WHERE lemma_id=?",
                    (row["id"],),
                )
            ]
            record["references"] = {}
            record["concept_facts"] = [
                dict(fact)
                for fact in connection.execute(
                    "SELECT fact_type,fact_value FROM lemma_facts WHERE lemma_id=?", (row["id"],)
                )
            ]
            for table_row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ):
                table_name = str(table_row["name"])
                # Identifiers are introspected, quoted, and never interpolated as values.
                quoted = '"' + table_name.replace('"', '""') + '"'
                columns = {
                    column["name"] for column in connection.execute(f"PRAGMA table_info({quoted})")
                }
                if "lemma_id" in columns:
                    count = connection.execute(
                        f"SELECT count(*) FROM {quoted} WHERE lemma_id=?", (row["id"],)
                    ).fetchone()[0]
                    if count:
                        record["references"][table_name] = count
            records[guid] = record
        return {
            "mode": "read-only preview",
            "schema": "ALTER TABLE variant_forms ADD COLUMN grammatical_gender VARCHAR (if absent)",
            "schema_column_present": any(
                column["name"] == "grammatical_gender"
                for column in connection.execute("PRAGMA table_info(variant_forms)")
            ),
            "default": "Ordinary lemma translation/forms and existing grammatical-gender fact; never inferred from male",
            "merge_into": COUSIN_GUID,
            "retire": [{"guid": guid, "gender_variant": gender} for guid, gender in COUSIN_MERGES],
            "seeds": [
                {"guid": guid, "language": language, "male": words[:2], "female": words[2:]}
                for (guid, language), words in COUNTERPART_SEEDS.items()
            ],
            "existing": records,
        }
    finally:
        connection.close()


def apply_changes(session: Session) -> None:
    """Apply the selected data edits to a prepared schema; caller commits."""
    for source_guid, gender in COUSIN_MERGES:
        merge_cousin(session, source_guid, gender)
    cousin = session.query(Lemma).filter_by(guid=COUSIN_GUID).one()
    definition = "A child of one's aunt or uncle; a relative who shares a common grandparent."
    changes = [
        FieldChange("disambiguation", cousin.disambiguation, None),
        FieldChange("definition_text", cousin.definition_text, definition),
    ]
    cousin.disambiguation = None
    cousin.definition_text = definition
    log_field_changes(
        session,
        source=SOURCE,
        operation_type="lemma_update",
        entity_guid=COUSIN_GUID,
        lemma_id=cousin.id,
        changes=changes,
    )
    # Exclusions existed because cousins were split by gender. The retained
    # default now exposes the counterparts, so it must remain in the curriculum.
    for override in (
        session.query(LemmaDifficultyOverride)
        .filter_by(lemma_id=cousin.id, difficulty_level=-1)
        .all()
    ):
        log_field_changes(
            session,
            source=SOURCE,
            operation_type="lemma_difficulty_override_delete",
            entity_guid=COUSIN_GUID,
            lemma_id=cousin.id,
            changes=[FieldChange("difficulty_level", -1, cousin.difficulty_level)],
            extra={"language_code": override.language_code},
        )
        session.delete(override)
    add_counterpart_seeds(session)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-tier", choices=("minor", "major"), default="major")
    args = parser.parse_args()
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)
    if not args.apply:
        print(json.dumps(preview(config), ensure_ascii=False, indent=2))
        return
    print(
        f"{args.backup_tier.title()} backup: {create_backup(config, 'gender-variants', args.backup_tier)}"
    )
    engine = create_engine(f"sqlite:///{database_path(config)}")
    apply_sqlite_pragmas(engine)
    try:
        with engine.begin() as connection:
            columns = {
                column["name"] for column in inspect(connection).get_columns("variant_forms")
            }
            if "grammatical_gender" not in columns:
                connection.execute(
                    text("ALTER TABLE variant_forms ADD COLUMN grammatical_gender VARCHAR")
                )
        with Session(engine) as session:
            with session.begin():
                apply_changes(session)
    finally:
        engine.dispose()
    print("Applied gender variants. Release files have not been exported.")


if __name__ == "__main__":
    main()
