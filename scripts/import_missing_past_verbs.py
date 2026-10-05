#!/usr/bin/env python3
"""Add the verbs behind high-frequency past-tense tokens the dictionary lacks.

The input is ``data/wordfreq/top5000_missing_past_verbs_20261004.tsv``: the
120 most frequent ``-ed`` tokens in the top 5000 whose verb had no lemma on
2026-10-04 ("introduced" -> "introduce", "placed" -> "place").  Its ``level``
column places each verb in one of four new stand-alone levels (415 everyday
and social actions, 455 thinking and judging, 475 making and changing, 485
speech and reporting); ``--level`` covers only rows that leave it blank.  It was built
read-only from ``word_tokens``, verb lemmas and their English derivative forms.

Two things kept these out.  Adding the past form itself ("decided") sends the
model's sense, whose English term is "decide", to the pending queue as a
divergent headword.  Adding the base form ("place") instead stops at the
existence guard when a noun of the same spelling is stored.  So each verb is
added by its base form with ``pos_type="verb"``: the model is asked for verb
senses only, and only a stored *verb* sense counts as already present.

Pending rows are not touched.  Most pending verbs listed in the TSV were queued
from some other word ("decide" from "determine"), and are left for review.

The new lemmas carry only their base form.  Run the rule-based conjugation
afterwards so "introduced" links to "introduce" (no LLM):

    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python src/agents/vilkas.py \\
        --task en-verb-conjugations --populate

The same words' common noun senses are added in a second pass, so the noun is
not forgotten once the verb exists.  ``top5000_missing_past_verbs_nouns_20261005.tsv``
lists the 17 with no stored noun (a "permit", a press "release"), each one
level above its verb's (416/456/476/486) as stand-alone levels to adjust later:

    PYTHONPATH=src python scripts/import_missing_past_verbs.py --pos-type noun \\
        --input data/wordfreq/top5000_missing_past_verbs_nouns_20261005.tsv

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import BarsukasAPIError
from api.constants import BASE_URL
from api.lemmas import add_word

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_INPUT = ROOT / "data" / "wordfreq" / "top5000_missing_past_verbs_20261004.tsv"
POS_TYPES = ("verb", "noun")


class VerbRow(NamedTuple):
    """One TSV row: the word to add and, for a verb, the past form behind it.

    The verb TSV names the word ``verb`` and carries ``past_form``/``rank``; the
    noun TSV has only ``word`` and ``level``, so those two are blank there.
    """

    past_form: str
    rank: Optional[int]
    verb: str
    pending_verb_ids: str
    level: Optional[int]


def read_rows(path: Path) -> List[VerbRow]:
    """Read the TSV, dropping repeated words (the first, most frequent, wins)."""
    rows: List[VerbRow] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle, delimiter="\t"):
            verb = (record.get("verb") or record.get("word") or "").strip()
            if not verb or verb in seen:
                continue
            seen.add(verb)
            level_text = (record.get("level") or "").strip()
            rank_text = (record.get("rank") or "").strip()
            rows.append(
                VerbRow(
                    past_form=(record.get("past_form") or "").strip(),
                    rank=int(rank_text) if rank_text else None,
                    verb=verb,
                    pending_verb_ids=record.get("pending_verb_ids", "").strip(),
                    level=int(level_text) if level_text else None,
                )
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Word TSV")
    parser.add_argument(
        "--pos-type",
        choices=POS_TYPES,
        default="verb",
        help="Part of speech to add; noun needs the noun TSV via --input",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Barsukas LLM model (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--level",
        type=int,
        help="Level for rows with no TSV level (default: the server's -1, unset)",
    )
    parser.add_argument("--limit", type=int, help="Add at most this many words")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Make the live, paid API calls. Without this flag, only print the plan.",
    )
    return parser.parse_args()


def _row_level(row: VerbRow, default_level: Optional[int]) -> Optional[int]:
    """The TSV's level for the row, else ``--level``, else None (server's -1)."""
    return row.level if row.level is not None else default_level


def print_plan(rows: List[VerbRow], default_level: Optional[int], pos_type: str) -> None:
    print(f"Barsukas: {BASE_URL}")
    print(f"POS: {pos_type}")
    print(f"Fallback level: {default_level if default_level is not None else 'unset (-1)'}")
    print(f"Words: {len(rows)}")
    for index, row in enumerate(rows, start=1):
        level = _row_level(row, default_level)
        source = f" <- {row.past_form} (rank {row.rank})" if row.past_form else ""
        pending = f"  (pending verb rows: {row.pending_verb_ids})" if row.pending_verb_ids else ""
        print(
            f"{index:3}. {row.verb:<14}{source} "
            f"level {level if level is not None else -1}{pending}"
        )


def _summarize(response: Dict[str, Any]) -> str:
    data = response.get("data") or {}
    senses = data.get("senses") or []
    pending = data.get("pending_senses") or []
    parts = [str(data.get("status"))]
    if senses:
        parts.append("created " + ", ".join(f"{s['guid']}/{s['pos_subtype']}" for s in senses))
    if pending:
        parts.append(f"queued {len(pending)}")
    return "; ".join(parts)


def execute(
    rows: List[VerbRow],
    model: str,
    level: Optional[int],
    limit: Optional[int],
    pos_type: str,
) -> int:
    """Add each word as ``pos_type``. Returns how many calls ended in ``created``."""
    if limit is not None and limit < 1:
        raise RuntimeError("--limit must be at least 1")
    counts: Dict[str, int] = {}
    attempted = 0
    for row in rows:
        if limit is not None and attempted >= limit:
            break
        response = add_word(row.verb, model, _row_level(row, level), pos_type=pos_type)
        status = str((response.get("data") or {}).get("status"))
        counts[status] = counts.get(status, 0) + 1
        # An "already_exists" answer made no LLM call, so it does not use up
        # the limit: a re-run after a partial run reaches the next new verbs.
        if status != "already_exists":
            attempted += 1
        print(f"{row.verb:<14} {_summarize(response)}", flush=True)

    print("\nSummary: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return counts.get("created", 0)


def main() -> int:
    args = parse_args()
    # The verb TSV holds 120 verbs; running it as nouns would pay for noun
    # senses of "involve" and "refer".  Only the curated noun TSV may do that.
    if args.pos_type != "verb" and args.input.resolve() == DEFAULT_INPUT.resolve():
        print("--pos-type noun needs the noun TSV via --input", file=sys.stderr)
        return 2
    rows = read_rows(args.input)
    print_plan(rows, args.level, args.pos_type)
    if not args.execute:
        print("\nNo API calls made. Re-run with --execute only after approval.")
        return 0

    print(f"\nLIVE MODE: Barsukas will use {args.model!r} for paid sense/translation calls.")
    try:
        execute(rows, args.model, args.level, args.limit, args.pos_type)
    except (BarsukasAPIError, RuntimeError, requests.exceptions.RequestException) as error:
        print(f"Import stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
