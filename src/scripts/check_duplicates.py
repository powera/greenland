#!/usr/bin/env python3
"""Check duplicate release words for a specific language.

This script loads lemma data through the existing storage backend layer, then
groups entries by their word form in a requested language and classifies
collisions into three buckets:

1. Same word but different POS
2. Meaning collisions (same surface form, same POS, different concepts)
3. Duplicates (same surface form, same POS, same concept listed multiple times)

By default this reads from the release JSONL data under ``data/release/lemmas``
via the JSONL backend, which internally populates a temporary SQLite database
for queries. The backend can still be overridden with the usual storage flags.
"""

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Iterable, Sequence, cast

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.common.common_args import add_backend_args, add_common_args, get_data_source_config
from storage.backend.factory import create_session
from storage.models.schema import Lemma, LemmaTranslation
from storage.translation_helpers import LANGUAGE_FIELDS

DEFAULT_RELEASE_DIR = Path(__file__).resolve().parents[2] / "data" / "release"


@dataclass(frozen=True)
class LemmaEntry:
    """Minimal lemma data needed for duplicate classification."""

    guid: str
    word: str
    lemma_text: str
    definition_text: str
    disambiguation: str
    pos_type: str
    pos_subtype: str

    @property
    def pos_label(self) -> str:
        """Return a human-readable POS label."""
        if self.pos_subtype:
            return f"{self.pos_type}/{self.pos_subtype}"
        return self.pos_type

    @property
    def concept_label(self) -> str:
        """Return a readable concept label for output."""
        if self.disambiguation:
            return f"{self.lemma_text} ({self.disambiguation})"
        return self.lemma_text

    @property
    def concept_key(self) -> tuple[str, str, str]:
        """Return a normalized concept identity for duplicate detection."""
        return (
            normalize_text(self.lemma_text),
            normalize_text(self.definition_text),
            normalize_text(self.disambiguation),
        )


def normalize_text(value: str | None) -> str:
    """Normalize text for grouping/comparison."""
    if value is None:
        return ""
    return " ".join(value.strip().split()).casefold()


def get_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Check duplicate and colliding release words for a language."
    )
    parser.add_argument(
        "language",
        help="Language code to analyze (for example: lt, zh, fr, es, de)",
    )
    add_common_args(parser)
    add_backend_args(parser)
    parser.set_defaults(backend="jsonl", data_dir=str(DEFAULT_RELEASE_DIR))
    return parser


def validate_language(language_code: str) -> str:
    """Validate the requested language code."""
    normalized_code = language_code.strip().lower()
    if normalized_code not in LANGUAGE_FIELDS:
        supported_codes = ", ".join(sorted(LANGUAGE_FIELDS.keys()))
        raise ValueError(
            f"Unsupported language code '{language_code}'. Supported codes: {supported_codes}"
        )
    return normalized_code


def load_entries(language_code: str, args: argparse.Namespace) -> list[LemmaEntry]:
    """Load lemma entries for the requested language."""
    config = get_data_source_config(args)
    session = create_session(config)
    try:
        rows = cast(
            Sequence[tuple[Lemma, LemmaTranslation]],
            session.query(Lemma, LemmaTranslation)
            .join(LemmaTranslation, LemmaTranslation.lemma_id == Lemma.id)
            .filter(LemmaTranslation.language_code == language_code)
            .filter(Lemma.guid.isnot(None))
            .order_by(LemmaTranslation.translation, Lemma.pos_type, Lemma.pos_subtype, Lemma.id)
            .all(),
        )
    finally:
        session.close()

    entries: list[LemmaEntry] = []
    for lemma, translation in rows:
        normalized_word = translation.translation.strip()
        if not normalized_word:
            continue
        entries.append(
            LemmaEntry(
                guid=lemma.guid or "",
                word=normalized_word,
                lemma_text=lemma.lemma_text,
                definition_text=lemma.definition_text,
                disambiguation=lemma.disambiguation or "",
                pos_type=lemma.pos_type,
                pos_subtype=lemma.pos_subtype or "",
            )
        )
    return entries


def group_by_word(entries: Iterable[LemmaEntry]) -> dict[str, list[LemmaEntry]]:
    """Group entries by normalized word text."""
    grouped_entries: DefaultDict[str, list[LemmaEntry]] = defaultdict(list)
    for entry in entries:
        grouped_entries[normalize_text(entry.word)].append(entry)
    return dict(grouped_entries)


def classify_same_word_different_pos(
    grouped_entries: dict[str, list[LemmaEntry]],
) -> list[tuple[str, list[LemmaEntry]]]:
    """Find words that occur under multiple POS labels."""
    collisions: list[tuple[str, list[LemmaEntry]]] = []
    for entries in grouped_entries.values():
        pos_labels = {entry.pos_label for entry in entries}
        if len(entries) > 1 and len(pos_labels) > 1:
            collisions.append((entries[0].word, sorted(entries, key=_entry_sort_key)))
    return sorted(collisions, key=lambda item: normalize_text(item[0]))


def classify_meaning_collisions(
    grouped_entries: dict[str, list[LemmaEntry]],
) -> list[tuple[str, str, list[LemmaEntry]]]:
    """Find same-word same-POS groups with different concepts."""
    collisions: list[tuple[str, str, list[LemmaEntry]]] = []
    for entries in grouped_entries.values():
        entries_by_pos: DefaultDict[str, list[LemmaEntry]] = defaultdict(list)
        for entry in entries:
            entries_by_pos[entry.pos_label].append(entry)
        for pos_label, pos_entries in entries_by_pos.items():
            concept_keys = {entry.concept_key for entry in pos_entries}
            if len(pos_entries) > 1 and len(concept_keys) > 1:
                collisions.append(
                    (pos_entries[0].word, pos_label, sorted(pos_entries, key=_entry_sort_key))
                )
    return sorted(collisions, key=lambda item: (normalize_text(item[0]), item[1]))


def classify_duplicates(
    grouped_entries: dict[str, list[LemmaEntry]],
) -> list[tuple[str, str, tuple[str, str, str], list[LemmaEntry]]]:
    """Find exact duplicates with same word, POS, and concept identity."""
    duplicates: list[tuple[str, str, tuple[str, str, str], list[LemmaEntry]]] = []
    for entries in grouped_entries.values():
        concept_groups: DefaultDict[tuple[str, str, str, str], list[LemmaEntry]] = defaultdict(list)
        for entry in entries:
            group_key = (entry.pos_label, *entry.concept_key)
            concept_groups[group_key].append(entry)
        for group_key, duplicate_entries in concept_groups.items():
            if len(duplicate_entries) > 1:
                pos_label = group_key[0]
                concept_key = group_key[1:]
                duplicates.append(
                    (
                        duplicate_entries[0].word,
                        pos_label,
                        concept_key,
                        sorted(duplicate_entries, key=_entry_sort_key),
                    )
                )
    return sorted(duplicates, key=lambda item: (normalize_text(item[0]), item[1], item[2]))


def _entry_sort_key(entry: LemmaEntry) -> tuple[str, str, str, str]:
    """Provide stable sorting for output rows."""
    return (
        entry.pos_label,
        normalize_text(entry.lemma_text),
        normalize_text(entry.disambiguation),
        entry.guid,
    )


def format_entry(entry: LemmaEntry) -> str:
    """Format one lemma entry for display."""
    concept_text = entry.concept_label
    if entry.definition_text:
        return (
            f"- {entry.pos_label}: {concept_text} :: {entry.definition_text} "
            f"[guid={entry.guid}]"
        )
    return f"- {entry.pos_label}: {concept_text} [guid={entry.guid}]"


def print_same_word_different_pos(groups: Sequence[tuple[str, list[LemmaEntry]]]) -> None:
    """Print groups classified as same word, different POS."""
    print(f"=== Same word, different POS ({len(groups)}) ===")
    if not groups:
        print("None")
        print()
        return

    for word, entries in groups:
        pos_summary = ", ".join(sorted({entry.pos_label for entry in entries}))
        print(f"{word} -> {pos_summary}")
        for entry in entries:
            print(format_entry(entry))
        print()


def print_meaning_collisions(groups: Sequence[tuple[str, str, list[LemmaEntry]]]) -> None:
    """Print groups classified as meaning collisions."""
    print(f"=== Meaning collisions ({len(groups)}) ===")
    if not groups:
        print("None")
        print()
        return

    for word, pos_label, entries in groups:
        print(f"{word} [{pos_label}]")
        for entry in entries:
            print(format_entry(entry))
        print()


def print_duplicates(
    groups: Sequence[tuple[str, str, tuple[str, str, str], list[LemmaEntry]]],
) -> None:
    """Print groups classified as exact duplicates."""
    print(f"=== Duplicates ({len(groups)}) ===")
    if not groups:
        print("None")
        print()
        return

    for word, pos_label, _concept_key, entries in groups:
        print(f"{word} [{pos_label}]")
        for entry in entries:
            print(format_entry(entry))
        print()


def print_summary(
    language_code: str,
    entries: Sequence[LemmaEntry],
    same_word_different_pos: Sequence[tuple[str, list[LemmaEntry]]],
    meaning_collisions: Sequence[tuple[str, str, list[LemmaEntry]]],
    duplicates: Sequence[tuple[str, str, tuple[str, str, str], list[LemmaEntry]]],
    args: argparse.Namespace,
) -> None:
    """Print a top-level summary before the detailed sections."""
    language_name = LANGUAGE_FIELDS[language_code][1]
    backend_name = args.backend or "sqlite"
    print(
        f"Duplicate report for {language_name} ({language_code}) " f"using backend={backend_name}"
    )
    if getattr(args, "data_dir", None):
        print(f"Data dir: {args.data_dir}")
    if getattr(args, "db_path", None):
        print(f"DB path: {args.db_path}")
    print(f"Entries scanned: {len(entries)}")
    print(f"Same word, different POS groups: {len(same_word_different_pos)}")
    print(f"Meaning collision groups: {len(meaning_collisions)}")
    print(f"Duplicate groups: {len(duplicates)}")
    print()


def main() -> int:
    """Run the duplicate checker CLI."""
    parser = get_argument_parser()
    args = parser.parse_args()

    try:
        language_code = validate_language(args.language)
    except ValueError as exc:
        parser.error(str(exc))

    entries = load_entries(language_code, args)
    grouped_entries = group_by_word(entries)
    same_word_different_pos = classify_same_word_different_pos(grouped_entries)
    meaning_collisions = classify_meaning_collisions(grouped_entries)
    duplicates = classify_duplicates(grouped_entries)

    print_summary(
        language_code=language_code,
        entries=entries,
        same_word_different_pos=same_word_different_pos,
        meaning_collisions=meaning_collisions,
        duplicates=duplicates,
        args=args,
    )
    print_same_word_different_pos(same_word_different_pos)
    print_meaning_collisions(meaning_collisions)
    print_duplicates(duplicates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
