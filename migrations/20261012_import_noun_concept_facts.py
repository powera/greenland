#!/usr/bin/env python3
"""Import only noun concept dimensions from release; retire old booleans atomically."""

import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import argparse
from datetime import datetime
import json
import sqlite3
from typing import Dict, Tuple

from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.config.lemma_fact_registry import RETIRED_LEMMA_FACT_TYPES, validate_lemma_fact
from storage.models.schema import Lemma
from storage.release.lemma import apply_lemma_facts, build_concept_label

DIMENSIONS = frozenset({"individuation", "concreteness"})


def read_facts(release_dir: Path) -> Dict[str, Tuple[str, Dict[str, str]]]:
    """Validate complete dimension pairs and sense identities before touching SQLite."""
    result: Dict[str, Tuple[str, Dict[str, str]]] = {}
    for path in sorted(release_dir.rglob("base.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            facts = record.get("facts") or {}
            if RETIRED_LEMMA_FACT_TYPES.intersection(facts):
                raise ValueError(f"Retired release facts in {path}")
            dimensions = {name: value for name, value in facts.items() if name in DIMENSIONS}
            if not dimensions:
                continue
            if dimensions.keys() != DIMENSIONS or record.get("pos_type") != "noun":
                raise ValueError(f"Incomplete or non-noun dimensions: {record.get('guid')}")
            for name, value in dimensions.items():
                error = validate_lemma_fact(name, value)
                if error:
                    raise ValueError(error)
            guid = record["guid"]
            if guid in result:
                raise ValueError(f"Duplicate release GUID: {guid}")
            result[guid] = (record["concept_label"], dimensions)
    if not result:
        raise ValueError("No noun concept dimensions found in release")
    return result


def stage_import(session: Session, release_dir: Path) -> Tuple[int, int]:
    """Preflight every sense, then stage changes while preserving unrelated facts."""
    records = read_facts(release_dir)
    lemmas = session.query(Lemma).all()
    by_guid = {lemma.guid: lemma for lemma in lemmas}
    for guid, (label, _) in records.items():
        lemma = by_guid.get(guid)
        if (
            lemma is None
            or lemma.pos_type != "noun"
            or build_concept_label(lemma.lemma_text, lemma.disambiguation) != label
        ):
            raise ValueError(f"Missing or mismatched SQLite noun sense: {guid} ({label})")
    retired = 0
    for lemma in lemmas:
        legacy = [fact for fact in lemma.lemma_facts if fact.fact_type in RETIRED_LEMMA_FACT_TYPES]
        if legacy and lemma.guid not in records:
            raise ValueError(f"Legacy facts have no reviewed release replacement: {lemma.guid}")
        retired += len(legacy)
    changed = 0
    for guid, (_, dimensions) in records.items():
        lemma = by_guid[guid]
        wanted = {
            fact.fact_type: fact.fact_value
            for fact in lemma.lemma_facts
            if fact.fact_type not in RETIRED_LEMMA_FACT_TYPES
        }
        changed += sum(wanted.get(name) != value for name, value in dimensions.items())
        wanted.update(dimensions)
        apply_lemma_facts(lemma, {"facts": wanted})
    return changed, retired


def migrate(config: DataSourceConfig, release_dir: Path, *, apply: bool = False) -> None:
    """Preview by default; back up committed WAL contents before applying."""
    if config.backend_type != BackendType.SQLITE or not config.sqlite_path:
        raise ValueError("SQLite configuration required")
    database = Path(config.sqlite_path).resolve()
    if not database.is_file():
        raise ValueError("Existing SQLite database required")
    session = create_session(config)
    try:
        changed, retired = stage_import(session, release_dir)
        if apply and (changed or retired):
            backup = database.with_name(
                f"{database.name}.bak-{datetime.now():%Y%m%d-%H%M%S-%f}-import-noun-facts"
            )
            with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as source:
                with sqlite3.connect(backup) as destination:
                    source.backup(destination)
            print(f"Backup: {backup}")
            session.commit()
        else:
            session.rollback()
        print(
            f"{'Applied' if apply else 'Preview'}: {changed} dimension writes, {retired} retired rows"
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    parser.add_argument(
        "--release-dir", type=Path, default=SOURCE_ROOT.parent / "data/release/lemmas"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    migrate(
        DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path),
        args.release_dir,
        apply=args.apply,
    )


if __name__ == "__main__":
    main()
