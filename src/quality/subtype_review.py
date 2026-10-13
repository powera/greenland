#!/usr/bin/env python3
"""LLM review of the senses filed under a POS subtype, staged as a TSV.

The model sees one subtype of one part of speech ("noun/time_period"), the full
list of that part of speech's subtypes, and every sense filed under it with its
definition and level, and names the misfiled ones:

* ``move`` -- the sense belongs in another listed subtype ("death" filed as a
  time_period), which the answer names;
* ``wrong_pos`` -- the definition describes another part of speech;
* ``wrong_sense`` -- the definition is wrong, so the category cannot be judged.

Reviewing writes nothing: the flags go to a TSV whose ``apply`` column is
pre-filled ``yes`` on clear moves into a named subtype and left blank on
everything else -- borderline moves, moves into the ``<pos>_other`` catch-all,
and the two flag-only verdicts.  Edit the column, then ``--apply`` the file.

Applying moves each ``yes`` row through
:func:`storage.crud.lemma.handle_lemma_type_subtype_change`, which tombstones
the old GUID and issues one under the new subtype's prefix, so every applied
row renumbers a word in the next release.  A row whose lemma no longer has the
GUID or subtype the TSV recorded is skipped, not forced.  Only ``move`` rows can
be applied; the others are a to-do list for the lemma edit page.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/quality/subtype_review.py \\
        --pos noun --subtype time_period --max-level 30 --dry-run
    PYTHONPATH=src python src/quality/subtype_review.py --max-level 30 \\
        --output /tmp/subtype_review.tsv
    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python src/quality/subtype_review.py \\
        --apply /tmp/subtype_review.tsv
"""

import argparse
import csv
import datetime
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, TextIO

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

import constants
import util.prompt_loader
from clients.unified_client import UnifiedLLMClient
from quality.level_outliers import match_word
from reports.curriculum_bands import backup_database
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.crud.lemma import handle_lemma_type_subtype_change
from storage.models.guid_prefixes import SUBTYPE_DEFS, classifiable_subtypes, render_subtype_list
from storage.models.schema import Lemma
from storage.utils.guid import run_lemma_write

logger = logging.getLogger(__name__)

VERDICT_VALUES = ("move", "wrong_pos", "wrong_sense")
SEVERITY_VALUES = ("clear", "borderline")
#: The open-class POS types: the closed classes have one subtype, so nothing to review.
REVIEW_POS_TYPES = ("noun", "verb", "adjective", "adverb")
#: Senses per prompt; a large subtype is split so the model does not skim.
DEFAULT_CHUNK_SIZE = 150
#: Operation-log and tombstone source for applied rows.
APPLY_SOURCE = "subtype_review"
#: ``apply`` values read as "apply this row", compared case-insensitively.
APPLY_YES = frozenset({"yes", "y", "true", "1", "x"})

TSV_COLUMNS = (
    "apply",
    "pos_type",
    "current_subtype",
    "suggested_subtype",
    "verdict",
    "severity",
    "word",
    "disambiguation",
    "level",
    "guid",
    "lemma_id",
    "definition",
    "reasoning",
    "suggestion",
)


# -- Subtype names ----------------------------------------------------------


def catch_all(pos_type: str) -> str:
    """The stored name of ``pos_type``'s catch-all subtype, e.g. ``noun_other``."""
    return f"{pos_type}_other"


def prompt_name(pos_type: str, subtype: str) -> str:
    """A subtype as ``render_subtype_list`` shows it: the catch-all is plain "other"."""
    return "other" if subtype == catch_all(pos_type) else subtype


def stored_name(pos_type: str, name: str) -> str:
    """The stored subtype for a name the model answered with."""
    return catch_all(pos_type) if name == "other" else name


def subtype_choices(pos_type: str) -> List[str]:
    """The subtypes a sense may be moved to, as the prompt names them."""
    return [prompt_name(pos_type, subtype) for subtype in classifiable_subtypes(pos_type)]


def build_json_schema(pos_type: str) -> Dict[str, Any]:
    """The answer schema, with ``suggested_subtype`` limited to the POS's live subtypes."""
    return {
        "type": "object",
        "properties": {
            "flags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "number": {"type": "integer"},
                        "word": {"type": "string"},
                        "verdict": {"type": "string", "enum": list(VERDICT_VALUES)},
                        "suggested_subtype": {
                            "type": "string",
                            "enum": subtype_choices(pos_type) + [""],
                        },
                        "severity": {"type": "string", "enum": list(SEVERITY_VALUES)},
                        "reasoning": {"type": "string"},
                        "suggestion": {"type": "string"},
                    },
                    "required": [
                        "number",
                        "word",
                        "verdict",
                        "suggested_subtype",
                        "severity",
                        "reasoning",
                        "suggestion",
                    ],
                },
            },
        },
        "required": ["flags"],
    }


# -- Results ----------------------------------------------------------------


@dataclass(frozen=True)
class SubtypeFlag:
    """One sense the model flagged, matched back to its lemma."""

    lemma_id: int
    guid: Optional[str]
    word: str
    disambiguation: Optional[str]
    level: Optional[int]
    definition: str
    pos_type: str
    current_subtype: str
    verdict: str
    #: Stored subtype name for a move ("noun_other", not "other"); "" otherwise.
    suggested_subtype: str
    severity: str
    reasoning: str
    suggestion: str

    @property
    def default_apply(self) -> bool:
        """Whether the TSV pre-fills ``yes``: a clear move into a named subtype.

        A move into the catch-all is left for a person to opt into: "other" is
        usually the model failing to place a sense, not a placement.
        """
        return (
            self.verdict == "move"
            and self.severity == "clear"
            and bool(self.suggested_subtype)
            and self.suggested_subtype != catch_all(self.pos_type)
        )


@dataclass(frozen=True)
class SubtypeScan:
    """The flags for one subtype, checked against the senses that were sent."""

    pos_type: str
    subtype: str
    word_count: int
    flags: tuple[SubtypeFlag, ...]
    #: Why part of the answer was discarded; empty when it was used whole.
    problems: tuple[str, ...] = ()


# -- Pure prompt building ---------------------------------------------------


def describe_word(number: int, lemma: Lemma) -> str:
    """One numbered prompt line: text, sense tag, definition, level."""
    line = f"{number}. {lemma.lemma_text}"
    if lemma.disambiguation:
        line += f" [{lemma.disambiguation}]"
    definition = (lemma.definition_text or "").strip() or "(no definition)"
    level = lemma.difficulty_level if lemma.difficulty_level is not None else "none"
    return f"{line}: {definition} | level {level}"


def build_context() -> str:
    """The system context: instructions, the same for every subtype."""
    return util.prompt_loader.get_context("quality", "subtype_review")


def describe_subtype(pos_type: str, subtype: str) -> str:
    """What the subtype under review covers, as its definition says."""
    if subtype == catch_all(pos_type):
        return (
            f"Any {pos_type} that doesn't fit the other categories. Flag every sense "
            "here that a listed subtype fits."
        )
    spec = SUBTYPE_DEFS.get(pos_type, {}).get(subtype)
    if spec is None:
        return f"{subtype} (not a defined {pos_type} subtype: every sense here needs a move)"
    text = spec.description or subtype.replace("_", " ")
    if spec.examples:
        text += f" (e.g. {', '.join(spec.examples)})"
    if spec.deprecated:
        text += (
            ". This subtype is retired and is not in the list below: flag every sense "
            "here as a move to the listed subtype that fits"
        )
    return text


def build_prompt(pos_type: str, subtype: str, words: Sequence[Lemma], chunk_note: str = "") -> str:
    """The per-subtype prompt listing every sense, numbered from 1."""
    template = util.prompt_loader.get_prompt("quality", "subtype_review")
    replacements = {
        "{{pos}}": pos_type,
        "{{subtype}}": prompt_name(pos_type, subtype),
        "{{subtype_description}}": describe_subtype(pos_type, subtype),
        "{{subtype_list}}": render_subtype_list(pos_type),
        "{{word_count}}": str(len(words)),
        "{{chunk_note}}": chunk_note,
        "{{words}}": "\n".join(
            describe_word(number, lemma) for number, lemma in enumerate(words, start=1)
        ),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def parse_flags(
    payload: Mapping[str, Any], pos_type: str, subtype: str, words: Sequence[Lemma]
) -> SubtypeScan:
    """Match the model's flags back to the senses sent, discarding unusable ones.

    A flag is matched as :func:`quality.level_outliers.match_word` does it.  A
    flag with an unknown verdict is dropped; a move to a subtype that is not a
    live choice, or to the subtype the sense is already in, is kept with no
    suggestion, so it reaches the TSV but cannot be applied.
    """
    problems: List[str] = []
    flags: List[SubtypeFlag] = []
    seen: set[int] = set()
    choices = set(subtype_choices(pos_type))

    for item in payload.get("flags") or []:
        if not isinstance(item, dict):
            problems.append(f"flag {item!r} is not an object")
            continue
        word = str(item.get("word") or "").strip()
        lemma = match_word(item.get("number"), word, words)
        if lemma is None:
            problems.append(f"flag {item.get('number')!r} {word!r} matches no sense sent")
            continue
        if lemma.id in seen:
            continue
        seen.add(lemma.id)

        verdict = str(item.get("verdict") or "").strip()
        if verdict not in VERDICT_VALUES:
            problems.append(f"{lemma.lemma_text}: unknown verdict {verdict!r}, dropped")
            continue
        severity = str(item.get("severity") or "").strip()
        if severity not in SEVERITY_VALUES:
            problems.append(f"{lemma.lemma_text}: severity {severity!r} read as 'borderline'")
            severity = "borderline"

        suggested = ""
        if verdict == "move":
            answered = str(item.get("suggested_subtype") or "").strip()
            if answered not in choices:
                problems.append(f"{lemma.lemma_text}: {answered!r} is not a {pos_type} subtype")
            elif stored_name(pos_type, answered) == subtype:
                problems.append(f"{lemma.lemma_text}: suggested its current subtype {answered!r}")
            else:
                suggested = stored_name(pos_type, answered)

        flags.append(
            SubtypeFlag(
                lemma_id=lemma.id,
                guid=lemma.guid,
                word=lemma.lemma_text,
                disambiguation=lemma.disambiguation,
                level=lemma.difficulty_level,
                definition=(lemma.definition_text or "").strip(),
                pos_type=pos_type,
                current_subtype=subtype,
                verdict=verdict,
                suggested_subtype=suggested,
                severity=severity,
                reasoning=str(item.get("reasoning") or "").strip(),
                suggestion=str(item.get("suggestion") or "").strip(),
            )
        )

    return SubtypeScan(
        pos_type=pos_type,
        subtype=subtype,
        word_count=len(words),
        flags=tuple(flags),
        problems=tuple(problems),
    )


def chunk(words: Sequence[Lemma], size: int) -> List[Sequence[Lemma]]:
    """``words`` in consecutive runs of at most ``size``."""
    return [words[start : start + size] for start in range(0, len(words), size)]


def subtypes_to_review(
    pos_types: Sequence[str], subtypes: Sequence[str], include_catch_all: bool
) -> List[tuple[str, str]]:
    """The (POS, subtype) pairs to review, in table order.

    Retired subtypes are included: a sense still filed under one is a move
    waiting to happen.  The catch-all is skipped unless asked for, since
    placing those senses is its own job.  ``subtypes`` narrows the list and
    raises on a name none of ``pos_types`` has.
    """
    pairs: List[tuple[str, str]] = []
    for pos_type in pos_types:
        for subtype in SUBTYPE_DEFS.get(pos_type, {}):
            if subtypes and subtype not in subtypes:
                continue
            if subtype == catch_all(pos_type) and not include_catch_all and not subtypes:
                continue
            pairs.append((pos_type, subtype))
    unknown = set(subtypes) - {subtype for _, subtype in pairs}
    if unknown:
        raise ValueError(f"Not a subtype of {', '.join(pos_types)}: {', '.join(sorted(unknown))}")
    return pairs


# -- Database and LLM -------------------------------------------------------


def lemmas_in_subtype(
    session: Session,
    pos_type: str,
    subtype: str,
    min_level: Optional[int] = None,
    max_level: Optional[int] = None,
) -> List[Lemma]:
    """The released senses filed under one subtype, by level then spelling.

    Excluded senses (level -1) are left out.  With either level bound, so are
    senses with no level.
    """
    query = session.query(Lemma).filter(
        Lemma.pos_type == pos_type,
        Lemma.pos_subtype == subtype,
        Lemma.guid.isnot(None),
    )
    query = query.filter(
        (Lemma.difficulty_level.is_(None))
        | (Lemma.difficulty_level != constants.EXCLUDE_DIFFICULTY_LEVEL)
    )
    if min_level is not None:
        query = query.filter(Lemma.difficulty_level >= min_level)
    if max_level is not None:
        query = query.filter(Lemma.difficulty_level <= max_level)
    words = query.all()
    return sorted(
        words,
        key=lambda lemma: (
            lemma.difficulty_level is None,
            lemma.difficulty_level or 0,
            lemma.lemma_text.casefold(),
            lemma.id,
        ),
    )


def prepare_prompts(
    pos_type: str, subtype: str, words: Sequence[Lemma], chunk_size: int
) -> List[tuple[str, Sequence[Lemma]]]:
    """One (prompt, senses) pair per chunk of ``words``."""
    batches = chunk(words, chunk_size)
    prompts = []
    for index, batch in enumerate(batches, start=1):
        note = f" (part {index} of {len(batches)})" if len(batches) > 1 else ""
        prompts.append((build_prompt(pos_type, subtype, batch, note), batch))
    return prompts


def review_subtype(
    session: Session,
    pos_type: str,
    subtype: str,
    client: UnifiedLLMClient,
    min_level: Optional[int] = None,
    max_level: Optional[int] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> SubtypeScan:
    """Ask the model which senses under one subtype are misfiled. Writes nothing."""
    words = lemmas_in_subtype(session, pos_type, subtype, min_level, max_level)
    flags: List[SubtypeFlag] = []
    problems: List[str] = []
    schema = build_json_schema(pos_type)
    for prompt, batch in prepare_prompts(pos_type, subtype, words, chunk_size):
        response = client.generate_chat(prompt=prompt, context=build_context(), json_schema=schema)
        payload = response.structured_data
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            payload = {}
        scan = parse_flags(payload, pos_type, subtype, batch)
        flags.extend(scan.flags)
        problems.extend(scan.problems)
    return SubtypeScan(
        pos_type=pos_type,
        subtype=subtype,
        word_count=len(words),
        flags=tuple(flags),
        problems=tuple(problems),
    )


# -- TSV --------------------------------------------------------------------


def flag_row(flag: SubtypeFlag) -> Dict[str, str]:
    """One TSV row for a flag."""
    return {
        "apply": "yes" if flag.default_apply else "",
        "pos_type": flag.pos_type,
        "current_subtype": flag.current_subtype,
        "suggested_subtype": flag.suggested_subtype,
        "verdict": flag.verdict,
        "severity": flag.severity,
        "word": flag.word,
        "disambiguation": flag.disambiguation or "",
        "level": "" if flag.level is None else str(flag.level),
        "guid": flag.guid or "",
        "lemma_id": str(flag.lemma_id),
        "definition": flag.definition,
        "reasoning": flag.reasoning,
        "suggestion": flag.suggestion,
    }


def read_apply_rows(handle: TextIO) -> List[Dict[str, str]]:
    """The rows of a reviewed TSV whose ``apply`` column says yes."""
    reader = csv.DictReader(handle, delimiter="\t")
    return [row for row in reader if (row.get("apply") or "").strip().casefold() in APPLY_YES]


# -- Apply ------------------------------------------------------------------


@dataclass(frozen=True)
class AppliedMove:
    """One subtype change written to the database."""

    word: str
    old_guid: str
    new_guid: Optional[str]
    old_subtype: str
    new_subtype: str


@dataclass(frozen=True)
class ApplyResult:
    """What ``apply_rows`` changed, and the rows it would not apply."""

    applied: tuple[AppliedMove, ...]
    skipped: tuple[str, ...]


def row_problem(row: Mapping[str, str], lemma: Optional[Lemma]) -> Optional[str]:
    """Why a ``yes`` row cannot be applied to ``lemma``, or None if it can."""
    pos_type = row.get("pos_type", "")
    suggested = row.get("suggested_subtype", "")
    if row.get("verdict") != "move":
        return f"verdict {row.get('verdict')!r} is fixed by hand, not applied"
    if suggested not in classifiable_subtypes(pos_type):
        return f"{suggested!r} is not a live {pos_type} subtype"
    if lemma is None:
        return "no lemma with that id"
    if lemma.guid != row.get("guid"):
        return f"GUID is now {lemma.guid}"
    if lemma.pos_type != pos_type or lemma.pos_subtype != row.get("current_subtype"):
        return f"now filed as {lemma.pos_type}/{lemma.pos_subtype}"
    if suggested == lemma.pos_subtype:
        return "already in the suggested subtype"
    return None


def apply_rows(
    session: Session, rows: Sequence[Mapping[str, str]], *, commit: bool = True
) -> ApplyResult:
    """Move every applicable row's lemma to its suggested subtype, in one commit.

    Each move renumbers the lemma and tombstones its old GUID.  A row that
    fails :func:`row_problem` is skipped and reported; the rest still apply.
    ``commit=False`` runs every move and rolls them back, for a preview.
    """
    applied: List[AppliedMove] = []
    skipped: List[str] = []

    def write() -> None:
        done: set[int] = set()
        for row in rows:
            label = f"{row.get('word', '?')} ({row.get('guid') or 'no GUID'})"
            try:
                lemma_id = int(row.get("lemma_id") or "")
            except ValueError:
                skipped.append(f"{label}: no lemma_id")
                continue
            if lemma_id in done:
                skipped.append(f"{label}: listed twice")
                continue
            lemma = session.get(Lemma, lemma_id)
            problem = row_problem(row, lemma)
            if problem is not None or lemma is None:
                skipped.append(f"{label}: {problem}")
                continue
            old_guid = lemma.guid or ""
            old_subtype = lemma.pos_subtype or ""
            result = handle_lemma_type_subtype_change(
                session,
                lemma,
                lemma.pos_type,
                row["suggested_subtype"],
                source=APPLY_SOURCE,
                notes=row.get("reasoning") or None,
            )
            done.add(lemma_id)
            applied.append(
                AppliedMove(
                    word=lemma.lemma_text,
                    old_guid=old_guid,
                    new_guid=result.get("new_guid"),
                    old_subtype=old_subtype,
                    new_subtype=row["suggested_subtype"],
                )
            )

    run_lemma_write(session, write, commit=commit)
    return ApplyResult(applied=tuple(applied), skipped=tuple(skipped))


def run_apply(session: Session, db_path: Path, tsv_path: Path, dry_run: bool) -> int:
    """The ``--apply`` CLI path: back up, apply, and report."""
    with tsv_path.open(encoding="utf-8", newline="") as handle:
        rows = read_apply_rows(handle)
    if not rows:
        logger.info("No rows marked apply in %s", tsv_path)
        return 0
    if not dry_run:
        try:
            backup = backup_database(db_path, "subtype-review")
        except FileExistsError:
            backup = backup_database(db_path, f"subtype-review-{datetime.datetime.now():%H%M%S}")
        logger.info("Backed up the database to %s", backup)
    result = apply_rows(session, rows, commit=not dry_run)
    for move in result.applied:
        logger.info(
            "%s: %s -> %s (%s -> %s)",
            move.word,
            move.old_subtype,
            move.new_subtype,
            move.old_guid,
            move.new_guid,
        )
    for reason in result.skipped:
        logger.warning("Skipped %s", reason)
    verb = "Would move" if dry_run else "Moved"
    logger.info("%s %d sense(s); skipped %d", verb, len(result.applied), len(result.skipped))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--pos",
        action="append",
        choices=REVIEW_POS_TYPES,
        help="POS type to review (repeatable; default: all four open classes)",
    )
    parser.add_argument(
        "--subtype", action="append", default=[], help="Only this subtype (repeatable)"
    )
    parser.add_argument(
        "--include-catch-all",
        action="store_true",
        help="Also review the <pos>_other buckets (placing unsubtyped senses)",
    )
    parser.add_argument("--min-level", type=int, help="Only senses at this level or above")
    parser.add_argument("--max-level", type=int, help="Only senses at this level or below")
    parser.add_argument(
        "--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Senses per prompt"
    )
    parser.add_argument(
        "--apply",
        type=Path,
        metavar="TSV",
        help="Apply the rows of a reviewed TSV marked apply=yes (no LLM call)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompts instead of calling the model; with --apply, roll back",
    )
    parser.add_argument("--model", help="Model to use (default: the configured default)")
    parser.add_argument("--output", type=Path, help="TSV path (default: stdout)")
    parser.add_argument("--db-path", type=Path, default=Path(constants.WORDFREQ_DB_PATH))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=str(args.db_path),
        model=args.model or constants.DEFAULT_MODEL,
    )
    session = create_session(config)

    if args.apply:
        return run_apply(session, args.db_path, args.apply, args.dry_run)

    pos_types: List[str] = args.pos or list(REVIEW_POS_TYPES)
    try:
        pairs = subtypes_to_review(pos_types, args.subtype, args.include_catch_all)
    except ValueError as exc:
        parser.error(str(exc))

    if args.dry_run:
        print("=== CONTEXT ===\n" + build_context())
        for pos_type, subtype in pairs:
            words = lemmas_in_subtype(session, pos_type, subtype, args.min_level, args.max_level)
            for prompt, _ in prepare_prompts(pos_type, subtype, words, args.chunk_size):
                print(f"\n=== PROMPT {pos_type}/{subtype} ===\n" + prompt)
        return 0

    client = UnifiedLLMClient.from_config(config)
    handle = args.output.open("w", encoding="utf-8", newline="") if args.output else sys.stdout
    writer = csv.DictWriter(handle, fieldnames=TSV_COLUMNS, delimiter="\t")
    writer.writeheader()
    for pos_type, subtype in pairs:
        scan = review_subtype(
            session,
            pos_type,
            subtype,
            client,
            args.min_level,
            args.max_level,
            args.chunk_size,
        )
        logger.info(
            "%s/%s: %d of %d sense(s) flagged",
            pos_type,
            subtype,
            len(scan.flags),
            scan.word_count,
        )
        for problem in scan.problems:
            logger.warning("%s/%s: %s", pos_type, subtype, problem)
        for flag in scan.flags:
            writer.writerow(flag_row(flag))
        handle.flush()
    if args.output:
        handle.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
