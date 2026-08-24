"""Report the lexical stratum ("term age") of curated lemmas.

Distinguishes ancient basic vocabulary (leg, water, ship, salt) from modern
coinages (computer, bicycle, tomato), using the classical-language consensus,
Japanese orthography and the semantic-domain prior. See
:mod:`words.term_age` for the signals and their known limits.

    PYTHONPATH=src python src/reports/term_age.py
    PYTHONPATH=src python src/reports/term_age.py --level 3-8 --output /tmp/age.json

The score is derived on demand and nothing is written back: this report is
advisory. In particular it never edits ``difficulty_level``, which is curated
by hand - the ``levels`` section is there to surface disagreements for a human
to act on.
"""

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session, selectinload

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend import create_session
from storage.models.schema import Lemma
from words.term_age import (
    LexicalStratum,
    TermAgeResult,
    score_term_age_for_lemma,
)

logger = logging.getLogger(__name__)

#: Stratum order for stable, meaningful output (ancient -> modern -> unknown).
STRATUM_ORDER: Tuple[LexicalStratum, ...] = (
    LexicalStratum.ANCIENT_CORE,
    LexicalStratum.TRADITIONAL,
    LexicalStratum.EARLY_MODERN,
    LexicalStratum.MODERN,
    LexicalStratum.UNKNOWN,
)


def parse_level_range(raw: str) -> Tuple[int, int]:
    """Parse ``"5"`` or ``"3-8"`` into an inclusive ``(low, high)`` range."""
    if "-" in raw:
        low_text, high_text = raw.split("-", 1)
        low, high = int(low_text), int(high_text)
    else:
        low = high = int(raw)
    if low > high:
        raise ValueError(f"invalid level range: {raw}")
    return low, high


def collect_results(
    session: Session,
    *,
    level_range: Optional[Tuple[int, int]] = None,
    pos_type: Optional[str] = None,
) -> List[Tuple[Lemma, TermAgeResult]]:
    """Score the selected lemmas, eager-loading translations to avoid N+1."""
    query = session.query(Lemma).options(selectinload(Lemma.translations))
    if level_range is not None:
        low, high = level_range
        query = query.filter(Lemma.difficulty_level.between(low, high))
    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)
    lemmas = query.order_by(Lemma.guid).all()
    return [(lemma, score_term_age_for_lemma(lemma)) for lemma in lemmas]


def summarize(scored: Sequence[Tuple[Lemma, TermAgeResult]]) -> Dict[str, Any]:
    """Build the report payload from scored lemmas."""
    strata = Counter(result.stratum.value for _lemma, result in scored)

    # Coverage: how much real evidence is behind these numbers.
    with_ancient = sum(1 for _l, result in scored if result.ancient_evidence_count)
    with_japanese = sum(1 for _l, result in scored if result.japanese_script is not None)
    suppressed = sum(
        1
        for _l, result in scored
        if any("katakana_suppressed_named_entity" in reason for reason in result.reasons)
    )
    hedged = sum(1 for _l, result in scored if "hedged_low_confidence" in result.reasons)

    # Stratum x difficulty level: the actionable cross-tab.
    cross_tab: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for lemma, result in scored:
        if lemma.difficulty_level is not None:
            cross_tab[result.stratum.value][lemma.difficulty_level] += 1

    # Highest-confidence calls at each extreme, which are the ones worth reading.
    def _entry(lemma: Lemma, result: TermAgeResult) -> Dict[str, Any]:
        return {
            "guid": lemma.guid,
            "lemma_text": lemma.lemma_text,
            "pos_subtype": lemma.pos_subtype,
            "difficulty_level": lemma.difficulty_level,
            "stratum": result.stratum.value,
            "score": round(result.score, 3),
            "confidence": round(result.confidence, 3),
            "ancient_conventional": (
                f"{result.ancient_conventional_count}/{result.ancient_evidence_count}"
                if result.ancient_evidence_count
                else None
            ),
            "reasons": list(result.reasons),
        }

    corroborated = [(lemma, result) for lemma, result in scored if result.ancient_evidence_count]
    by_score = sorted(corroborated, key=lambda pair: pair[1].score)

    return {
        "total_lemmas": len(scored),
        "strata": {stratum.value: strata.get(stratum.value, 0) for stratum in STRATUM_ORDER},
        "coverage": {
            "with_ancient_evidence": with_ancient,
            "with_japanese_translation": with_japanese,
            "named_entity_suppressions": suppressed,
            "hedged_low_confidence": hedged,
        },
        "stratum_by_difficulty_level": {
            stratum: dict(sorted(levels.items())) for stratum, levels in cross_tab.items()
        },
        "most_ancient": [_entry(lemma, result) for lemma, result in by_score[:15]],
        "most_modern": [_entry(lemma, result) for lemma, result in by_score[-15:]],
    }


def print_report(summary: Dict[str, Any]) -> None:
    """Print the summary in a readable form."""
    print("\nTerm age (lexical stratum)")
    print("==========================")
    print(f"  lemmas scored: {summary['total_lemmas']}")

    print("\n  Strata:")
    for stratum, count in summary["strata"].items():
        print(f"    {stratum:14s} {count}")

    coverage = summary["coverage"]
    print("\n  Coverage:")
    print(f"    with classical evidence: {coverage['with_ancient_evidence']}")
    print(f"    with Japanese form:      {coverage['with_japanese_translation']}")
    print(f"    named-entity suppressed: {coverage['named_entity_suppressions']}")
    print(f"    hedged (low confidence): {coverage['hedged_low_confidence']}")

    if coverage["with_ancient_evidence"] == 0:
        print(
            "\n    NOTE: no classical evidence in range - scores rest on the\n"
            "    Japanese and subtype signals alone and are correspondingly weak."
        )

    cross_tab = summary["stratum_by_difficulty_level"]
    if cross_tab:
        print("\n  Stratum by difficulty level:")
        for stratum in (item.value for item in STRATUM_ORDER):
            levels = cross_tab.get(stratum)
            if not levels:
                continue
            rendered = ", ".join(f"L{level}:{count}" for level, count in levels.items())
            print(f"    {stratum:14s} {rendered}")

    for heading, key in (("Most ancient", "most_ancient"), ("Most modern", "most_modern")):
        entries = summary[key]
        if not entries:
            continue
        print(f"\n  {heading} (classical evidence only):")
        for entry in entries:
            level = entry["difficulty_level"]
            level_text = f"L{level}" if level is not None else "L-"
            print(
                f"    {entry['score']:.2f} {entry['stratum']:13s} {level_text:4s} "
                f"{entry['lemma_text']} [{entry['ancient_conventional']}]"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument("--level", help="Difficulty level or range, e.g. '5' or '3-8'")
    parser.add_argument("--pos-type", help="Restrict to one part of speech")
    parser.add_argument("--output", type=Path, help="Write the report as JSON")
    args = parser.parse_args()

    level_range = parse_level_range(args.level) if args.level else None

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        scored = collect_results(session, level_range=level_range, pos_type=args.pos_type)
        summary = summarize(scored)
    finally:
        session.close()

    print_report(summary)
    if args.output is not None:
        args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
