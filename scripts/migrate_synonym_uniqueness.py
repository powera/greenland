#!/usr/bin/env python3
"""Report (and optionally clean up) cross-lemma synonym duplicates in derivative_forms.

The new partial unique index ``ix_derivative_forms_synonym_unique_per_lang``
requires that a synonym-class surface form attach to at most one Lemma in a
given language. This script finds existing rows that violate that rule.

Usage:
    PYTHONPATH=src python scripts/migrate_synonym_uniqueness.py [--db PATH] [--report-only] [--apply]

By default runs in report-only mode and prints a summary plus the conflict groups.
``--apply`` is reserved for a future cleanup pass and is intentionally not
implemented yet so the report can be reviewed first.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

if str(Path(__file__).parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import SYNONYM_GRAMMATICAL_FORMS, DerivativeForm, Lemma


def find_duplicates(
    session: Session,
) -> Dict[Tuple[str, str], List[DerivativeForm]]:
    """Group synonym-class rows by ``(language_code, derivative_form_text)``.

    Returns only groups that span more than one ``lemma_id`` (the actual rule
    violations). Same-lemma duplicates are blocked by the existing
    ``uq_derivative_form`` constraint and are not reported here.
    """
    rows: List[DerivativeForm] = (
        session.query(DerivativeForm)
        .filter(DerivativeForm.grammatical_form.in_(tuple(SYNONYM_GRAMMATICAL_FORMS)))
        .all()
    )

    groups: Dict[Tuple[str, str], List[DerivativeForm]] = defaultdict(list)
    for row in rows:
        groups[(row.language_code, row.derivative_form_text)].append(row)

    conflicts: Dict[Tuple[str, str], List[DerivativeForm]] = {}
    for key, group in groups.items():
        lemma_ids = {r.lemma_id for r in group}
        if len(lemma_ids) > 1:
            conflicts[key] = group
    return conflicts


def report(session: Session, conflicts: Dict[Tuple[str, str], List[DerivativeForm]]) -> None:
    if not conflicts:
        print("No cross-lemma synonym duplicates found.")
        return

    total_rows = sum(len(g) for g in conflicts.values())
    print(
        f"Found {len(conflicts)} (language, form) groups with cross-lemma synonym conflicts "
        f"covering {total_rows} rows.\n"
    )

    from typing import Optional

    lemma_cache: Dict[int, Optional[Lemma]] = {}

    def lemma_label(lemma_id: int) -> str:
        if lemma_id not in lemma_cache:
            lemma_cache[lemma_id] = (
                session.query(Lemma).filter(Lemma.id == lemma_id).first()
            )
        lemma = lemma_cache[lemma_id]
        if lemma is None:
            return f"<missing lemma {lemma_id}>"
        disambig = f" ({lemma.disambiguation})" if lemma.disambiguation else ""
        return f"{lemma.lemma_text}{disambig} [id={lemma.id}, guid={lemma.guid}]"

    for (lang, form_text), group in sorted(conflicts.items()):
        print(f"  [{lang}] {form_text!r}:")
        for row in sorted(group, key=lambda r: (r.lemma_id, r.id)):
            print(
                f"    - row_id={row.id} lemma={lemma_label(row.lemma_id)} "
                f"grammatical_form={row.grammatical_form} verified={row.verified}"
            )
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default="data/wordfreq/linguistics.sqlite",
        help="Path to SQLite database file (default: data/wordfreq/linguistics.sqlite)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        default=True,
        help="Report conflicts only (default; no changes made)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reserved: would delete duplicate rows. Not implemented yet.",
    )
    args = parser.parse_args()

    if args.apply:
        print("--apply is not implemented; review the report first.", file=sys.stderr)
        return 2

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 1

    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        conflicts = find_duplicates(session)
        report(session, conflicts)

    return 0 if not conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
