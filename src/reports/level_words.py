"""Write the words at each curriculum level as one diffable text file.

One line per (level, subtype), words in alphabetical order, so a moved word
shows as a changed line in an ordinary ``diff`` -- much easier to review than
the per-lemma files under ``data/release``. A headword with more than one sense
carries its disambiguation (or GUID) so the senses can be told apart.

``--mapping`` applies a ``curriculum_relevel`` proposal in memory, so the
before and after of a rebalance can be diffed without touching the database::

    PYTHONPATH=src python src/reports/level_words.py --output /tmp/before.txt
    PYTHONPATH=src python src/reports/level_words.py --output /tmp/after.txt \\
        --mapping /tmp/relevel/mapping.json
    diff /tmp/before.txt /tmp/after.txt

The relevel writes both files itself (``levels-before.txt`` and
``levels-after.txt``) next to its other artifacts.
"""

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from sqlalchemy.orm import Session

import constants
from reports.curriculum_bands import band_of
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.models.schema import Lemma

BAND_ORDER = ("core", "named", "topic", "gap", "excluded")
BAND_TITLES = {
    "core": f"Core ({constants.MIN_DIFFICULTY_LEVEL}-{constants.CORE_DIFFICULTY_LEVEL_MAX})",
    "named": (
        f"Named units ({constants.NAMED_DIFFICULTY_LEVEL_MIN}-"
        f"{constants.GENERAL_DIFFICULTY_LEVEL_MAX})"
    ),
    "topic": f"Topic ({constants.TOPIC_DIFFICULTY_LEVEL_MIN}-{constants.MAX_DIFFICULTY_LEVEL})",
    "gap": "Outside every band",
    "excluded": "Excluded",
}


@dataclass(frozen=True)
class LevelWord:
    """One sense at one level."""

    level: int
    pos_type: str
    pos_subtype: Optional[str]
    lemma_text: str
    disambiguation: Optional[str]
    guid: str


def ambiguous_headwords(session: Session) -> set[str]:
    """Casefolded headwords held by more than one live lemma, in any band."""
    counts = Counter(
        text.casefold()
        for (text,) in session.query(Lemma.lemma_text).filter(Lemma.guid.isnot(None)).all()
    )
    return {headword for headword, count in counts.items() if count > 1}


def format_level_words(
    words: Iterable[LevelWord],
    bands: Sequence[str] = BAND_ORDER,
    ambiguous: Optional[set[str]] = None,
) -> str:
    """Render words grouped by band, level and subtype.

    A word is labelled with its disambiguation whenever it has one, and with its
    GUID if it has none but shares its headword (``ambiguous``, from
    :func:`ambiguous_headwords`). Taking the shared headwords from the whole
    database, not from the words listed, keeps every listing's labels identical.
    """
    word_list = [word for word in words if band_of(word.level) in bands]
    if ambiguous is None:
        headword_counts = Counter(word.lemma_text.casefold() for word in word_list)
        ambiguous = {headword for headword, count in headword_counts.items() if count > 1}

    def label(word: LevelWord) -> str:
        if word.disambiguation:
            return f"{word.lemma_text} [{word.disambiguation}]"
        if word.lemma_text.casefold() in ambiguous:
            return f"{word.lemma_text} [{word.guid}]"
        return word.lemma_text

    by_level: dict[int, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for word in word_list:
        subtype = f"{word.pos_type}/{word.pos_subtype or word.pos_type}"
        by_level[word.level][subtype].append(label(word))

    lines: list[str] = []
    for band in BAND_ORDER:
        if band not in bands:
            continue
        levels = sorted(level for level in by_level if band_of(level) == band)
        if not levels:
            continue
        band_total = sum(len(items) for level in levels for items in by_level[level].values())
        lines.extend([f"# {BAND_TITLES[band]}: {len(levels)} levels, {band_total} words", ""])
        for level in levels:
            subtypes = by_level[level]
            level_total = sum(len(items) for items in subtypes.values())
            lines.append(f"## Level {level} ({level_total} words)")
            for subtype in sorted(subtypes, key=lambda key: (-len(subtypes[key]), key)):
                items = sorted(subtypes[subtype], key=str.casefold)
                lines.append(f"  {subtype} ({len(items)}): {', '.join(items)}")
            lines.append("")
    return "\n".join(lines)


def load_level_words(session: Session, mapping_path: Optional[Path] = None) -> list[LevelWord]:
    """Every levelled lemma, with a relevel ``mapping.json`` applied if given."""
    proposed: dict[str, int] = {}
    if mapping_path is not None:
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
        proposed = {item["guid"]: int(item["proposed_level"]) for item in payload["assignments"]}
    lemmas = (
        session.query(Lemma)
        .filter(Lemma.guid.isnot(None), Lemma.difficulty_level.isnot(None))
        .all()
    )
    return [
        LevelWord(
            level=proposed.get(lemma.guid or "", int(lemma.difficulty_level or 0)),
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            lemma_text=lemma.lemma_text,
            disambiguation=lemma.disambiguation,
            guid=lemma.guid or "",
        )
        for lemma in lemmas
    ]


def main() -> None:
    """Write the level listing for the current database or a proposal."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--db-path", type=Path, default=Path(constants.WORDFREQ_DB_PATH))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mapping",
        type=Path,
        help="curriculum_relevel mapping.json to apply before listing",
    )
    parser.add_argument(
        "--bands",
        default=",".join(BAND_ORDER),
        help=f"Comma-separated bands to list (default: {','.join(BAND_ORDER)})",
    )
    args = parser.parse_args()
    bands = [band.strip() for band in args.bands.split(",") if band.strip()]
    unknown = sorted(set(bands) - set(BAND_ORDER))
    if unknown:
        parser.error(f"Unknown band(s): {', '.join(unknown)}")

    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=str(args.db_path))
    session = create_session(config)
    try:
        words = load_level_words(session, args.mapping)
        ambiguous = ambiguous_headwords(session)
    finally:
        session.close()
    args.output.write_text(format_level_words(words, bands, ambiguous), encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
