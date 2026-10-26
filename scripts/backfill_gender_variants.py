#!/usr/bin/env python3
"""Ask which already-translated person nouns have male/female words, per language.

New translations answer this inside voras's word prompt.  This script asks it
for the person nouns (storage.models.guid_prefixes.is_human_subtype) that were
translated before that, and again whenever a language is added: each lemma's
languages with no gender_variant_status yet, given the ordinary word in each.
English, the source language, is always included.  A storage dialect
(es-419) whose word matches its parent's (es) copies the parent's answer
instead of being asked.

The answers are stored through storage.crud.gender_variant: male/female
variant words with their grammatical gender and status "pair", or status
"none" when one word serves both.  Plurals are generated separately (vilkas).

Run without --dry-run it makes live LLM calls, or OpenAI batches with --batch:

  PYTHONPATH=src python scripts/backfill_gender_variants.py --dry-run
  PYTHONPATH=src python scripts/backfill_gender_variants.py --guid N36_047
  PYTHONPATH=src python scripts/backfill_gender_variants.py --batch
  PYTHONPATH=src python scripts/backfill_gender_variants.py --languages all --batch

--languages takes voras's selection: default tiers 1-2, "all" for tiers 1-3.
--replace asks again for languages already checked, replacing their answer.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.common.batch_run import add_batch_args, is_openai_model, run_batch_populate
from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_guid_arg,
    add_language_args,
    add_level_args,
    add_llm_args,
    get_data_source_config,
    parse_level_arg,
)
from sqlalchemy.orm import Session

from clients.unified_client import UnifiedLLMClient
from storage.backend import create_session
from storage.models.guid_prefixes import human_subtypes
from storage.models.schema import Lemma
from words.translation_workflow import resolve_generation_languages
from workqueue.handlers.words.gender_variants import GENDER_VARIANTS_JOB, gender_variant_states
from workqueue.llm_batch import run_inline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    add_common_args(parser)
    add_backend_args(parser)
    add_llm_args(parser)
    add_language_args(parser)
    add_guid_arg(parser, "Check only the person noun with this GUID")
    add_level_args(parser)
    add_batch_args(parser)
    parser.add_argument("--limit", type=int, default=None, help="At most this many lemmas")
    parser.add_argument(
        "--no-english",
        action="store_true",
        help="Leave out English, which is otherwise always included",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Ask again for languages already checked, replacing their answer",
    )
    return parser


def select_lemmas(
    session: Session, guid: Optional[str], level: Optional[str], limit: Optional[int]
) -> List[Lemma]:
    """Curated person nouns in id order, optionally within a level range ("1-10")."""
    query = (
        session.query(Lemma)
        .filter(
            Lemma.pos_type == "noun",
            Lemma.pos_subtype.in_(human_subtypes()),
            Lemma.guid.isnot(None),
        )
        .order_by(Lemma.id)
    )
    if guid:
        query = query.filter(Lemma.guid == guid)
    min_level, max_level = parse_level_arg(level)
    if min_level is not None:
        query = query.filter(Lemma.difficulty_level >= min_level)
    if max_level is not None:
        query = query.filter(Lemma.difficulty_level <= max_level)
    if limit:
        query = query.limit(limit)
    lemmas: List[Lemma] = query.all()
    return lemmas


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.batch:
        if not is_openai_model(args.model):
            parser.error(f"--batch uses the OpenAI Batch API; {args.model} is not an OpenAI model")
        if args.items_per_batch < 1:
            parser.error("--items-per-batch must be at least 1")
    languages = [] if args.no_english else ["en"]
    languages += [code for code in resolve_generation_languages(args.languages) if code != "en"]
    config = get_data_source_config(args)
    session = create_session(config)
    try:
        lemmas = select_lemmas(session, args.guid, args.level, args.limit)
        states, complete = gender_variant_states(session, lemmas, languages, args.replace)
        print(f"Languages ({len(languages)}): {', '.join(languages)}")
        print(f"Person nouns: {len(lemmas)} ({complete} with nothing to ask)")
        print(f"Requests: {len(states)}")
        if args.batch:
            run_batch_populate(
                GENDER_VARIANTS_JOB,
                states,
                args,
                session,
                "GENDER VARIANTS - BATCH BACKFILL",
                [f"languages ({len(languages)}): {', '.join(languages)}"],
            )
            return 0
        if args.dry_run or not states:
            if args.dry_run:
                print("DRY RUN - no requests sent, nothing written")
            return 0
        if not args.yes:
            response = input(f"Send {len(states)} live request(s)? [y/N]: ").strip().lower()
            if response not in ("y", "yes"):
                print("Aborted.")
                return 0
        client = UnifiedLLMClient.from_config(config)
        failed = 0
        for state in states:
            outcome = run_inline(session, GENDER_VARIANTS_JOB, [state], client, args.model)[0]
            print(f"{state['lemma_id']}: {outcome.status}: {outcome.detail}")
            if outcome.status == "failed":
                failed += 1
        return 1 if failed else 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
