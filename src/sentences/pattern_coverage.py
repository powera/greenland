#!/usr/bin/env python3
"""Report which pattern sentences each language can make, and what data is
missing for the rest.

Read-only.  For each pattern: how many candidate words fill it, how many
sentences that yields across every subject, and the skip reasons (missing
gender, form, English plural, measure word) with example words.

  PYTHONPATH=src python src/sentences/pattern_coverage.py --language lt es es-419 fr zh
  PYTHONPATH=src python src/sentences/pattern_coverage.py --language fr --skips
  PYTHONPATH=src python src/sentences/pattern_coverage.py --language lt --output /tmp/lt.jsonl
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Dict, List, Optional, Set, Tuple

from agents.common.common_args import add_backend_args, get_data_source_config
from langtools.sentence_patterns import (
    PatternResult,
    patterns_for,
    render,
    supported_languages,
)
from sentences.pattern_pools import load_pools
from storage.backend import create_session


def summarize(language_code: str, result: PatternResult, show_skips: int) -> List[str]:
    sentences_by_pattern: Counter[str] = Counter(s.pattern_id for s in result.sentences)
    words_by_pattern: Dict[str, Set[str]] = defaultdict(set)
    for rendered in result.sentences:
        words_by_pattern[rendered.pattern_id].add(rendered.word_guids[0])
    skips_by_pattern: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    for skip in result.skips:
        skips_by_pattern[skip.pattern_id][skip.reason].append(skip.guid)

    lines = [f"== {language_code} =="]
    for pattern in patterns_for(language_code):
        pid = pattern.pattern_id
        reasons = skips_by_pattern.get(pid, {})
        skipped = sum(len(set(guids)) for guids in reasons.values())
        lines.append(
            f"  {pid:<10} {len(words_by_pattern[pid]):>4} words  "
            f"{sentences_by_pattern[pid]:>6} sentences  {skipped:>4} skips"
        )
        for reason, guids in sorted(reasons.items(), key=lambda item: -len(set(item[1]))):
            unique = sorted(set(guids))
            examples = ", ".join(unique[:show_skips])
            suffix = f": {examples}" if show_skips else ""
            lines.append(f"      {len(unique):>4}  {reason}{suffix}")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--language",
        nargs="+",
        default=supported_languages(),
        choices=supported_languages(),
    )
    parser.add_argument("--pattern", nargs="+", help="Only these pattern ids")
    parser.add_argument("--max-level", type=int, help="Only words at or below this level")
    parser.add_argument(
        "--skips",
        type=int,
        nargs="?",
        const=10,
        default=0,
        help="List up to N example GUIDs per skip reason (default 10)",
    )
    parser.add_argument("--output", help="Write every rendered sentence to this JSONL file")
    parser.add_argument("--debug", action="store_true")
    add_backend_args(parser)
    args = parser.parse_args(argv)

    config = get_data_source_config(args)
    session = create_session(config, readonly=True)
    output_rows: List[Tuple[str, Dict[str, object]]] = []
    try:
        for language_code in args.language:
            pools = load_pools(session, language_code, max_level=args.max_level)
            result = render(language_code, pools, args.pattern)
            print("\n".join(summarize(language_code, result, args.skips)))
            if args.output:
                output_rows += [(language_code, asdict(s)) for s in result.sentences]
    finally:
        session.close()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            for language_code, row in output_rows:
                handle.write(json.dumps({"language": language_code, **row}, ensure_ascii=False))
                handle.write("\n")
        print(f"Wrote {len(output_rows)} sentences to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
