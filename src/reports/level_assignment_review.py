"""Audit Trakaido level assignments for pedagogical ordering problems.

The report is read-only. It reads ``lemmas.difficulty_level``, applies any
``LemmaDifficultyOverride`` for the chosen language, and flags four classes of
ordering problem that make an early curriculum hard to teach from:

``scatter``
    A semantic group (``pos_subtype``) whose members are spread across distant
    levels, leaving one or two stragglers far from the bulk of the group.
``obscure``
    A word introduced early whose corpus frequency is far worse than that of
    its level-mates, e.g. an ``economist`` sitting among ``wolf`` and ``goat``.
``sense_order``
    A polysemous headword whose first-taught sense is not its most prominent
    one, e.g. teaching ``stock`` (broth) before ``stock`` (financial).
``unusable_verb``
    A verb introduced before the vocabulary it needs an object from, and
    before the copula/auxiliary verbs required to build a sentence at all.
"""

import argparse
import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from reports.curriculum_bands import UNRANKED_SENTINEL
from storage.backend import create_session
from storage.models.schema import Lemma, LemmaDifficultyOverride

# Ranks at or above UNRANKED_SENTINEL are what the frequency rollup assigns
# when a lemma has no usable corpus evidence (mostly multiword entries). They
# carry no signal about obscurity, so the obscure check skips them rather than
# reporting every multiword phrase in the curriculum.

# Verbs that must exist before a learner can build a sentence out of the
# nouns they already know. A content verb taught far ahead of these is
# flagged: there is nothing to say with it yet.
ENABLING_VERBS = ("be", "have")

# pos_subtypes that supply the objects most physical-action verbs take.
OBJECT_SUBTYPES = ("food", "beverage", "small_movable_object")

# Early levels deliberately seed a part of speech with a handful of words and
# fill the group in much later, so a scattered group is not itself a problem.
# What is a problem is the drought afterwards: a POS introduced early and then
# absent for many consecutive levels. Levels at or below this are the seeding
# window whose scatter is intentional.
SEEDING_WINDOW = 8

# Subtypes whose vocabulary is specialist enough that it should not appear
# before the given level, regardless of how frequent the individual words are.
SUBTYPE_FLOORS = {
    "disease_condition": 30,
    "medication_remedy": 30,
}


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


def find_unusable_verbs(rows: Sequence[LemmaRow], *, max_level: int) -> List[Finding]:
    """Flag verbs taught before the words needed to use them.

    Two distinct problems are reported. A verb that arrives before ``be`` and
    ``have`` cannot be conjugated into a sentence at all; a verb that takes a
    physical object and arrives before any food, drink or handheld object has
    nothing to take as one.
    """
    enabling_levels = [
        row.level for row in rows if row.pos_type == "verb" and row.lemma_text in ENABLING_VERBS
    ]
    enabling_level = min(enabling_levels) if enabling_levels else None

    object_levels = [
        row.level for row in rows if row.pos_type == "noun" and row.group in OBJECT_SUBTYPES
    ]
    first_object_level = min(object_levels) if object_levels else None

    findings: List[Finding] = []

    verbs = [row for row in rows if row.pos_type == "verb" and row.level <= max_level]

    # The missing copula is one curriculum-wide fact, not one problem per verb:
    # report it once, naming the verbs it strands, so it does not bury the
    # per-verb object gaps below it.
    if enabling_level is not None:
        stranded = sorted(
            (row for row in verbs if row.level < enabling_level),
            key=lambda item: (item.level, item.lemma_text),
        )
        if stranded:
            findings.append(
                Finding(
                    kind="unusable_verb",
                    level=stranded[0].level,
                    word=f"{len(stranded)} verbs before '" + "'/'".join(ENABLING_VERBS) + "'",
                    group="verb/*",
                    detail=(
                        f"the enabling verbs ({', '.join(ENABLING_VERBS)}) are not "
                        f"taught until L{enabling_level}, so every verb from "
                        f"L{stranded[0].level} to L{stranded[-1].level} is introduced "
                        "before a learner can conjugate a sentence around it"
                    ),
                    related=[f"{row.display}@L{row.level}" for row in stranded],
                )
            )

    if first_object_level is not None:
        for row in sorted(verbs, key=lambda item: (item.level, item.lemma_text)):
            if row.level >= first_object_level:
                continue
            findings.append(
                Finding(
                    kind="unusable_verb",
                    level=row.level,
                    word=row.display,
                    group=f"verb/{row.group}",
                    detail=(
                        f"taught at L{row.level}, before any "
                        f"{'/'.join(OBJECT_SUBTYPES)} noun (first at "
                        f"L{first_object_level}) it could take as an object"
                    ),
                    frequency_rank=row.frequency_rank,
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
    findings.extend(find_scatter(rows, max_level=max_level, min_group=min_group, gap=gap))
    findings.extend(find_obscure(rows, max_level=max_level, rank_multiple=rank_multiple))
    findings.extend(find_sense_order(rows, max_level=max_level))
    findings.extend(find_unusable_verbs(rows, max_level=max_level))

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
    print(f"Level assignment review - language '{report['language_code']}'")
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

    for kind in ("unusable_verb", "scatter", "sense_order", "obscure"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        print(f"\n=== {kind} ({len(items)}) ===")
        for finding in sorted(items, key=lambda item: (item["level"], item["word"])):
            print(f"  L{finding['level']:>3}  {finding['word']}  [{finding['group']}]")
            print(f"        {finding['detail']}")


def main() -> None:
    """Run the level-assignment review from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument(
        "--language",
        default="es",
        help="Language code whose difficulty overrides are applied (default: es)",
    )
    parser.add_argument(
        "--max-level",
        type=int,
        default=25,
        help="Highest level to audit (default: 25)",
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
