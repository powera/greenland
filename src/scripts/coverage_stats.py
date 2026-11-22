#!/usr/bin/python3

"""Report what fraction of curated lemmas have their translations and grammar facts.

Read-only, and no LLM client is loaded.  Every number comes from a handful of
bulk column queries (one per table), so the run takes seconds and its memory
stays at a few sets of lemma ids however large the database grows.  The
agents' own reports (``voras --coverage``, ``lape2 coverage``) instead walk
the lemmas one at a time, issuing queries per lemma and language.

The rules match the fill agents, so "missing" here is what a run would ask for:

  * Translations follow voras: a lemma is translated in a language when it has
    a non-blank translation there (English falls back to ``lemma_text``), and a
    blank translation beside a -1 difficulty override is a deliberate gap,
    counted as excluded rather than missing.
  * Grammar facts follow lape2's catalog (``agents.lape2.catalog``): a fact
    applies to a lemma when its POS and language are in the fact's registry
    entry and the lemma is translated in that language; it is complete when
    its completion fact is stored (for override facts, a ``regular`` or
    ``not_applicable`` status, or ``override`` with the form beside it).
    Previously uncertain answers count as missing, which lape2 only re-asks
    with --retry-uncertain.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/scripts/coverage_stats.py
    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/scripts/coverage_stats.py \\
        --level 1-20 --languages all --section translations
    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/scripts/coverage_stats.py \\
        --pos-type noun --section grammar --grammar-languages fr de
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
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

import constants
from agents.common.common_args import parse_level_arg
from agents.lape2.catalog import CATALOG, SPECS, FactSpec
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.config.lemma_fact_registry import LEMMA_FACT_DEFINITIONS
from storage.models.grammar_fact import GrammarFact
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Lemma, LemmaDifficultyOverride, LemmaTranslation
from storage.translation_helpers import (
    LANGUAGE_FIELDS,
    TIER_1_LANGUAGES,
    TIER_2_LANGUAGES,
    TIER_3_LANGUAGES,
    TIER_4_LANGUAGES,
)
from words.translation_workflow import resolve_generation_languages

# What lape2 covers when given no --languages: every language some
# per-language fact is defined for.
DEFAULT_GRAMMAR_LANGUAGES: List[str] = sorted(
    {language for spec in SPECS if spec.kind != "concept" for language in spec.languages()}
)

# Override facts are complete on one of these statuses, or on "override"
# with the overriding form stored beside it.
OVERRIDE_DONE_STATUSES = ("regular", "not_applicable")


@dataclass
class TranslationRow:
    language: str
    tier: str
    translated: int
    excluded: int
    missing: int
    percent: float


@dataclass
class FactRow:
    fact_type: str
    language: Optional[str]
    applicable: int
    complete: int
    percent: float


@dataclass
class Report:
    lemma_count: int
    level: Optional[str]
    pos_type: Optional[str]
    translations: List[TranslationRow] = field(default_factory=list)
    fully_translated: Optional[int] = None
    facts: List[FactRow] = field(default_factory=list)
    # language ("concept" for language-independent facts) -> (lemmas with an
    # applicable fact, of which every applicable fact is complete)
    fact_readiness: Dict[str, Tuple[int, int]] = field(default_factory=dict)


def tier_of(language: str) -> str:
    """The tier name a language is served at, for the report's tier column."""
    for name, members in (
        ("1", TIER_1_LANGUAGES),
        ("2", TIER_2_LANGUAGES),
        ("3", TIER_3_LANGUAGES),
        ("4", TIER_4_LANGUAGES),
    ):
        if language in members:
            return name
    return "-"


def percent(part: int, whole: int) -> float:
    return part / whole * 100 if whole else 0.0


def curated_lemma_ids(
    min_level: Optional[int], max_level: Optional[int], pos_type: Optional[str]
) -> Select[Tuple[int]]:
    """The selection voras and lape2 work over: curated (GUID) lemmas, filtered."""
    query = select(Lemma.id).where(Lemma.guid.isnot(None))
    if min_level is not None:
        query = query.where(Lemma.difficulty_level >= min_level)
    if max_level is not None:
        query = query.where(Lemma.difficulty_level <= max_level)
    if pos_type is not None:
        query = query.where(Lemma.pos_type == pos_type)
    return query


def load_lemma_pos(session: Session, lemma_ids: Select[Tuple[int]]) -> Dict[int, str]:
    rows = session.execute(
        select(Lemma.id, Lemma.pos_type).where(Lemma.id.in_(lemma_ids.scalar_subquery()))
    )
    return {lemma_id: pos or "" for lemma_id, pos in rows}


def load_translated(
    session: Session, lemma_ids: Select[Tuple[int]], languages: Sequence[str]
) -> Dict[str, Set[int]]:
    """Language -> ids of the selected lemmas translated in it, as get_translation reads it."""
    field_to_code = {LANGUAGE_FIELDS[code][0]: code for code in languages}
    translated: Dict[str, Set[int]] = {code: set() for code in languages}
    rows = session.execute(
        select(LemmaTranslation.lemma_id, LemmaTranslation.language_code).where(
            LemmaTranslation.language_code.in_(list(field_to_code)),
            LemmaTranslation.lemma_id.in_(lemma_ids.scalar_subquery()),
            func.trim(LemmaTranslation.translation) != "",
        )
    )
    for lemma_id, field_name in rows:
        translated[field_to_code[field_name]].add(lemma_id)
    if "en" in translated:
        # get_translation reads lemma_text when a lemma has no en row at all
        # (an en row that is present but blank stays blank).
        en_field = LANGUAGE_FIELDS["en"][0]
        has_en_row = select(LemmaTranslation.lemma_id).where(
            LemmaTranslation.language_code == en_field
        )
        fallback = session.execute(
            select(Lemma.id).where(
                Lemma.id.in_(lemma_ids.scalar_subquery()),
                Lemma.id.not_in(has_en_row.scalar_subquery()),
                func.trim(Lemma.lemma_text) != "",
            )
        )
        translated["en"].update(lemma_id for (lemma_id,) in fallback)
    return translated


def load_excluded(
    session: Session, lemma_ids: Select[Tuple[int]], languages: Sequence[str]
) -> Dict[str, Set[int]]:
    """Language -> ids of the selected lemmas with a -1 (excluded) override there."""
    excluded: Dict[str, Set[int]] = {code: set() for code in languages}
    rows = session.execute(
        select(LemmaDifficultyOverride.lemma_id, LemmaDifficultyOverride.language_code).where(
            LemmaDifficultyOverride.difficulty_level == constants.EXCLUDE_DIFFICULTY_LEVEL,
            LemmaDifficultyOverride.language_code.in_(list(languages)),
            LemmaDifficultyOverride.lemma_id.in_(lemma_ids.scalar_subquery()),
        )
    )
    for lemma_id, language in rows:
        excluded[language].add(lemma_id)
    return excluded


def translation_rows(
    languages: Sequence[str],
    lemma_count: int,
    translated: Dict[str, Set[int]],
    excluded: Dict[str, Set[int]],
) -> List[TranslationRow]:
    rows = []
    for language in languages:
        done = len(translated[language])
        gaps = len(excluded[language] - translated[language])
        rows.append(
            TranslationRow(
                language=language,
                tier=tier_of(language),
                translated=done,
                excluded=gaps,
                missing=lemma_count - done - gaps,
                percent=percent(done, lemma_count - gaps),
            )
        )
    return rows


def count_fully_translated(
    lemma_ids: Set[int],
    languages: Sequence[str],
    translated: Dict[str, Set[int]],
    excluded: Dict[str, Set[int]],
) -> int:
    """Lemmas with nothing missing in any of *languages*."""
    remaining = set(lemma_ids)
    for language in languages:
        remaining &= translated[language] | excluded[language]
    return len(remaining)


def load_grammar_facts(
    session: Session,
    lemma_ids: Select[Tuple[int]],
    fact_types: Set[str],
    languages: Sequence[str],
) -> Dict[Tuple[str, str], Dict[int, str]]:
    """(fact_type, language) -> {lemma_id: value} for the non-blank stored facts."""
    stored: Dict[Tuple[str, str], Dict[int, str]] = defaultdict(dict)
    rows = session.execute(
        select(
            GrammarFact.lemma_id,
            GrammarFact.language_code,
            GrammarFact.fact_type,
            GrammarFact.fact_value,
        ).where(
            GrammarFact.fact_type.in_(sorted(fact_types)),
            GrammarFact.language_code.in_(list(languages)),
            GrammarFact.lemma_id.in_(lemma_ids.scalar_subquery()),
            func.trim(GrammarFact.fact_value) != "",
        )
    )
    for lemma_id, language, fact_type, value in rows:
        stored[(fact_type, language)][lemma_id] = value
    return stored


def load_concept_facts(
    session: Session, lemma_ids: Select[Tuple[int]], fact_types: Set[str]
) -> Dict[str, Set[int]]:
    """fact_type -> ids of the selected lemmas with a non-blank language-free fact."""
    stored: Dict[str, Set[int]] = defaultdict(set)
    rows = session.execute(
        select(LemmaFact.lemma_id, LemmaFact.fact_type).where(
            LemmaFact.fact_type.in_(sorted(fact_types)),
            LemmaFact.lemma_id.in_(lemma_ids.scalar_subquery()),
            func.trim(LemmaFact.fact_value) != "",
        )
    )
    for lemma_id, fact_type in rows:
        stored[fact_type].add(lemma_id)
    return stored


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


def fact_rows(
    session: Session,
    lemma_ids: Select[Tuple[int]],
    lemma_pos: Dict[int, str],
    specs: Sequence[FactSpec],
    languages: Sequence[str],
    translated: Dict[str, Set[int]],
) -> Tuple[List[FactRow], Dict[str, Tuple[int, int]]]:
    language_specs = [spec for spec in specs if spec.kind != "concept"]
    concept_specs = [spec for spec in specs if spec.kind == "concept"]
    stored = load_grammar_facts(
        session,
        lemma_ids,
        {spec.completion_type for spec in language_specs}
        | {spec.fact_type for spec in language_specs if spec.kind == "override"},
        languages,
    )
    concepts = load_concept_facts(session, lemma_ids, {spec.fact_type for spec in concept_specs})

    rows: List[FactRow] = []
    # language -> lemmas with an applicable fact / lemmas with one missing
    has_fact: Dict[str, Set[int]] = defaultdict(set)
    has_gap: Dict[str, Set[int]] = defaultdict(set)
    for spec in language_specs:
        for language in languages:
            if language not in spec.languages():
                continue
            applicable = {
                lemma_id
                for lemma_id in translated[language]
                if spec.applies(lemma_pos[lemma_id], language)
            }
            if not applicable:
                continue
            complete = applicable & completed_ids(spec, language, stored)
            rows.append(
                FactRow(
                    spec.fact_type,
                    language,
                    len(applicable),
                    len(complete),
                    percent(len(complete), len(applicable)),
                )
            )
            has_fact[language] |= applicable
            has_gap[language] |= applicable - complete
    for spec in concept_specs:
        required_pos = LEMMA_FACT_DEFINITIONS[spec.fact_type].required_pos
        applicable = {lemma_id for lemma_id, pos in lemma_pos.items() if pos in required_pos}
        if not applicable:
            continue
        complete = applicable & concepts[spec.fact_type]
        rows.append(
            FactRow(
                spec.fact_type,
                None,
                len(applicable),
                len(complete),
                percent(len(complete), len(applicable)),
            )
        )
        has_fact["concept"] |= applicable
        has_gap["concept"] |= applicable - complete
    readiness = {
        language: (len(ids), len(ids - has_gap[language])) for language, ids in has_fact.items()
    }
    return rows, readiness


def build_report(
    session: Session,
    *,
    level: Optional[str],
    pos_type: Optional[str],
    translation_languages: Sequence[str],
    grammar_languages: Sequence[str],
    specs: Sequence[FactSpec],
) -> Report:
    min_level, max_level = parse_level_arg(level)
    lemma_ids = curated_lemma_ids(min_level, max_level, pos_type)
    lemma_pos = load_lemma_pos(session, lemma_ids)
    report = Report(lemma_count=len(lemma_pos), level=level, pos_type=pos_type)
    all_languages = list(dict.fromkeys([*translation_languages, *grammar_languages]))
    translated = load_translated(session, lemma_ids, all_languages)
    if translation_languages:
        excluded = load_excluded(session, lemma_ids, translation_languages)
        report.translations = translation_rows(
            translation_languages, report.lemma_count, translated, excluded
        )
        report.fully_translated = count_fully_translated(
            set(lemma_pos), translation_languages, translated, excluded
        )
    if specs:
        report.facts, report.fact_readiness = fact_rows(
            session, lemma_ids, lemma_pos, specs, grammar_languages, translated
        )
    return report


def print_report(report: Report) -> None:
    scope = ", ".join(
        part
        for part in (
            f"level {report.level}" if report.level else "",
            f"pos {report.pos_type}" if report.pos_type else "",
        )
        if part
    )
    print(f"Curated lemmas: {report.lemma_count}" + (f" ({scope})" if scope else ""))

    if report.translations:
        print("\nTRANSLATIONS  (percent = translated / (lemmas - excluded))")
        print(f"  {'lang':<14}{'tier':>4}{'translated':>12}{'excluded':>10}{'missing':>9}{'%':>8}")
        for row in report.translations:
            print(
                f"  {row.language:<14}{row.tier:>4}{row.translated:>12}{row.excluded:>10}"
                f"{row.missing:>9}{row.percent:>7.1f}%"
            )
        if report.fully_translated is not None:
            print(
                f"  Nothing missing in any of these languages: {report.fully_translated}"
                f"/{report.lemma_count} ({percent(report.fully_translated, report.lemma_count):.1f}%)"
            )

    if report.facts:
        print("\nGRAMMAR FACTS  (complete / applicable; applicable needs a translation)")
        by_fact: Dict[str, List[FactRow]] = defaultdict(list)
        for fact in report.facts:
            by_fact[fact.fact_type].append(fact)
        for fact_type, rows in by_fact.items():
            complete = sum(row.complete for row in rows)
            applicable = sum(row.applicable for row in rows)
            cells = "  ".join(
                f"{row.language or 'concept'} {row.percent:.0f}% ({row.applicable - row.complete})"
                for row in rows
            )
            print(
                f"  {fact_type:<26}{percent(complete, applicable):>6.1f}%"
                f"  missing {applicable - complete:>6}   {cells}"
            )
        print("  (per language: percent complete, then missing count in brackets)")
        print("\n  Lemmas with every applicable fact complete:")
        for language, (with_facts, ready) in sorted(report.fact_readiness.items()):
            print(
                f"    {language:<10}{ready:>7}/{with_facts:<7}{percent(ready, with_facts):>6.1f}%"
            )


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Translation and grammar-fact coverage of curated lemmas (read-only, fast)"
    )
    parser.add_argument("--db-path", type=str, default=None, help="SQLite database path")
    parser.add_argument(
        "--level", type=str, default=None, help="Difficulty level, e.g. '5' or '1-20'"
    )
    parser.add_argument("--pos-type", type=str, default=None, help="e.g. noun, verb, adjective")
    parser.add_argument(
        "--section",
        choices=("all", "translations", "grammar"),
        default="all",
        help="Which report to print (default: both)",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help="Translation languages, as voras takes them: codes, 'all' (tiers 1-3) or "
        "'ancient'. Default: tiers 1-2, voras's default",
    )
    parser.add_argument(
        "--grammar-languages",
        nargs="+",
        choices=DEFAULT_GRAMMAR_LANGUAGES,
        default=None,
        help="Grammar-fact languages. Default: every language lape2 covers",
    )
    parser.add_argument(
        "--facts",
        nargs="+",
        choices=sorted(CATALOG),
        default=None,
        help="Only these lape2 facts (default: all)",
    )
    parser.add_argument("--json", type=str, default=None, help="Also write the report here")
    parser.add_argument("--debug", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = get_argument_parser()
    args = parser.parse_args(argv)
    try:
        parse_level_arg(args.level)
    except ValueError as error:
        parser.error(str(error))

    translation_languages: List[str] = []
    if args.section in ("all", "translations"):
        translation_languages = resolve_generation_languages(args.languages)
    specs: List[FactSpec] = []
    grammar_languages: List[str] = []
    if args.section in ("all", "grammar"):
        specs = [CATALOG[fact] for fact in args.facts] if args.facts else list(SPECS)
        grammar_languages = list(args.grammar_languages or DEFAULT_GRAMMAR_LANGUAGES)

    config = DataSourceConfig(sqlite_path=args.db_path, debug=args.debug)
    with contextlib.closing(create_session(config, readonly=True)) as session:
        report = build_report(
            session,
            level=args.level,
            pos_type=args.pos_type,
            translation_languages=translation_languages,
            grammar_languages=grammar_languages,
            specs=specs,
        )
    print_report(report)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(asdict(report), handle, indent=2, ensure_ascii=False)
        print(f"\nReport written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
