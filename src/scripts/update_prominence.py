#!/usr/bin/env python3
"""Backfill Lemma.sense_prominence based on Trakaido difficulty level.

Sets ``sense_prominence = "very_common"`` for every Lemma whose
``difficulty_level`` is between 1 and 15 inclusive. Other lemmas are left
untouched (they keep the schema default of ``"common"``, or whatever value
was set explicitly).

Idempotent: re-running only updates rows whose current value differs from
the target.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend.factory import create_session
from storage.models.schema import SENSE_PROMINENCE_VERY_COMMON, Lemma

TRAKAIDO_LEVEL_MIN: int = 1
TRAKAIDO_LEVEL_MAX: int = 15


def run(dry_run: bool, config_args: argparse.Namespace) -> int:
    config = get_data_source_config(config_args)
    session = create_session(config)
    try:
        targets = (
            session.query(Lemma)
            .filter(
                Lemma.difficulty_level >= TRAKAIDO_LEVEL_MIN,
                Lemma.difficulty_level <= TRAKAIDO_LEVEL_MAX,
                Lemma.sense_prominence != SENSE_PROMINENCE_VERY_COMMON,
            )
            .all()
        )
        print(
            f"Found {len(targets)} lemmas with difficulty_level in "
            f"[{TRAKAIDO_LEVEL_MIN}, {TRAKAIDO_LEVEL_MAX}] needing prominence update"
        )
        for lemma in targets:
            lemma.sense_prominence = SENSE_PROMINENCE_VERY_COMMON

        if dry_run:
            session.rollback()
            print("Dry run: no changes committed")
        else:
            session.commit()
            print(f"Updated {len(targets)} lemmas to sense_prominence='very_common'")
        return len(targets)
    finally:
        session.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run, config_args=args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
