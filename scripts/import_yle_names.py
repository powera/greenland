#!/usr/bin/env python3
"""Seed the ``names`` table with the given names from the Cambridge YLE lists.

The YLE wordlists carry a "Names" theme -- the characters who populate the exam
papers (Alice, Ben, Mr Chen). They are not vocabulary: a learner does not
*learn* George, and ``wordfreq.tiers.cambridge_yle`` never resolves them to a
lemma, so they fall out of every wordlist import as unmatched. They are exactly
what :class:`storage.models.name_entity.Name` was added to hold, and that table
is still empty, so this is its first batch.

51 given names, each with the gender hint the schema wants for languages that
decline names (Lithuanian) or pick honorifics by gender. The hint is a
generation aid, never a claim about a real person -- "Kim" and "Pat" are
recorded neutral because the YLE material uses them either way.

"Ben" is here only because the extractor fix split the row it was welded to
("bat (as sports equipment) Ben"); it was invisible to earlier gap reports.

Lowercase "may" is deliberately absent. It is tagged Names in the source only
because the extractor reads the theme column, not the word, and swept up the
modal verb.

This writes names but no renderings: :class:`NameTranslation` rows (``Džordžas``,
``乔治``) are an LLM job and belong in a separate run. Re-running is safe --
``get_or_create_name`` matches on (name_text, kind) and skips what exists.

Usage:
    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python scripts/import_yle_names.py
    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python scripts/import_yle_names.py --execute
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from storage.backend.config import DataSourceConfig
from storage.backend.factory import create_session
from storage.crud.name_entity import assign_name_guid, get_or_create_name

SOURCE_NOTE = "Cambridge YLE wordlist (Starters/Movers/Flyers), Names theme"

# (name_text, gender). All are given names, so kind is "given_name" throughout.
NAMES: Sequence[tuple[str, str]] = (
    # Masculine
    ("Alex", "masculine"),
    ("Ben", "masculine"),
    ("Bill", "masculine"),
    ("Charlie", "masculine"),
    ("Dan", "masculine"),
    ("David", "masculine"),
    ("Frank", "masculine"),
    ("Fred", "masculine"),
    ("George", "masculine"),
    ("Harry", "masculine"),
    ("Hugo", "masculine"),
    ("Jack", "masculine"),
    ("Jim", "masculine"),
    # Also a lemma ("mark", noun). Names are case-significant, so the two coexist.
    ("Mark", "masculine"),
    ("Matt", "masculine"),
    ("Michael", "masculine"),
    ("Nick", "masculine"),
    ("Oliver", "masculine"),
    ("Paul", "masculine"),
    ("Peter", "masculine"),
    ("Richard", "masculine"),
    ("Robert", "masculine"),
    ("Sam", "masculine"),
    ("Tom", "masculine"),
    ("William", "masculine"),
    # Feminine
    ("Alice", "feminine"),
    # YLE prints "Ann/Anna"; stored as two names.
    ("Ann", "feminine"),
    # YLE prints "Ann/Anna"; stored as two names.
    ("Anna", "feminine"),
    ("Betty", "feminine"),
    ("Clare", "feminine"),
    ("Daisy", "feminine"),
    ("Emma", "feminine"),
    ("Eva", "feminine"),
    ("Grace", "feminine"),
    ("Helen", "feminine"),
    ("Holly", "feminine"),
    ("Jane", "feminine"),
    ("Jill", "feminine"),
    ("Julia", "feminine"),
    ("Katy", "feminine"),
    ("Lily", "feminine"),
    ("Lucy", "feminine"),
    ("Mary", "feminine"),
    ("Sally", "feminine"),
    ("Sarah", "feminine"),
    ("Sophia", "feminine"),
    ("Sue", "feminine"),
    ("Vicky", "feminine"),
    ("Zoe", "feminine"),
    # Neutral
    # Used for either gender in the YLE material.
    ("Kim", "neutral"),
    # Used for either gender in the YLE material.
    ("Pat", "neutral"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write the names. Without this flag, only print the plan.",
    )
    parser.add_argument(
        "--guid",
        action="store_true",
        help="Also assign a release GUID to each name created.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"Given names to seed: {len(NAMES)}")
    for rank, (name_text, gender) in enumerate(NAMES, start=1):
        print(f"{rank:3}. {name_text:10} {gender}")

    if not args.execute:
        print("\nNo database writes made. Re-run with --execute to seed.")
        return 0

    session = create_session(DataSourceConfig())
    created = 0
    skipped = 0
    try:
        for name_text, gender in NAMES:
            name, was_created = get_or_create_name(
                session,
                name_text=name_text,
                kind="given_name",
                gender=gender,
                notes=SOURCE_NOTE,
            )
            if was_created:
                created += 1
                if args.guid:
                    assign_name_guid(session, name)
            else:
                skipped += 1
        session.commit()
    finally:
        session.close()

    print(f"\nComplete: {created} name(s) created, {skipped} already present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
