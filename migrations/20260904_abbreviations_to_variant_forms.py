#!/usr/bin/env python3
"""
Migration: move ``abbreviation`` / ``expanded_form`` rows into ``variant_forms``.

An abbreviation is the same lemma at a different length -- "TV" for
"television" -- so it is a *variant*, another way of writing the word, and not
a grammatical slot of it.  It also needs a paradigm of its own ("TVs"), which a
single ``derivative_forms`` row cannot hold.  ``derivative_forms`` now holds
inflections only; see ``storage.models.variant_form``.

Each migrated row becomes a one-form variant paradigm keyed by its own text,
under ``variant_kind`` "abbreviation" or "expanded".  The paradigm is not
expanded mechanically here: these rows were written without one, and inventing
the remaining slots during a migration would fabricate spellings no generator
vouched for.  ``words.synonyms.store_spelling_variants`` expands new ones going
forward, and a human can fill these in from Barsukas.

The ``grammatical_form`` a variant row needs is the lemma's own base slot
(``noun/en_singular`` for a noun), which ``derivative_forms`` does not record
for these rows -- the old ``grammatical_form`` was the marker itself.  It is
recovered from the lemma's part of speech via the same
``langtools.form_registry`` mapping the variant writer uses, so a row lands in
the slot its paradigm would have used.  A lemma whose POS has no registered
mapping is reported and left alone rather than guessed at.

Idempotent: ``add_variant_form`` upserts on
(lemma, language, kind, key, grammatical_form), and a source row is deleted
only after its variant row exists, so a re-run over a half-finished migration
finishes it.  Re-running after completion finds nothing and reports zero.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from typing import Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.variant_form import add_variant_form
from storage.models.schema import DerivativeForm, Lemma
from storage.models.variant_form import (
    VARIANT_KIND_ABBREVIATION,
    VARIANT_KIND_EXPANDED,
)
from words.synonyms import variant_base_grammatical_form

# The legacy ``grammatical_form`` markers, and the variant kind each becomes.
LEGACY_KIND_BY_FORM: Dict[str, str] = {
    "abbreviation": VARIANT_KIND_ABBREVIATION,
    "expanded_form": VARIANT_KIND_EXPANDED,
}

MIGRATION_SOURCE = "migration:20260904_abbreviations_to_variant_forms"


@dataclass
class MigrationResult:
    """What the migration found and did."""

    rows_scanned: int = 0
    rows_migrated: int = 0
    rows_skipped: List[str] = field(default_factory=list)


def _legacy_rows(session: Session) -> List[DerivativeForm]:
    """Every derivative form still carrying a legacy alternative-form marker."""
    return (
        session.query(DerivativeForm)
        .filter(DerivativeForm.grammatical_form.in_(tuple(LEGACY_KIND_BY_FORM)))
        .order_by(DerivativeForm.id)
        .all()
    )


def migrate_row(
    session: Session,
    row: DerivativeForm,
    result: MigrationResult,
    dry_run: bool = False,
) -> None:
    """Move one legacy row into ``variant_forms``, or record why it was skipped."""
    result.rows_scanned += 1

    lemma: Optional[Lemma] = session.query(Lemma).filter(Lemma.id == row.lemma_id).first()
    if lemma is None:
        result.rows_skipped.append(f"form {row.id} ({row.derivative_form_text!r}): no such lemma")
        return

    text = (row.derivative_form_text or "").strip()
    if not text:
        result.rows_skipped.append(f"form {row.id}: empty text")
        return

    base_grammatical_form = variant_base_grammatical_form(row.language_code, lemma.pos_type)
    if base_grammatical_form is None:
        result.rows_skipped.append(
            f"form {row.id} ({text!r}): no base slot for "
            f"{row.language_code}/{lemma.pos_type}; migrate by hand"
        )
        return

    if dry_run:
        result.rows_migrated += 1
        return

    add_variant_form(
        session=session,
        lemma=lemma,
        variant_form_text=text,
        language_code=row.language_code,
        variant_key=text,
        grammatical_form=base_grammatical_form,
        variant_kind=LEGACY_KIND_BY_FORM[row.grammatical_form],
        is_base_form=True,
        verified=bool(row.verified),
        notes=row.notes,
        source=MIGRATION_SOURCE,
    )
    # Delete only once the variant row exists, so an interrupted run leaves the
    # source row in place and is finished by the next one.
    session.delete(row)
    session.commit()
    result.rows_migrated += 1


def run_migration(config: DataSourceConfig, dry_run: bool = False) -> MigrationResult:
    """Migrate every legacy abbreviation/expanded-form row."""
    result = MigrationResult()
    session = create_session(config)
    try:
        for row in _legacy_rows(session):
            migrate_row(session, row, result, dry_run=dry_run)
    finally:
        session.close()
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse command-line arguments and run the migration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        type=str,
        default=None,
        help="SQLite database to migrate (default: the configured database)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would move without writing",
    )
    args = parser.parse_args(argv)

    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.sqlite_path)
    result = run_migration(config, dry_run=args.dry_run)

    action = "Would migrate" if args.dry_run else "Migrated"
    print(f"Scanned {result.rows_scanned} legacy rows")
    print(f"{action} {result.rows_migrated} into variant_forms")
    for skipped in result.rows_skipped:
        print(f"SKIPPED: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
