#!/usr/bin/env python3
"""
Vanagas - External Wordlist Comparison Agent

Cross-references external authoritative wordlists (currently Cambridge YLE:
Pre A1 Starters, A1 Movers, A2 Flyers) against the Barsukas `lemmas` table and
reports coverage gaps, difficulty-level mismatches, POS mismatches, and
lemmas excluded from a language's wordlist that nonetheless appear in YLE.

"Vanagas" means "hawk" in Lithuanian - surveys the landscape from above and
spots what's missing.

No LLM calls; read-only comparison.
"""

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.common.common_args import (
    add_backend_args,
    add_common_args,
    add_output_args,
    get_data_source_config,
)
from storage.backend.factory import create_session
from storage.models.schema import Lemma

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DEFAULT_WORDLIST = "data/cambridge/yle_wordlist.json"
DEFAULT_OUTPUT_DIR = Path("data/cambridge")
DEFAULT_OUTPUT_BASENAME = "yle_comparison_report"

# YLE short POS codes → Barsukas long names.
# The "closest bucket" mappings (poss/dis/title) follow the plan in
# plans/we-will-want-jolly-token.md.
POS_MAP: Dict[str, str] = {
    "n": "noun",
    "v": "verb",
    "adj": "adjective",
    "adv": "adverb",
    "prep": "preposition",
    "conj": "conjunction",
    "det": "determiner",
    "pron": "pronoun",
    "excl": "interjection",
    "int": "interrogative",
    "poss": "pronoun",
    "dis": "interjection",
    "title": "noun",
}

# Expected difficulty bands per YLE level (inclusive). Deliberately loose:
# Trakaido front-loads common nouns at low difficulty, so tight bands produce
# mostly-noise mismatches.
LEVEL_BANDS: Dict[str, Tuple[int, int]] = {
    "starters": (1, 6),
    "movers": (7, 15),
    "flyers": (16, 30),
}

# Number of outlier lemmas to show per level per direction.
OUTLIER_COUNT = 10

# The "Names" theme entries (Alice, Ben, ...) are proper names unlikely to be
# in the lemma DB as learner vocabulary - skip rather than flag missing.
SKIP_THEMES = {"Names"}


def _candidate_surface_forms(entry: Dict[str, Any]) -> List[str]:
    """Return all surface forms we should try to match against Lemma.lemma_text.

    Handles UK/US variants and `word/word` slash forms (e.g. mouse/mice).
    """
    forms: List[str] = []
    seen: set[str] = set()

    def add(form: Optional[str]) -> None:
        if not form:
            return
        normalized = form.strip().lower()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        forms.append(normalized)

    word = entry.get("word") or ""
    # Split slash forms.
    for piece in word.split("/"):
        add(piece)

    variants = entry.get("variants") or {}
    for key in ("UK", "US"):
        variant_value = variants.get(key) if isinstance(variants, dict) else None
        if variant_value:
            for piece in str(variant_value).split("/"):
                add(piece)

    return forms


def _is_compound(word: str) -> bool:
    return " " in word.strip()


def _band_for_level(level: str) -> Tuple[int, int]:
    return LEVEL_BANDS[level]


def _effective_difficulty(lemma: Lemma, language_code: str) -> Optional[int]:
    """Return the per-language override if present, else the base difficulty."""
    for override in lemma.difficulty_overrides:
        if override.language_code == language_code:
            return int(override.difficulty_level)
    return lemma.difficulty_level


def _load_wordlist(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data: Dict[str, Any] = json.load(fh)
        return data


def _index_lemmas_by_text(session: Any) -> Dict[str, List[Lemma]]:
    """Index all English lemmas by lowercased lemma_text.

    English lemmas live on Lemma.lemma_text directly (not in LemmaTranslation).
    """
    index: Dict[str, List[Lemma]] = defaultdict(list)
    for lemma in session.query(Lemma).all():
        if not lemma.lemma_text:
            continue
        index[lemma.lemma_text.strip().lower()].append(lemma)
    return dict(index)


def _find_matches(
    entry: Dict[str, Any], lemma_index: Dict[str, List[Lemma]]
) -> Tuple[List[Lemma], List[str]]:
    """Return (matched lemmas, surface forms tried)."""
    forms = _candidate_surface_forms(entry)
    matches: List[Lemma] = []
    seen_ids: set[int] = set()
    for form in forms:
        for lemma in lemma_index.get(form, []):
            if lemma.id in seen_ids:
                continue
            seen_ids.add(lemma.id)
            matches.append(lemma)
    return matches, forms


def compare(
    wordlist: Dict[str, Any],
    lemma_index: Dict[str, List[Lemma]],
    levels: Sequence[str],
    language_code: str = "en",
) -> Dict[str, Any]:
    """Run the comparison for the given YLE levels.

    Returns a dict shaped for both text and JSON rendering.
    """
    entries: List[Dict[str, Any]] = list(wordlist.get("entries", []))
    by_level: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        entry_level = entry.get("level")
        if isinstance(entry_level, str) and entry_level in levels:
            by_level[entry_level].append(entry)

    result: Dict[str, Any] = {
        "source": wordlist.get("source"),
        "levels": {},
        "summary": {},
    }

    for level in levels:
        level_entries = by_level.get(level, [])
        band = _band_for_level(level)

        matched: List[Dict[str, Any]] = []
        missing: List[Dict[str, Any]] = []
        missing_compound: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        pos_mismatches: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        # (effective_difficulty, lemma_record) for outlier selection.
        difficulty_samples: List[Tuple[int, Dict[str, Any]]] = []

        for entry in level_entries:
            themes = entry.get("themes") or []
            if any(theme in SKIP_THEMES for theme in themes):
                skipped.append(
                    {"word": entry.get("word"), "reason": "proper_name", "themes": themes}
                )
                continue

            matches, forms_tried = _find_matches(entry, lemma_index)

            if not matches:
                record = {
                    "word": entry.get("word"),
                    "pos": entry.get("pos", []),
                    "themes": themes,
                    "forms_tried": forms_tried,
                }
                if _is_compound(entry.get("word") or ""):
                    missing_compound.append(record)
                else:
                    missing.append(record)
                continue

            # We have at least one lemma match. Inspect POS + difficulty.
            yle_pos_codes: List[str] = entry.get("pos") or []
            expected_pos_types = {POS_MAP[code] for code in yle_pos_codes if code in POS_MAP}
            db_pos_types = {lemma.pos_type for lemma in matches}

            pos_ok = (not expected_pos_types) or bool(expected_pos_types & db_pos_types)
            if not pos_ok:
                pos_mismatches.append(
                    {
                        "word": entry.get("word"),
                        "yle_pos": yle_pos_codes,
                        "expected_pos_types": sorted(expected_pos_types),
                        "db_pos_types": sorted(db_pos_types),
                        "lemma_ids": [lemma.id for lemma in matches],
                    }
                )

            # Pick the best lemma for difficulty analysis: prefer one whose
            # pos_type matches the YLE POS; otherwise take the first match.
            pos_matched_lemmas = [
                lemma for lemma in matches if lemma.pos_type in expected_pos_types
            ] or matches

            for lemma in pos_matched_lemmas:
                effective = _effective_difficulty(lemma, language_code)
                if effective is None:
                    continue
                if effective == -1:
                    excluded.append(
                        {
                            "word": entry.get("word"),
                            "lemma_id": lemma.id,
                            "lemma_text": lemma.lemma_text,
                            "pos_type": lemma.pos_type,
                            "pos_subtype": lemma.pos_subtype,
                        }
                    )
                    continue
                difficulty_samples.append(
                    (
                        effective,
                        {
                            "word": entry.get("word"),
                            "lemma_id": lemma.id,
                            "lemma_text": lemma.lemma_text,
                            "pos_type": lemma.pos_type,
                            "effective_difficulty": effective,
                        },
                    )
                )

            matched.append(
                {
                    "word": entry.get("word"),
                    "lemma_ids": [lemma.id for lemma in matches],
                }
            )

        # Outliers: highest DB difficulty in each YLE level, plus lowest
        # for movers/flyers (lowest for starters is obviously level 1 and
        # not interesting).
        sorted_desc = sorted(difficulty_samples, key=lambda item: -item[0])
        highest_outliers = [record for _, record in sorted_desc[:OUTLIER_COUNT]]
        if level == "starters":
            lowest_outliers: List[Dict[str, Any]] = []
        else:
            sorted_asc = sorted(difficulty_samples, key=lambda item: item[0])
            lowest_outliers = [record for _, record in sorted_asc[:OUTLIER_COUNT]]

        level_data = {
            "total": len(level_entries),
            "matched_count": len(matched),
            "missing": missing,
            "missing_compound": missing_compound,
            "skipped": skipped,
            "pos_mismatches": pos_mismatches,
            "excluded": excluded,
            "expected_band": list(band),
            "highest_outliers": highest_outliers,
            "lowest_outliers": lowest_outliers,
        }
        result["levels"][level] = level_data
        result["summary"][level] = {
            "total": len(level_entries),
            "matched": len(matched),
            "missing": len(missing),
            "missing_compound": len(missing_compound),
            "skipped": len(skipped),
            "pos_mismatches": len(pos_mismatches),
            "excluded": len(excluded),
        }

    return result


def render_text_report(report: Dict[str, Any]) -> str:
    """Render the comparison report as plain text."""
    lines: List[str] = []
    lines.append("=== Summary ===")
    for level, counts in report["summary"].items():
        lines.append(
            f"  {level:<9} {counts['total']:>4} YLE entries -> "
            f"{counts['matched']:>4} matched, "
            f"{counts['missing']:>3} missing, "
            f"{counts['missing_compound']:>3} missing-compound, "
            f"{counts['skipped']:>3} skipped, "
            f"{counts['pos_mismatches']:>3} pos-mismatch, "
            f"{counts['excluded']:>3} excluded-but-in-yle"
        )
    lines.append("")

    lines.append("=== Missing from DB (by level) ===")
    empty = True
    for level, data in report["levels"].items():
        missing_all: List[Dict[str, Any]] = list(data["missing"]) + list(data["missing_compound"])
        if not missing_all:
            continue
        empty = False
        missing_all.sort(key=lambda record: (record.get("word") or ""))
        for record in missing_all:
            pos_str = ",".join(record.get("pos") or []) or "?"
            themes = ", ".join(record.get("themes") or []) or "-"
            lines.append(f"  [{level}] {record['word']} ({pos_str}) -- {themes}")
    if empty:
        lines.append("  (none)")
    lines.append("")

    lines.append("=== Difficulty outliers (per YLE level) ===")
    for level, data in report["levels"].items():
        band = data["expected_band"]
        lines.append(f"  [{level}] expected band {band[0]}-{band[1]}")
        if data["highest_outliers"]:
            lines.append(f"    highest DB difficulty in {level}:")
            for record in data["highest_outliers"]:
                lines.append(
                    f"      {record['effective_difficulty']:>3}  "
                    f"'{record['lemma_text']}' ({record['pos_type']}, "
                    f"lemma id={record['lemma_id']})"
                )
        if data["lowest_outliers"]:
            lines.append(f"    lowest DB difficulty in {level}:")
            for record in data["lowest_outliers"]:
                lines.append(
                    f"      {record['effective_difficulty']:>3}  "
                    f"'{record['lemma_text']}' ({record['pos_type']}, "
                    f"lemma id={record['lemma_id']})"
                )
    lines.append("")

    lines.append("=== POS mismatches ===")
    empty = True
    for level, data in report["levels"].items():
        for record in data["pos_mismatches"]:
            empty = False
            yle = ",".join(record["yle_pos"])
            db = ",".join(record["db_pos_types"]) or "-"
            lines.append(f"  [{level}] [yle: {yle}] '{record['word']}' -- DB has {db}")
    if empty:
        lines.append("  (none)")
    lines.append("")

    lines.append("=== Excluded lemmas that appear in YLE ===")
    empty = True
    for level, data in report["levels"].items():
        for record in data["excluded"]:
            empty = False
            lines.append(
                f"  [{level}] '{record['lemma_text']}' "
                f"({record['pos_type']}, lemma id={record['lemma_id']}) -- "
                "difficulty_level=-1 override for 'en'"
            )
    if empty:
        lines.append("  (none)")
    lines.append("")

    lines.append("=== Skipped (proper names) ===")
    empty = True
    for level, data in report["levels"].items():
        for record in data["skipped"]:
            empty = False
            lines.append(f"  [{level}] {record['word']} ({record['reason']})")
    if empty:
        lines.append("  (none)")
    lines.append("")

    return "\n".join(lines)


def _parse_levels(levels_arg: Optional[str]) -> List[str]:
    if not levels_arg:
        return ["starters", "movers", "flyers"]
    requested = [part.strip().lower() for part in levels_arg.split(",") if part.strip()]
    unknown = [part for part in requested if part not in LEVEL_BANDS]
    if unknown:
        raise ValueError(f"Unknown levels: {unknown}. Choose from: {sorted(LEVEL_BANDS.keys())}")
    return requested


def get_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Cambridge YLE (Starters/Movers/Flyers) wordlists against "
            "the Barsukas lemma database."
        )
    )
    parser.add_argument(
        "--wordlist",
        type=str,
        default=DEFAULT_WORDLIST,
        help=f"Path to extracted YLE wordlist JSON (default: {DEFAULT_WORDLIST})",
    )
    parser.add_argument(
        "--levels",
        type=str,
        default=None,
        help="Comma-separated subset of levels (starters,movers,flyers). Default: all.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Language code for LemmaDifficultyOverride lookup (default: en)",
    )
    add_common_args(parser)
    add_backend_args(parser)
    add_output_args(parser)
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print report to stdout instead of writing to a file.",
    )
    return parser


def main() -> int:
    parser = get_argument_parser()
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        levels = _parse_levels(args.levels)
    except ValueError as exc:
        parser.error(str(exc))

    wordlist_path = Path(args.wordlist)
    if not wordlist_path.exists():
        parser.error(f"Wordlist file not found: {wordlist_path}")

    logger.info("Loading wordlist from %s", wordlist_path)
    wordlist = _load_wordlist(wordlist_path)

    config = get_data_source_config(args)
    logger.info("Loading lemmas via backend=%s", config.backend_type)
    session = create_session(config)
    try:
        lemma_index = _index_lemmas_by_text(session)
        logger.info("Indexed %d distinct English lemma surface forms", len(lemma_index))
        report = compare(wordlist, lemma_index, levels, language_code=args.language)
    finally:
        session.close()

    if args.format == "json":
        payload = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        payload = render_text_report(report)

    if args.stdout:
        print(payload)
    else:
        if args.output:
            output_path = Path(args.output)
        else:
            suffix = "json" if args.format == "json" else "txt"
            output_path = DEFAULT_OUTPUT_DIR / f"{DEFAULT_OUTPUT_BASENAME}.{suffix}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
        logger.info("Report written to %s", output_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
