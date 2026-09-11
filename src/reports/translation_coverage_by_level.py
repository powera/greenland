"""Report per-level translation coverage for each language.

Voras's ``--coverage`` mode reports one number per language over a single level
range.  Planning a translation run needs the cross-tab instead: for a candidate
level ceiling, how many words does each language still owe?  That is what picks
the language set for a batched run, since the LLM cost is
``words x language-batches`` -- a language whose gap is a 100-word tail rides
along nearly free beside one that owes 900.

Usage::

    PYTHONPATH=src python src/reports/translation_coverage_by_level.py --max-level 30
    PYTHONPATH=src python src/reports/translation_coverage_by_level.py \
        --max-level 30 --languages es-419 zh-tw pt-br bs de it --per-level
    PYTHONPATH=src python src/reports/translation_coverage_by_level.py \
        --max-level 30 --missing-for de

Only curated lemmas (those with a GUID) are counted, matching what the release
exports and what Voras selects for population.  A translation counts as present
only when its text is non-empty, so a blank placeholder row reads as missing --
the same rule ``words.translation_coverage`` applies.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend import create_session
from storage.models.schema import Lemma, LemmaTranslation
from storage.translation_helpers import LANGUAGE_FIELDS, get_language_name

# (totals by level, present-count by language then level, level of each lemma id)
CoverageData = Tuple[Dict[int, int], Dict[str, Dict[int, int]], Dict[int, int]]


def load_coverage(session: Any, min_level: int, max_level: Optional[int]) -> CoverageData:
    """Return per-level lemma totals and per-language present-counts.

    Built from two flat queries joined in memory rather than a per-lemma
    ``get_translation`` loop: the whole 65-level cross-tab is one pass over the
    lemma table and one over the non-empty translation rows.
    """
    lemma_query = (
        session.query(Lemma.id, Lemma.difficulty_level)
        .filter(Lemma.guid.isnot(None))
        .filter(Lemma.difficulty_level >= min_level)
    )
    if max_level is not None:
        lemma_query = lemma_query.filter(Lemma.difficulty_level <= max_level)

    level_of: Dict[int, int] = {}
    totals: Dict[int, int] = defaultdict(int)
    for lemma_id, level in lemma_query.all():
        level_of[lemma_id] = level
        totals[level] += 1

    present: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    translation_rows = (
        session.query(LemmaTranslation.lemma_id, LemmaTranslation.language_code)
        .filter(LemmaTranslation.translation.isnot(None))
        .filter(func.trim(LemmaTranslation.translation) != "")
        .all()
    )
    for lemma_id, lang_code in translation_rows:
        level = level_of.get(lemma_id)
        if level is not None:
            present[lang_code][level] += 1

    return dict(totals), present, level_of


def summarize(
    totals: Dict[int, int], present: Dict[str, Dict[int, int]], languages: List[str]
) -> Dict[str, Any]:
    """Return the report as plain data, ordered by how much each language owes."""
    grand_total = sum(totals.values())
    per_language = []
    for lang_code in languages:
        have = sum(present.get(lang_code, {}).values())
        per_language.append(
            {
                "language_code": lang_code,
                "language_name": get_language_name(lang_code) or lang_code,
                "have": have,
                "missing": grand_total - have,
                "coverage_percentage": (have / grand_total * 100) if grand_total else 0.0,
                "missing_by_level": {
                    str(level): totals[level] - present.get(lang_code, {}).get(level, 0)
                    for level in sorted(totals)
                },
            }
        )
    per_language.sort(key=lambda row: (row["missing"], row["language_code"]))
    return {
        "total_lemmas": grand_total,
        "totals_by_level": {str(level): totals[level] for level in sorted(totals)},
        "languages": per_language,
    }


def print_report(report: Dict[str, Any], per_level: bool) -> None:
    """Print the coverage summary, and optionally the per-level breakdown."""
    print(f"\nCurated lemmas in range: {report['total_lemmas']}\n")
    print(f"{'lang':<14} {'name':<28} {'have':>6} {'missing':>8} {'cover':>7}")
    print("-" * 68)
    for row in report["languages"]:
        print(
            f"{row['language_code']:<14} {row['language_name']:<28} "
            f"{row['have']:>6} {row['missing']:>8} {row['coverage_percentage']:>6.1f}%"
        )

    if not per_level:
        return

    codes = [row["language_code"] for row in report["languages"]]
    print("\nWords still missing each language, by level:\n")
    header = f"{'lvl':>4} {'total':>6}  " + " ".join(f"{code:>8}" for code in codes)
    print(header)
    print("-" * len(header))
    for level, level_total in report["totals_by_level"].items():
        cells = []
        for row in report["languages"]:
            missing = row["missing_by_level"][level]
            # A dot reads as "nothing owed" far faster than a column of zeros.
            cells.append(f"{missing:>8}" if missing else f"{'.':>8}")
        print(f"{level:>4} {level_total:>6}  " + " ".join(cells))


def find_missing_words(
    session: Any, level_of: Dict[int, int], lang_code: str
) -> List[Dict[str, Any]]:
    """Return the in-range lemmas that have no non-empty translation for a language."""
    translated: Set[int] = {
        lemma_id
        for (lemma_id,) in session.query(LemmaTranslation.lemma_id)
        .filter(LemmaTranslation.language_code == lang_code)
        .filter(LemmaTranslation.translation.isnot(None))
        .filter(func.trim(LemmaTranslation.translation) != "")
        .all()
    }
    missing_ids = [lemma_id for lemma_id in level_of if lemma_id not in translated]
    if not missing_ids:
        return []

    words = []
    # Chunked to stay clear of the SQLite variable limit on a wide level range.
    for start in range(0, len(missing_ids), 500):
        chunk = missing_ids[start : start + 500]
        for lemma in session.query(Lemma).filter(Lemma.id.in_(chunk)).all():
            words.append(
                {
                    "guid": lemma.guid,
                    "lemma_text": lemma.lemma_text,
                    "pos_type": lemma.pos_type,
                    "disambiguation": lemma.disambiguation,
                    "difficulty_level": lemma.difficulty_level,
                }
            )
    words.sort(key=lambda row: (row["difficulty_level"], row["lemma_text"]))
    return words


def print_missing_words(words: List[Dict[str, Any]], lang_code: str) -> None:
    """List the untranslated words for one language."""
    print(f"\n{len(words)} words missing {lang_code}:\n")
    for word in words:
        disambiguation = f" ({word['disambiguation']})" if word["disambiguation"] else ""
        label = f"{word['lemma_text']}{disambiguation}"
        print(
            f"  {word['difficulty_level']:>3}  {label:<34} {word['pos_type'] or '':<12} {word['guid']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    add_common_args(parser)
    add_backend_args(parser)
    parser.add_argument(
        "--min-level", type=int, default=1, help="Lowest level to include (inclusive, default: 1)"
    )
    parser.add_argument(
        "--max-level", type=int, default=None, help="Highest level to include (inclusive)"
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=None,
        help="Language codes to report (default: every language with any stored translation)",
    )
    parser.add_argument(
        "--per-level", action="store_true", help="Also print the per-level breakdown"
    )
    parser.add_argument(
        "--missing-for",
        type=str,
        default=None,
        help="List the words missing this language instead of the count table",
    )
    parser.add_argument("--output", type=Path, help="Also write the report as JSON here")
    args = parser.parse_args()

    config = get_data_source_config(args)
    session = create_session(config)
    try:
        totals, present, level_of = load_coverage(session, args.min_level, args.max_level)
        if not totals:
            print("No curated lemmas in that level range.")
            return

        if args.missing_for:
            words = find_missing_words(session, level_of, args.missing_for)
            print_missing_words(words, args.missing_for)
            if args.output is not None:
                args.output.write_text(
                    json.dumps(words, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            return

        languages = args.languages or [code for code in LANGUAGE_FIELDS if present.get(code)]
        report = summarize(totals, present, languages)
    finally:
        session.close()

    print_report(report, args.per_level)
    if args.output is not None:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
