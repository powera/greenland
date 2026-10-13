#!/usr/bin/env python3
"""LLM scan of a curriculum level for words that do not belong in it.

The model sees one level's title, band and CEFR, and every word at the level
with its part of speech, sense definition and frequency rank, and names the
outliers:

* ``wrong_sense`` -- the spelling fits, but the stored sense does not
  ("bat" in a sports unit, defined as the animal).  The fix is to move the
  lemma or place the right sense, not to rewrite its definition: a lemma row
  is one sense, and its translations belong to that sense;
* ``off_topic`` -- the sense is right, but the title would not predict it;
* ``obscure`` -- on topic, but too rare or technical for the level;
* ``other`` -- anything else, explained in the reasoning.

Words are numbered in the prompt and the answer refers to them by number, so
two senses of one spelling at a level stay distinguishable.  Nothing is
written: :func:`scan_level` returns the flags, and the CLI prints them.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/quality/level_outliers.py \\
        --level 150 --dry-run
    PYTHONPATH=src python src/quality/level_outliers.py --level 150 --level 1070
    PYTHONPATH=src python src/quality/level_outliers.py --band named --output /tmp/outliers.tsv
"""

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

import constants
import util.prompt_loader
from clients.unified_client import UnifiedLLMClient
from reports.curriculum_bands import OVERRIDE_ONLY_LEVELS, UNRANKED_SENTINEL, band_of
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.crud.curriculum_level import get_curriculum_level, list_curriculum_levels
from storage.models.schema import Lemma
from wordfreq.data.cohorts import COHORT_LEVELS
from words.level_naming import level_words

logger = logging.getLogger(__name__)

ISSUE_VALUES = ("wrong_sense", "off_topic", "obscure", "other")
SEVERITY_VALUES = ("clear", "borderline")
BANDS = ("core", "named", "topic")
#: Neighbouring core levels shown as reference on each side.
NEIGHBOURS_PER_SIDE = 1

OUTLIER_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "outliers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "integer"},
                    "word": {"type": "string"},
                    "issue": {"type": "string", "enum": list(ISSUE_VALUES)},
                    "severity": {"type": "string", "enum": list(SEVERITY_VALUES)},
                    "reasoning": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["number", "word", "issue", "severity", "reasoning", "suggestion"],
            },
        },
    },
    "required": ["outliers"],
}


@dataclass(frozen=True)
class Outlier:
    """One word the model flagged, matched back to its lemma."""

    lemma_id: int
    guid: Optional[str]
    word: str
    issue: str
    severity: str
    reasoning: str
    suggestion: str


@dataclass(frozen=True)
class NeighbourLevel:
    """A core level next to the one under review, shown for reference."""

    level: int
    title: Optional[str]
    words: tuple[Lemma, ...]


@dataclass(frozen=True)
class LevelOutlierScan:
    """The flags for one level, checked against the words that were sent."""

    level: int
    title: Optional[str]
    word_count: int
    outliers: tuple[Outlier, ...]
    #: Why part of the answer was discarded; empty when it was used whole.
    problems: tuple[str, ...] = ()


# -- Pure prompt building ---------------------------------------------------


def describe_word(number: int, lemma: Lemma) -> str:
    """One numbered prompt line: text, part of speech, sense tag, definition, rank."""
    pos = lemma.pos_type
    if lemma.pos_subtype:
        pos = f"{pos}/{lemma.pos_subtype}"
    line = f"{number}. {lemma.lemma_text} ({pos})"
    if lemma.disambiguation:
        line += f" [{lemma.disambiguation}]"
    definition = (lemma.definition_text or "").strip() or "(no definition)"
    # The sentinel is stored for words with no measured rank; shown as a number,
    # it would read as "moderately rare".
    ranked = lemma.frequency_rank not in (None, UNRANKED_SENTINEL)
    rank = lemma.frequency_rank if ranked else "unranked"
    return f"{line}: {definition} | rank {rank}"


def build_context() -> str:
    """The system context: instructions, the same for every level."""
    return util.prompt_loader.get_context("quality", "level_outliers")


def word_label(lemma: Lemma) -> str:
    """A word as a neighbour list shows it: the text, with its sense tag."""
    if lemma.disambiguation:
        return f"{lemma.lemma_text} ({lemma.disambiguation})"
    return lemma.lemma_text


def format_neighbours(neighbours: Sequence[NeighbourLevel]) -> str:
    """The reference block of neighbouring levels, or "" when there are none."""
    if not neighbours:
        return ""
    lines = ["", "For reference only, the neighbouring core levels (not for review):"]
    for neighbour in neighbours:
        title = neighbour.title or "(no title yet)"
        words = ", ".join(word_label(lemma) for lemma in neighbour.words)
        lines.append(f"Level {neighbour.level} - {title}: {words}")
    return "\n".join(lines) + "\n"


def build_prompt(
    level: int,
    title: Optional[str],
    cefr: Optional[str],
    words: Sequence[Lemma],
    neighbours: Sequence[NeighbourLevel] = (),
) -> str:
    """The per-level prompt listing every word, numbered from 1."""
    template = util.prompt_loader.get_prompt("quality", "level_outliers")
    replacements = {
        "{{level}}": str(level),
        "{{title}}": title or "(no title yet)",
        "{{band}}": band_of(level),
        "{{cefr}}": cefr or "?",
        "{{word_count}}": str(len(words)),
        "{{words}}": "\n".join(
            describe_word(number, lemma) for number, lemma in enumerate(words, start=1)
        ),
        "{{neighbours}}": format_neighbours(neighbours),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def parse_outliers(
    payload: Mapping[str, Any], level: int, title: Optional[str], words: Sequence[Lemma]
) -> LevelOutlierScan:
    """Match the model's flags back to the words sent, discarding unusable ones.

    A flag is matched by its number; when the number is out of range or names
    a different word, the spelling is used instead if exactly one word at the
    level has it.  Otherwise the flag is dropped and reported in ``problems``.
    """
    problems: List[str] = []
    outliers: List[Outlier] = []
    seen: set[int] = set()

    for item in payload.get("outliers") or []:
        if not isinstance(item, dict):
            problems.append(f"flag {item!r} is not an object")
            continue
        word = str(item.get("word") or "").strip()
        lemma = match_word(item.get("number"), word, words)
        if lemma is None:
            problems.append(f"flag {item.get('number')!r} {word!r} matches no word at the level")
            continue
        if lemma.id in seen:
            continue
        seen.add(lemma.id)

        issue = str(item.get("issue") or "").strip()
        if issue not in ISSUE_VALUES:
            problems.append(f"{lemma.lemma_text}: issue {issue!r} read as 'other'")
            issue = "other"
        severity = str(item.get("severity") or "").strip()
        if severity not in SEVERITY_VALUES:
            problems.append(f"{lemma.lemma_text}: severity {severity!r} read as 'borderline'")
            severity = "borderline"

        outliers.append(
            Outlier(
                lemma_id=lemma.id,
                guid=lemma.guid,
                word=lemma.lemma_text,
                issue=issue,
                severity=severity,
                reasoning=str(item.get("reasoning") or "").strip(),
                suggestion=str(item.get("suggestion") or "").strip(),
            )
        )

    return LevelOutlierScan(
        level=level,
        title=title,
        word_count=len(words),
        outliers=tuple(outliers),
        problems=tuple(problems),
    )


def match_word(number: Any, word: str, words: Sequence[Lemma]) -> Optional[Lemma]:
    """The word a flag refers to: by number when it agrees with the spelling, else by spelling."""
    try:
        index = int(number) - 1
    except (TypeError, ValueError):
        index = -1
    if 0 <= index < len(words):
        candidate = words[index]
        if not word or candidate.lemma_text.casefold() == word.casefold():
            return candidate
    same_spelling = [lemma for lemma in words if lemma.lemma_text.casefold() == word.casefold()]
    if word and len(same_spelling) == 1:
        return same_spelling[0]
    return None


# -- Database and LLM -------------------------------------------------------


def prepare_level(session: Session, level: int) -> tuple[str, Optional[str], List[Lemma]]:
    """The prompt for ``level``, its title, and the words in prompt order."""
    row = get_curriculum_level(session, level)
    title = row.name if row is not None else None
    cefr = row.cefr if row is not None else None
    words = level_words(session, level)
    neighbours = neighbour_levels(session, level)
    return build_prompt(level, title, cefr, words, neighbours), title, words


def neighbour_levels(session: Session, level: int) -> List[NeighbourLevel]:
    """The nearest core levels with words on each side of a core ``level``.

    Only the core is taught in order, so only there is a level's neighbour
    meaningful; named and topic numbers are not a sequence.
    """
    if band_of(level) != "core":
        return []
    core = [
        number
        for number in range(constants.MIN_DIFFICULTY_LEVEL, constants.CORE_DIFFICULTY_LEVEL_MAX + 1)
        if number != level and number not in OVERRIDE_ONLY_LEVELS
    ]
    before = [number for number in reversed(core) if number < level]
    after = [number for number in core if number > level]
    neighbours: List[NeighbourLevel] = []
    for side in (before, after):
        found = 0
        for number in side:
            if found >= NEIGHBOURS_PER_SIDE:
                break
            words = level_words(session, number)
            if not words:
                continue
            row = get_curriculum_level(session, number)
            neighbours.append(NeighbourLevel(number, row.name if row else None, tuple(words)))
            found += 1
    return sorted(neighbours, key=lambda neighbour: neighbour.level)


def scan_level(session: Session, level: int, client: UnifiedLLMClient) -> LevelOutlierScan:
    """Ask the model which words at ``level`` are outliers. Writes nothing."""
    prompt, title, words = prepare_level(session, level)
    if not words:
        return LevelOutlierScan(level=level, title=title, word_count=0, outliers=())
    response = client.generate_chat(
        prompt=prompt, context=build_context(), json_schema=OUTLIER_JSON_SCHEMA
    )
    payload = response.structured_data
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        payload = {}
    return parse_outliers(payload, level, title, words)


def levels_in_band(session: Session, band: str) -> List[int]:
    """Titled levels in ``band``, in order, less the fixed sets and override-only levels.

    A cohort level holds exactly its set, so there is nothing for the model to
    judge; a stray word there is a data error checked by hand (see
    ``wordfreq.data.cohorts``).  An override-only level has no base words to
    scan.  ``--level`` can still scan either.
    """
    skipped = COHORT_LEVELS | OVERRIDE_ONLY_LEVELS
    return sorted(
        int(row.level)
        for row in list_curriculum_levels(session)
        if band_of(int(row.level)) == band and int(row.level) not in skipped
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--level", type=int, action="append", help="A level to scan (repeatable)")
    target.add_argument(
        "--band", choices=BANDS, help="Every titled level in a band, except fixed sets"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the prompts instead of calling the model"
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
    levels: List[int] = args.level or levels_in_band(session, args.band)

    if args.dry_run:
        print("=== CONTEXT ===\n" + build_context())
        for level in levels:
            print(f"\n=== PROMPT {level} ===\n" + prepare_level(session, level)[0])
        return 0

    client = UnifiedLLMClient.from_config(config)
    handle = args.output.open("w", encoding="utf-8", newline="") if args.output else sys.stdout
    writer = csv.writer(handle, delimiter="\t")
    writer.writerow(
        ["level", "title", "guid", "word", "issue", "severity", "suggestion", "reasoning"]
    )
    for level in levels:
        scan = scan_level(session, level, client)
        logger.info(
            "Level %d (%s): %d of %d word(s) flagged",
            level,
            scan.title or "untitled",
            len(scan.outliers),
            scan.word_count,
        )
        for problem in scan.problems:
            logger.warning("Level %d: %s", level, problem)
        for outlier in scan.outliers:
            writer.writerow(
                [
                    level,
                    scan.title or "",
                    outlier.guid or "",
                    outlier.word,
                    outlier.issue,
                    outlier.severity,
                    outlier.suggestion,
                    outlier.reasoning,
                ]
            )
        handle.flush()
    if args.output:
        handle.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
