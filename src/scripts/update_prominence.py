#!/usr/bin/env python3
"""Backfill Lemma.sense_prominence for lemmas that share a spelling, via an LLM.

``sense_prominence`` weights the split of a surface form's corpus frequency
between the lemmas competing for it (see
``wordfreq.lexeme_frequency.get_token_share``). A lemma with no homograph takes
the full frequency whatever its label, so this only visits ``lemma_text``
values held by two or more lemmas -- all the senses of one spelling go into a
single call, since the judgment is comparative.

This replaces an earlier heuristic that set ``very_common`` for anything with a
Trakaido difficulty_level of 1-15. That conflated two different things: how
early a word is taught, and which of its meanings a reader encounters. "top"
the spinning toy is easy vocabulary and a rare sense of the written word.

Idempotent: a lemma is written only when the model's answer differs from what
is stored. Use ``--only-unrated`` to skip spellings that already carry a rating;
an unrated sense is NULL, and stays eligible until something writes a label.

Examples:
  # See what would be rated, no LLM calls at all
  PYTHONPATH=src python src/scripts/update_prominence.py --list

  # Rate ten spellings and show the answers without writing
  PYTHONPATH=src python src/scripts/update_prominence.py --limit 10 --dry-run

  # Rate everything unrated and commit
  PYTHONPATH=src python src/scripts/update_prominence.py --only-unrated
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_llm_args,
    get_data_source_config,
)
from storage.backend.factory import create_session
from words.sense_prominence import (
    apply_ratings,
    find_duplicate_text_groups,
    rate_group,
)

logger = logging.getLogger(__name__)


def run(args: argparse.Namespace) -> int:
    """Rate shared spellings. Returns the number of lemmas changed."""
    config = get_data_source_config(args)
    session = create_session(config)
    try:
        groups = find_duplicate_text_groups(
            session, limit=args.limit, only_unrated=args.only_unrated
        )
        lemma_count = sum(len(senses) for _, senses in groups)
        print(f"Found {len(groups)} shared spellings covering {lemma_count} lemmas")

        if args.list:
            for lemma_text, senses in groups:
                print(f"\n{lemma_text} ({len(senses)} senses)")
                for sense in senses:
                    print(
                        f"  [{sense.current_prominence or 'unrated':11s}] {sense.guid or '-':8s} "
                        f"({sense.pos_type}) {sense.definition_text[:60]}"
                    )
            return 0

        if not groups:
            return 0

        # Imported here so --list needs no LLM client at all.
        from wordfreq.translation.client import LinguisticClient

        client = LinguisticClient(config=config.with_model(args.model, debug=args.debug))

        total_changed = 0
        failures = 0
        for index, (lemma_text, senses) in enumerate(groups, start=1):
            ratings, error = rate_group(client.client, lemma_text, senses, model=args.model)
            if error is not None:
                failures += 1
                print(f"[{index}/{len(groups)}] {lemma_text}: FAILED ({error})")
                continue

            by_id = {sense.lemma_id: sense for sense in senses}
            print(f"[{index}/{len(groups)}] {lemma_text}")
            for rating in ratings:
                sense = by_id[rating.lemma_id]
                marker = "->" if sense.current_prominence != rating.prominence else "  "
                print(
                    f"    {marker} {sense.current_prominence or 'unrated':11s} => "
                    f"{rating.prominence:11s} {sense.definition_text[:45]}"
                )

            changed = apply_ratings(session, ratings)
            total_changed += len(changed)

            if not args.dry_run:
                session.commit()

            if args.throttle and index < len(groups):
                time.sleep(args.throttle)

        if args.dry_run:
            session.rollback()
            print(f"\nDry run: {total_changed} lemmas would change, nothing committed")
        else:
            print(f"\nUpdated {total_changed} lemmas across {len(groups)} spellings")
        if failures:
            print(f"{failures} spellings failed to rate")
        return total_changed
    finally:
        session.close()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    add_llm_args(parser)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Rate at most this many shared spellings (default: all)",
    )
    parser.add_argument(
        "--only-unrated",
        action="store_true",
        help="Skip spellings where every lemma already carries a rating",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the shared spellings and exit, making no LLM calls",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
