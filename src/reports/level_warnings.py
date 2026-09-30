"""Warn about problems in the curriculum's level assignments.

This is the one level report: it is read-only, and every finding is a warning
for a human to weigh, never a move. Levels are placed by hand; nothing here
decides where a word goes. It reads ``lemmas.difficulty_level``, applies any
``LemmaDifficultyOverride`` for the chosen language, and flags:

``level_size``
    A core level outside the allowed 20-50 words, or outside the ideal 25-40.
    A fixed set's level (``wordfreq.data.cohorts``) is exempt: it holds
    exactly its set.
``duplicate_headword``
    One headword with more than one sense in the core (levels 1-30). A
    noun/adjective or noun/verb pair ("fear" the feeling and the verb) is one
    word taught in two forms and is not flagged; neither are the headwords in
    :data:`CORE_POLYSEMY_ALLOWED`.
``scatter``
    A semantic group (``pos_subtype``) whose members are spread across distant
    levels, leaving one or two stragglers far from the bulk of the group.
    Themed core levels ("In the classroom") pull words away from their
    subtype on purpose, and nothing records which words are on a level's
    theme, so expect these to include deliberate placements.
``obscure``
    A word introduced early whose corpus frequency is far worse than that of
    its level-mates, e.g. an ``economist`` sitting among ``wolf`` and ``goat``.
``sense_order``
    A polysemous headword whose first-taught sense is not its most prominent
    one, e.g. teaching ``stock`` (broth) before ``stock`` (financial). A less
    common sense that suits its level's theme may come first on purpose.

Polysemy that lacks a disambiguation is the integrity checker's job
(``agents/bebras``), not this report's.
"""

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

import constants
from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from reports.curriculum_bands import UNRANKED_SENTINEL
from storage.backend import create_session
from storage.models.schema import Lemma, LemmaDifficultyOverride
from wordfreq.data.cohorts import cohort_at

# Ranks at or above UNRANKED_SENTINEL are what the frequency rollup assigns
# when a lemma has no usable corpus evidence (mostly multiword entries). They
# carry no signal about obscurity, so the obscure check skips them rather than
# reporting every multiword phrase in the curriculum.

# Word counts for a core level: outside the allowed range is a problem, and
# outside the ideal range is worth a look.
LEVEL_SIZE_ALLOWED = (20, 50)
LEVEL_SIZE_IDEAL = (25, 40)

# Headwords with two senses that both belong in the core. Edit by hand.
#
# fish: the animal and the food are a hairy distinction, and both are basic.
# left: "left vs right" and "what's left" are both everyday meanings.
# light: light/heavy and light/dark are both basic opposites.
# second: the ordinal and the unit of time are both core.
CORE_POLYSEMY_ALLOWED: frozenset[str] = frozenset({"fish", "left", "light", "second"})

# Cross-POS pairs taught together as forms of one word.
PAIRED_POS_TYPES: frozenset[frozenset[str]] = frozenset(
    {frozenset({"noun", "adjective"}), frozenset({"noun", "verb"})}
)


@dataclass
class LemmaRow:
    """A lemma with its language-effective level resolved."""

    lemma_id: int
    guid: Optional[str]
    lemma_text: str
    disambiguation: Optional[str]
    pos_type: str
    pos_subtype: Optional[str]
    level: int
    frequency_rank: Optional[int]
    overridden: bool

    @property
    def display(self) -> str:
        """Return the headword with its sense qualifier, when it has one."""
        if self.disambiguation:
            return f"{self.lemma_text} ({self.disambiguation})"
        return self.lemma_text

    @property
    def group(self) -> str:
        """Return the wireword group label, which is the POS subtype."""
        return self.pos_subtype or "(none)"


@dataclass
class Finding:
    """One flagged ordering problem."""

    kind: str
    level: int
    word: str
    group: str
    detail: str
    frequency_rank: Optional[int] = None
    related: List[str] = field(default_factory=list)


def load_rows(session: Session, language_code: str) -> List[LemmaRow]:
    """Return every leveled lemma with *language_code* overrides applied.

    Lemmas whose effective level is -1 (excluded from this language's
    wordlist) are dropped, since they are never taught.
    """
    overrides: Dict[int, int] = {
        lemma_id: difficulty_level
        for lemma_id, difficulty_level in session.query(
            LemmaDifficultyOverride.lemma_id, LemmaDifficultyOverride.difficulty_level
        ).filter(LemmaDifficultyOverride.language_code == language_code)
    }

    rows: List[LemmaRow] = []
    for lemma in session.query(Lemma).filter(Lemma.difficulty_level.isnot(None)):
        override = overrides.get(lemma.id)
        level = override if override is not None else lemma.difficulty_level
        if level is None or level < 0:
            continue
        rows.append(
            LemmaRow(
                lemma_id=lemma.id,
                guid=lemma.guid,
                lemma_text=lemma.lemma_text,
                disambiguation=lemma.disambiguation,
                pos_type=lemma.pos_type,
                pos_subtype=lemma.pos_subtype,
                level=level,
                frequency_rank=lemma.frequency_rank,
                overridden=override is not None,
            )
        )
    return rows


def find_scatter(
    rows: Sequence[LemmaRow], *, max_level: int, min_group: int, gap: int
) -> List[Finding]:
    """Flag groups whose early members sit far from the rest of the group.

    A group is reported when a level holds at most two of its members and the
    nearest other level holding the group is more than *gap* levels away. That
    is the "one animal at level 9, ten at levels 2, 13 and 19" shape.
    """
    by_group: Dict[Tuple[str, str], List[LemmaRow]] = defaultdict(list)
    for row in rows:
        by_group[(row.pos_type, row.group)].append(row)

    findings: List[Finding] = []
    for (pos_type, group), members in sorted(by_group.items()):
        if len(members) < min_group:
            continue
        levels: Dict[int, List[LemmaRow]] = defaultdict(list)
        for member in members:
            levels[member.level].append(member)
        if len(levels) < 2:
            continue

        for level in sorted(levels):
            if level > max_level:
                continue
            stragglers = levels[level]
            if len(stragglers) > 2:
                continue
            others = [other for other in levels if other != level]
            distance = min(abs(other - level) for other in others)
            if distance <= gap:
                continue
            bulk = sorted(
                ((lvl, len(items)) for lvl, items in levels.items() if lvl != level),
                key=lambda pair: -pair[1],
            )[:4]
            findings.append(
                Finding(
                    kind="scatter",
                    level=level,
                    word=", ".join(sorted(item.display for item in stragglers)),
                    group=f"{pos_type}/{group}",
                    detail=(
                        f"{len(stragglers)} of {len(members)} {group} items at level "
                        f"{level}; nearest other {group} level is {distance} away. "
                        f"Rest of group: " + ", ".join(f"L{lvl}x{count}" for lvl, count in bulk)
                    ),
                    related=[f"L{lvl}x{count}" for lvl, count in bulk],
                )
            )
    return findings


def find_obscure(
    rows: Sequence[LemmaRow], *, max_level: int, rank_multiple: float
) -> List[Finding]:
    """Flag early words far rarer than the median word at their level.

    Comparing against the level's own median keeps the check honest across a
    curriculum whose later levels are legitimately rarer throughout.
    """
    by_level: Dict[int, List[LemmaRow]] = defaultdict(list)
    for row in rows:
        if row.level <= max_level:
            by_level[row.level].append(row)

    findings: List[Finding] = []
    for level in sorted(by_level):
        ranked: List[Tuple[LemmaRow, int]] = [
            (row, row.frequency_rank)
            for row in by_level[level]
            if row.frequency_rank is not None and row.frequency_rank < UNRANKED_SENTINEL
        ]
        if len(ranked) < 5:
            continue
        median = statistics.median(rank for _, rank in ranked)
        threshold = median * rank_multiple
        for row, rank in sorted(ranked, key=lambda pair: -pair[1]):
            if rank < threshold:
                continue
            findings.append(
                Finding(
                    kind="obscure",
                    level=level,
                    word=row.display,
                    group=f"{row.pos_type}/{row.group}",
                    detail=(
                        f"rank {rank} vs level-{level} median {int(median)} "
                        f"({rank / median:.1f}x rarer)"
                    ),
                    frequency_rank=rank,
                )
            )
    return findings


def find_sense_order(rows: Sequence[LemmaRow], *, max_level: int) -> List[Finding]:
    """Flag headwords whose earliest-taught sense is not the primary one.

    Senses of one headword share a frequency rank, so rank cannot rank them.
    The heuristic instead flags a headword whose first sense arrives well
    before its siblings: an early, narrow sense (``stock`` the broth) taught
    ahead of the everyday one reads as a mis-ordering worth a human look.
    """
    by_headword: Dict[Tuple[str, str], List[LemmaRow]] = defaultdict(list)
    for row in rows:
        if row.disambiguation:
            by_headword[(row.lemma_text, row.pos_type)].append(row)

    findings: List[Finding] = []
    for (lemma_text, pos_type), senses in sorted(by_headword.items()):
        if len(senses) < 2:
            continue
        ordered = sorted(senses, key=lambda item: item.level)
        first = ordered[0]
        if first.level > max_level:
            continue
        rest = ordered[1:]
        gap = min(item.level - first.level for item in rest)
        if gap < 1:
            continue
        findings.append(
            Finding(
                kind="sense_order",
                level=first.level,
                word=first.display,
                group=f"{pos_type}/{first.group}",
                detail=(
                    f"first sense '{first.disambiguation}' at L{first.level}; "
                    f"other senses: "
                    + ", ".join(f"{item.disambiguation}@L{item.level}" for item in rest)
                ),
                frequency_rank=first.frequency_rank,
                related=[f"{item.disambiguation}@L{item.level}" for item in rest],
            )
        )
    return findings


def _is_core(level: int) -> bool:
    return constants.MIN_DIFFICULTY_LEVEL <= level <= constants.CORE_DIFFICULTY_LEVEL_MAX


def find_level_sizes(rows: Sequence[LemmaRow], *, max_level: int) -> List[Finding]:
    """Flag core levels outside :data:`LEVEL_SIZE_ALLOWED` or :data:`LEVEL_SIZE_IDEAL`."""
    sizes: Dict[int, int] = defaultdict(int)
    for row in rows:
        if _is_core(row.level) and row.level <= max_level:
            sizes[row.level] += 1

    allowed_min, allowed_max = LEVEL_SIZE_ALLOWED
    ideal_min, ideal_max = LEVEL_SIZE_IDEAL
    findings: List[Finding] = []
    for level, size in sorted(sizes.items()):
        if cohort_at(level) is not None:
            continue
        if not allowed_min <= size <= allowed_max:
            detail = f"{size} words, outside the allowed {allowed_min}-{allowed_max}"
        elif not ideal_min <= size <= ideal_max:
            detail = f"{size} words, outside the ideal {ideal_min}-{ideal_max}"
        else:
            continue
        findings.append(
            Finding(kind="level_size", level=level, word=f"level {level}", group="*", detail=detail)
        )
    return findings


def _is_paired_form(senses: Sequence[LemmaRow]) -> bool:
    """True when every two senses are a noun/adjective or noun/verb pairing."""
    return all(
        frozenset({first.pos_type, second.pos_type}) in PAIRED_POS_TYPES
        for index, first in enumerate(senses)
        for second in senses[index + 1 :]
    )


def find_duplicate_headwords(rows: Sequence[LemmaRow]) -> List[Finding]:
    """Flag headwords taught in more than one sense within the core.

    The core teaches a headword in one sense; its other senses belong to the
    named band. Family terms are checked like any other word, so "child" the
    young person and "child" the offspring both being core is reported.
    """
    by_headword: Dict[str, List[LemmaRow]] = defaultdict(list)
    for row in rows:
        if _is_core(row.level):
            by_headword[row.lemma_text.casefold()].append(row)

    findings: List[Finding] = []
    for headword, senses in sorted(by_headword.items()):
        if len(senses) < 2 or headword in CORE_POLYSEMY_ALLOWED or _is_paired_form(senses):
            continue
        ordered = sorted(senses, key=lambda item: (item.level, item.guid or ""))
        described = [
            f"{item.display} [{item.pos_type}/{item.group}]@L{item.level}" for item in ordered
        ]
        findings.append(
            Finding(
                kind="duplicate_headword",
                level=ordered[0].level,
                word=senses[0].lemma_text,
                group="/".join(sorted({item.pos_type for item in senses})),
                detail=f"{len(senses)} core senses: " + "; ".join(described),
                related=[item.guid or "" for item in ordered],
            )
        )
    return findings


def build_report(
    session: Session,
    *,
    language_code: str,
    max_level: int,
    min_group: int,
    gap: int,
    rank_multiple: float,
) -> Dict[str, Any]:
    """Run every check and return the assembled report structure."""
    rows = load_rows(session, language_code)
    findings: List[Finding] = []
    findings.extend(find_level_sizes(rows, max_level=max_level))
    findings.extend(find_duplicate_headwords(rows))
    findings.extend(find_scatter(rows, max_level=max_level, min_group=min_group, gap=gap))
    findings.extend(find_obscure(rows, max_level=max_level, rank_multiple=rank_multiple))
    findings.extend(find_sense_order(rows, max_level=max_level))

    counts: Dict[str, int] = defaultdict(int)
    for finding in findings:
        counts[finding.kind] += 1

    return {
        "language_code": language_code,
        "max_level": max_level,
        "lemmas_considered": len(rows),
        "overrides_applied": sum(1 for row in rows if row.overridden),
        "counts": dict(sorted(counts.items())),
        "findings": [asdict(finding) for finding in findings],
    }


def print_report(report: Dict[str, Any]) -> None:
    """Print the report grouped by problem kind."""
    print(f"Level warnings - language '{report['language_code']}'")
    print(
        f"  {report['lemmas_considered']} leveled lemmas, "
        f"{report['overrides_applied']} with a language override, "
        f"checking levels 1-{report['max_level']}"
    )
    for kind, count in report["counts"].items():
        print(f"  {kind}: {count}")

    by_kind: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for finding in report["findings"]:
        by_kind[finding["kind"]].append(finding)

    for kind in ("level_size", "duplicate_headword", "scatter", "sense_order", "obscure"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        print(f"\n=== {kind} ({len(items)}) ===")
        for finding in sorted(items, key=lambda item: (item["level"], item["word"])):
            print(f"  L{finding['level']:>3}  {finding['word']}  [{finding['group']}]")
            print(f"        {finding['detail']}")


def main() -> None:
    """Run the level warnings from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument(
        "--language",
        default="en",
        help="Language code whose difficulty overrides are applied (default: en)",
    )
    parser.add_argument(
        "--max-level",
        type=int,
        default=constants.CORE_DIFFICULTY_LEVEL_MAX,
        help="Highest level to audit (default: the end of the core)",
    )
    parser.add_argument(
        "--min-group",
        type=int,
        default=6,
        help="Smallest group size the scatter check considers (default: 6)",
    )
    parser.add_argument(
        "--gap",
        type=int,
        default=8,
        help="Level distance beyond which a straggler is scattered (default: 8)",
    )
    parser.add_argument(
        "--rank-multiple",
        type=float,
        default=4.0,
        help="Flag words this many times rarer than their level median (default: 4.0)",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        report = build_report(
            session,
            language_code=args.language,
            max_level=args.max_level,
            min_group=args.min_group,
            gap=args.gap,
            rank_multiple=args.rank_multiple,
        )
    finally:
        session.close()

    print_report(report)
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
