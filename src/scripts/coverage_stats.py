#!/usr/bin/python3

"""Pipeline progress: what fraction of curated lemmas have each piece of data.

One standardized, read-only report in place of each agent's own coverage mode
(``voras --coverage``, ``lape2 coverage``, ``papuga --coverage``, ...).  No LLM
client is loaded, and every number comes from one bulk column query per table,
so the run takes seconds and its memory stays at a few sets of lemma ids.

The report is one matrix: a row per item, a column per language, and an
``all`` column for items that are not per-language.  Each cell is the percent
done among the lemmas the item applies to (``--counts`` shows the number still
missing instead).  The rules match the agents that fill each item, so
"missing" is what a run of that agent would work on:

  translations  voras: a non-blank translation (English is the lemma itself,
                so it has no translation row here).  A blank translation beside
                a -1 difficulty override is a deliberate gap: that lemma is
                left out of every row for that language.
  definitions   the English definition, and a disambiguation for each sense
                whose spelling and POS another curated sense shares.
                (Per-language definitions are not reported: nothing fills
                them.)
  grammar       lape2's catalog (agents.lape2.catalog): a fact applies when its
                POS and language are in its registry entry and the lemma is
                translated there; it is done when its completion fact is stored
                (for override facts, a regular/not_applicable status, or
                "override" with the form beside it).  Previously uncertain
                answers count as missing.
  ipa           papuga: the base form (or the translation row) has both IPA
                and simplified phonetic pronunciation.
  audio         served audio: a lemma audio file with a staging or prod URL
                that is not needs_replacement (pending_review is served);
                "audio approved" is the reviewed subset.

Per-language items apply only to lemmas translated in that language.  The
grammar section ends with "every applicable fact": the lemmas with nothing
left for lape2 to ask in that column.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/scripts/coverage_stats.py
    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/scripts/coverage_stats.py \\
        --level 1-20 --sections translations audio --counts
"""

import sys
from pathlib import Path

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import contextlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import ColumnElement, Select, func, not_, or_, select
from sqlalchemy.orm import QueryableAttribute, Session

import constants
from agents.common.common_args import parse_level_arg
from agents.lape2.catalog import SPECS, FactSpec
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.config.lemma_fact_registry import LEMMA_FACT_DEFINITIONS
from storage.crud.derivative_form import needs_pronunciation_update_filter
from storage.models.grammar_fact import GrammarFact
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import (
    AudioQualityReview,
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
)
from storage.translation_helpers import LANGUAGE_FIELDS
from words.translation_workflow import (
    DEFAULT_POPULATE_LANGUAGES,
    POPULATE_LANGUAGE_GROUPS,
    all_populate_languages,
)

SECTIONS = ("translations", "definitions", "grammar", "ipa", "audio")

# The column for items that are not per-language.
ALL = "all"

# Override facts are complete on one of these statuses, or on "override"
# with the overriding form stored beside it.
OVERRIDE_DONE_STATUSES = ("regular", "not_applicable")

APPROVED_AUDIO_STATUSES = ("approved", "approved_with_issues")
REJECTED_AUDIO_STATUS = "needs_replacement"


@dataclass
class Cell:
    applicable: int
    done: int

    @property
    def missing(self) -> int:
        return self.applicable - self.done

    @property
    def percent(self) -> float:
        return self.done / self.applicable * 100 if self.applicable else 0.0


@dataclass
class Row:
    section: str
    item: str
    # language code (or ALL) -> cell; a language the item does not apply to
    # has no cell.
    cells: Dict[str, Cell] = field(default_factory=dict)


@dataclass
class Report:
    lemma_count: int
    level: Optional[str]
    pos_type: Optional[str]
    languages: List[str]
    rows: List[Row] = field(default_factory=list)


@dataclass
class Selection:
    """The curated lemmas in scope, and what every section shares about them."""

    lemma_ids: Select[Tuple[int]]
    pos: Dict[int, str]
    # language -> lemmas with a word there; "en" is every lemma
    translated: Dict[str, Set[int]]
    # language -> lemmas deliberately left without a word there (-1, blank)
    excluded: Dict[str, Set[int]]


class Tally:
    """Collects rows and, per column, which lemmas still have a gap in the section."""

    def __init__(self) -> None:
        self.rows: List[Row] = []
        self.applicable: Dict[str, Set[int]] = defaultdict(set)
        self.gaps: Dict[str, Set[int]] = defaultdict(set)

    def add(self, section: str, item: str, cells: Dict[str, Tuple[Set[int], Set[int]]]) -> None:
        """Record a row from language -> (applicable ids, done ids)."""
        row = Row(section, item)
        for language, (applicable, done) in cells.items():
            if not applicable:
                continue
            complete = applicable & done
            row.cells[language] = Cell(len(applicable), len(complete))
            self.applicable[language] |= applicable
            self.gaps[language] |= applicable - complete
        if row.cells:
            self.rows.append(row)

    def reset(self) -> None:
        """Start the next summary from here."""
        self.applicable.clear()
        self.gaps.clear()

    def summarize(self, section: str, item: str) -> None:
        """Add a row of lemmas with every item recorded since the last reset done."""
        row = Row(section, item)
        for language, ids in self.applicable.items():
            row.cells[language] = Cell(len(ids), len(ids - self.gaps[language]))
        self.rows.append(row)
        self.reset()


def resolve_languages(requested: Optional[Sequence[str]]) -> List[str]:
    """English plus voras's languages: tiers 1-2 by default, 'all' for 1-3, or groups."""
    codes: List[str] = []
    for code in requested or ["en", *DEFAULT_POPULATE_LANGUAGES]:
        lowered = code.strip().lower()
        if lowered == "all":
            codes.extend(["en", *all_populate_languages()])
        else:
            codes.extend(POPULATE_LANGUAGE_GROUPS.get(lowered, [lowered]))
    unknown = sorted(set(codes) - set(LANGUAGE_FIELDS))
    if unknown:
        raise ValueError(f"Unknown language codes: {', '.join(unknown)}")
    return list(dict.fromkeys(codes))


def nonblank(column: QueryableAttribute[Any]) -> ColumnElement[bool]:
    return func.trim(column) != ""


def curated_lemma_ids(
    min_level: Optional[int], max_level: Optional[int], pos_type: Optional[str]
) -> Select[Tuple[int]]:
    """The selection the agents work over: curated (GUID) lemmas, filtered."""
    query = select(Lemma.id).where(Lemma.guid.isnot(None))
    if min_level is not None:
        query = query.where(Lemma.difficulty_level >= min_level)
    if max_level is not None:
        query = query.where(Lemma.difficulty_level <= max_level)
    if pos_type is not None:
        query = query.where(Lemma.pos_type == pos_type)
    return query


def in_selection(
    column: QueryableAttribute[Any], lemma_ids: Select[Tuple[int]]
) -> ColumnElement[bool]:
    return column.in_(lemma_ids.scalar_subquery())


def load_selection(
    session: Session, lemma_ids: Select[Tuple[int]], languages: Sequence[str]
) -> Selection:
    pos = {
        lemma_id: pos_type or ""
        for lemma_id, pos_type in session.execute(
            select(Lemma.id, Lemma.pos_type).where(in_selection(Lemma.id, lemma_ids))
        )
    }
    field_to_code = {LANGUAGE_FIELDS[code][0]: code for code in languages if code != "en"}
    translated: Dict[str, Set[int]] = {code: set() for code in languages}
    if "en" in translated:
        translated["en"] = set(pos)
    for lemma_id, field_name in session.execute(
        select(LemmaTranslation.lemma_id, LemmaTranslation.language_code).where(
            LemmaTranslation.language_code.in_(list(field_to_code)),
            in_selection(LemmaTranslation.lemma_id, lemma_ids),
            nonblank(LemmaTranslation.translation),
        )
    ):
        translated[field_to_code[field_name]].add(lemma_id)
    excluded: Dict[str, Set[int]] = {code: set() for code in languages}
    for lemma_id, language in session.execute(
        select(LemmaDifficultyOverride.lemma_id, LemmaDifficultyOverride.language_code).where(
            LemmaDifficultyOverride.difficulty_level == constants.EXCLUDE_DIFFICULTY_LEVEL,
            LemmaDifficultyOverride.language_code.in_(list(languages)),
            in_selection(LemmaDifficultyOverride.lemma_id, lemma_ids),
        )
    ):
        if lemma_id not in translated[language]:
            excluded[language].add(lemma_id)
    return Selection(lemma_ids, pos, translated, excluded)


def add_translations(tally: Tally, selection: Selection, languages: Sequence[str]) -> None:
    every = set(selection.pos)
    tally.add(
        "translations",
        "translation",
        {
            language: (every - selection.excluded[language], selection.translated[language])
            for language in languages
            if language != "en"
        },
    )


def add_definitions(session: Session, tally: Tally, selection: Selection) -> None:
    every = set(selection.pos)
    defined = {
        lemma_id
        for (lemma_id,) in session.execute(
            select(Lemma.id).where(
                in_selection(Lemma.id, selection.lemma_ids), nonblank(Lemma.definition_text)
            )
        )
    }
    tally.add("definitions", "definition (en)", {ALL: (every, defined)})

    # A spelling shared with a curated sense outside the filter still needs
    # telling apart, so homonyms are found over every curated lemma.
    spelling = (func.lower(Lemma.lemma_text), Lemma.pos_type)
    shared = (
        select(*spelling)
        .where(Lemma.guid.isnot(None))
        .group_by(*spelling)
        .having(func.count() > 1)
        .subquery()
    )
    homonyms: Set[int] = set()
    disambiguated: Set[int] = set()
    for lemma_id, has_disambiguation in session.execute(
        select(Lemma.id, func.coalesce(nonblank(Lemma.disambiguation), False))
        .join(
            shared,
            (func.lower(Lemma.lemma_text) == shared.c[0]) & (Lemma.pos_type == shared.c[1]),
        )
        .where(in_selection(Lemma.id, selection.lemma_ids))
    ):
        homonyms.add(lemma_id)
        if has_disambiguation:
            disambiguated.add(lemma_id)
    tally.add("definitions", "disambiguation (homonyms)", {ALL: (homonyms, disambiguated)})


def completed_ids(
    spec: FactSpec, language: str, stored: Dict[Tuple[str, str], Dict[int, str]]
) -> Set[int]:
    """Lemmas lape2 would not ask *spec* of in *language* (see planner.plan_request)."""
    completion = stored.get((spec.completion_type, language), {})
    if spec.kind != "override":
        return set(completion)
    forms = stored.get((spec.fact_type, language), {})
    return {
        lemma_id
        for lemma_id, status in completion.items()
        if status in OVERRIDE_DONE_STATUSES or (status == "override" and lemma_id in forms)
    }


def add_grammar(
    session: Session, tally: Tally, selection: Selection, languages: Sequence[str]
) -> None:
    language_specs = [spec for spec in SPECS if spec.kind != "concept"]
    concept_specs = [spec for spec in SPECS if spec.kind == "concept"]
    fact_types = {spec.completion_type for spec in language_specs} | {
        spec.fact_type for spec in language_specs if spec.kind == "override"
    }
    stored: Dict[Tuple[str, str], Dict[int, str]] = defaultdict(dict)
    for lemma_id, language, fact_type, value in session.execute(
        select(
            GrammarFact.lemma_id,
            GrammarFact.language_code,
            GrammarFact.fact_type,
            GrammarFact.fact_value,
        ).where(
            GrammarFact.fact_type.in_(sorted(fact_types)),
            GrammarFact.language_code.in_(list(languages)),
            in_selection(GrammarFact.lemma_id, selection.lemma_ids),
            nonblank(GrammarFact.fact_value),
        )
    ):
        stored[(fact_type, language)][lemma_id] = value
    tally.reset()
    for spec in language_specs:
        tally.add(
            "grammar",
            spec.fact_type,
            {
                language: (
                    {
                        lemma_id
                        for lemma_id in selection.translated[language]
                        if spec.applies(selection.pos[lemma_id], language)
                    },
                    completed_ids(spec, language, stored),
                )
                for language in languages
                if language in spec.languages()
            },
        )

    concepts: Dict[str, Set[int]] = defaultdict(set)
    for lemma_id, fact_type in session.execute(
        select(LemmaFact.lemma_id, LemmaFact.fact_type).where(
            LemmaFact.fact_type.in_(sorted(spec.fact_type for spec in concept_specs)),
            in_selection(LemmaFact.lemma_id, selection.lemma_ids),
            nonblank(LemmaFact.fact_value),
        )
    ):
        concepts[fact_type].add(lemma_id)
    for spec in concept_specs:
        required_pos = LEMMA_FACT_DEFINITIONS[spec.fact_type].required_pos
        applicable = {lemma_id for lemma_id, pos in selection.pos.items() if pos in required_pos}
        tally.add("grammar", spec.fact_type, {ALL: (applicable, concepts[spec.fact_type])})
    tally.summarize("grammar", "every applicable fact")


def add_ipa(session: Session, tally: Tally, selection: Selection, languages: Sequence[str]) -> None:
    pronounced: Dict[str, Set[int]] = defaultdict(set)
    for lemma_id, language in session.execute(
        select(DerivativeForm.lemma_id, DerivativeForm.language_code).where(
            DerivativeForm.is_base_form.is_(True),
            not_(needs_pronunciation_update_filter()),
            DerivativeForm.language_code.in_(list(languages)),
            in_selection(DerivativeForm.lemma_id, selection.lemma_ids),
        )
    ):
        pronounced[language].add(lemma_id)
    field_to_code = {LANGUAGE_FIELDS[code][0]: code for code in languages}
    for lemma_id, field_name in session.execute(
        select(LemmaTranslation.lemma_id, LemmaTranslation.language_code).where(
            LemmaTranslation.language_code.in_(list(field_to_code)),
            nonblank(LemmaTranslation.ipa_pronunciation),
            nonblank(LemmaTranslation.phonetic_pronunciation),
            in_selection(LemmaTranslation.lemma_id, selection.lemma_ids),
        )
    ):
        pronounced[field_to_code[field_name]].add(lemma_id)
    tally.add(
        "ipa",
        "ipa + phonetic",
        {
            language: (selection.translated[language], pronounced[language])
            for language in languages
        },
    )


def add_audio(
    session: Session, tally: Tally, selection: Selection, languages: Sequence[str]
) -> None:
    served: Dict[str, Set[int]] = defaultdict(set)
    approved: Dict[str, Set[int]] = defaultdict(set)
    for lemma_id, language, status in session.execute(
        select(Lemma.id, AudioQualityReview.language_code, AudioQualityReview.status)
        .join(AudioQualityReview, AudioQualityReview.guid == Lemma.guid)
        .where(
            in_selection(Lemma.id, selection.lemma_ids),
            AudioQualityReview.grammatical_form.is_(None),
            AudioQualityReview.language_code.in_(list(languages)),
            AudioQualityReview.status != REJECTED_AUDIO_STATUS,
            or_(
                AudioQualityReview.s3_staging_url.isnot(None),
                AudioQualityReview.s3_prod_url.isnot(None),
            ),
        )
    ):
        served[language].add(lemma_id)
        if status in APPROVED_AUDIO_STATUSES:
            approved[language].add(lemma_id)
    tally.add(
        "audio",
        "audio (served)",
        {language: (selection.translated[language], served[language]) for language in languages},
    )
    tally.add(
        "audio",
        "audio (approved)",
        {language: (selection.translated[language], approved[language]) for language in languages},
    )


def build_report(
    session: Session,
    *,
    level: Optional[str],
    pos_type: Optional[str],
    languages: Sequence[str],
    sections: Sequence[str],
) -> Report:
    min_level, max_level = parse_level_arg(level)
    lemma_ids = curated_lemma_ids(min_level, max_level, pos_type)
    selection = load_selection(session, lemma_ids, languages)
    tally = Tally()
    if "translations" in sections:
        add_translations(tally, selection, languages)
    if "definitions" in sections:
        add_definitions(session, tally, selection)
    if "grammar" in sections:
        add_grammar(session, tally, selection, languages)
    if "ipa" in sections:
        add_ipa(session, tally, selection, languages)
    if "audio" in sections:
        add_audio(session, tally, selection, languages)
    return Report(
        lemma_count=len(selection.pos),
        level=level,
        pos_type=pos_type,
        languages=list(languages),
        rows=tally.rows,
    )


def format_cell(cell: Optional[Cell], counts: bool) -> str:
    if cell is None:
        return f"{'·':>7}"
    return f"{cell.missing:>7}" if counts else f"{cell.percent:>6.1f}%"


def print_report(report: Report, counts: bool) -> None:
    scope = ", ".join(
        part
        for part in (
            f"level {report.level}" if report.level else "",
            f"pos {report.pos_type}" if report.pos_type else "",
        )
        if part
    )
    print(f"Curated lemmas: {report.lemma_count}" + (f" ({scope})" if scope else ""))
    print(
        "Cells: "
        + (
            "number still missing"
            if counts
            else "percent done among the lemmas the item applies to"
        )
        + "; · = does not apply"
    )
    columns = [*report.languages, ALL]
    label_width = 28
    header = f"{'':<{label_width}}" + "".join(f"{code:>7}" for code in columns) + f"{'missing':>9}"
    section = ""
    for row in report.rows:
        if row.section != section:
            section = row.section
            print(f"\n{section.upper()}")
            print(header)
        cells = "".join(format_cell(row.cells.get(code), counts) for code in columns)
        missing = sum(cell.missing for cell in row.cells.values())
        print(f"  {row.item:<{label_width - 2}}{cells}{missing:>9}")


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline progress for curated lemmas: translations, definitions, "
        "grammar facts, IPA and audio (read-only, no LLM)"
    )
    parser.add_argument("--level", type=str, default=None, help="Level, e.g. '5' or '1-20'")
    parser.add_argument("--pos-type", type=str, default=None, help="e.g. noun, verb, adjective")
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help="Language codes, 'all' (en + tiers 1-3) or 'ancient'. Default: en + tiers 1-2",
    )
    parser.add_argument(
        "--sections", nargs="+", choices=SECTIONS, default=None, help="Default: all sections"
    )
    parser.add_argument(
        "--counts", action="store_true", help="Show the number missing instead of percent"
    )
    parser.add_argument("--json", type=str, default=None, help="Also write the report here")
    parser.add_argument("--db-path", type=str, default=None, help="SQLite database override")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = get_argument_parser()
    args = parser.parse_args(argv)
    try:
        parse_level_arg(args.level)
        languages = resolve_languages(args.languages)
    except ValueError as error:
        parser.error(str(error))
    sections = [section for section in SECTIONS if section in (args.sections or SECTIONS)]

    config = DataSourceConfig(sqlite_path=args.db_path)
    with contextlib.closing(create_session(config, readonly=True)) as session:
        report = build_report(
            session,
            level=args.level,
            pos_type=args.pos_type,
            languages=languages,
            sections=sections,
        )
    print_report(report, args.counts)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(asdict(report), handle, indent=2, ensure_ascii=False)
        print(f"\nReport written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
