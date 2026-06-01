#!/usr/bin/env python3
"""Find partial duplicate release lemmas across non-English translations.

A "partial duplicate" is a pair of release lemma entries that have different
English headwords, the same part of speech, and at least one identical
translation in another language. For example, English near-synonyms such as
"clearly" and "obviously" may need review if they share the same translation in
one or more target languages.
"""

import argparse
import itertools
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, DefaultDict, Iterable, Mapping, Sequence, cast

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.translation_helpers import RELEASE_LANGUAGES, SECONDARY_RELEASE_LANGUAGES

DEFAULT_RELEASE_DIR = Path(__file__).resolve().parents[2] / "data" / "release"


@dataclass(frozen=True)
class LemmaEntry:
    """One lemma row loaded from release JSONL data."""

    guid: str
    english: str
    pos_type: str
    pos_subtype: str
    concept_label: str
    concept_definition: str
    translations: Mapping[str, str]
    source_path: Path

    @property
    def pos_label(self) -> str:
        """Return a human-readable POS label including subtype when available."""
        if self.pos_subtype:
            return f"{self.pos_type}/{self.pos_subtype}"
        return self.pos_type


@dataclass
class PairCollision:
    """All shared non-English translations for a candidate duplicate pair."""

    first_entry: LemmaEntry
    second_entry: LemmaEntry
    shared_translations: dict[str, str] = field(default_factory=dict)

    @property
    def shared_language_count(self) -> int:
        """Return how many non-English languages collide for this pair."""
        return len(self.shared_translations)


def normalize_text(value: str | None) -> str:
    """Normalize text for duplicate comparisons."""
    if value is None:
        return ""
    return " ".join(value.strip().split()).casefold()


def get_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Find release lemmas with different English, the same POS, and matching "
            "translations in at least one non-English language."
        )
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_RELEASE_DIR,
        help="Release data directory to scan (default: data/release).",
    )
    parser.add_argument(
        "--languages",
        help=(
            "Comma-separated non-English language codes to compare. Defaults to all "
            "release and secondary-release languages present in the data."
        ),
    )
    parser.add_argument(
        "--min-languages",
        type=int,
        default=1,
        help="Minimum number of matching non-English languages required (default: 1).",
    )
    parser.add_argument(
        "--same-subtype",
        action="store_true",
        help="Require entries to have the same POS subtype as well as the same POS type.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of duplicate pairs to print.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of the text report.",
    )
    parser.add_argument(
        "--fail-on-found",
        action="store_true",
        help="Exit with status 1 when any matching partial duplicate is found.",
    )
    return parser


def load_secondary_translations(secondary_path: Path) -> dict[str, dict[str, str]]:
    """Load translations from a sibling secondary.jsonl file, keyed by GUID."""
    translations_by_guid: dict[str, dict[str, str]] = {}
    if not secondary_path.exists():
        return translations_by_guid

    for line_number, line in enumerate(secondary_path.read_text(encoding="utf-8").splitlines(), 1):
        stripped_line = line.strip()
        if not stripped_line:
            continue
        raw_row = cast(dict[str, Any], json.loads(stripped_line))
        guid = str(raw_row.get("guid", "")).strip()
        if not guid:
            raise ValueError(f"Missing guid in {secondary_path}:{line_number}")
        raw_translations = raw_row.get("translations", {})
        if not isinstance(raw_translations, dict):
            raise ValueError(f"Invalid translations in {secondary_path}:{line_number}")
        translations_by_guid[guid] = {
            str(language_code): str(translation)
            for language_code, translation in raw_translations.items()
            if translation is not None
        }
    return translations_by_guid


def load_entries(data_dir: Path) -> list[LemmaEntry]:
    """Load all lemma entries from data/release-style JSONL files."""
    lemma_root = data_dir / "lemmas"
    if not lemma_root.exists():
        raise ValueError(f"Release lemma directory does not exist: {lemma_root}")

    entries: list[LemmaEntry] = []
    for base_path in sorted(lemma_root.glob("*/*/base.jsonl")):
        secondary_translations = load_secondary_translations(base_path.with_name("secondary.jsonl"))
        for line_number, line in enumerate(base_path.read_text(encoding="utf-8").splitlines(), 1):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            raw_row = cast(dict[str, Any], json.loads(stripped_line))
            guid = str(raw_row.get("guid", "")).strip()
            if not guid:
                raise ValueError(f"Missing guid in {base_path}:{line_number}")
            raw_translations = raw_row.get("translations", {})
            if not isinstance(raw_translations, dict):
                raise ValueError(f"Invalid translations in {base_path}:{line_number}")

            translations = {
                str(language_code): str(translation)
                for language_code, translation in raw_translations.items()
                if translation is not None
            }
            translations.update(secondary_translations.get(guid, {}))
            english = translations.get("en", "").strip()
            if not english:
                raise ValueError(
                    f"Missing English translation for {guid} in {base_path}:{line_number}"
                )

            entries.append(
                LemmaEntry(
                    guid=guid,
                    english=english,
                    pos_type=str(raw_row.get("pos_type", "")).strip(),
                    pos_subtype=str(raw_row.get("pos_subtype", "")).strip(),
                    concept_label=str(raw_row.get("concept_label", "")).strip(),
                    concept_definition=str(raw_row.get("concept_definition", "")).strip(),
                    translations=translations,
                    source_path=base_path,
                )
            )
    return entries


def parse_languages(language_arg: str | None, entries: Sequence[LemmaEntry]) -> list[str]:
    """Return the non-English languages to compare."""
    if language_arg:
        languages = [language_code.strip().lower() for language_code in language_arg.split(",")]
        return [
            language_code for language_code in languages if language_code and language_code != "en"
        ]

    release_language_order = [
        language_code
        for language_code in RELEASE_LANGUAGES + SECONDARY_RELEASE_LANGUAGES
        if language_code != "en"
    ]
    languages_present = {
        language_code
        for entry in entries
        for language_code, translation in entry.translations.items()
        if language_code != "en" and translation.strip()
    }
    ordered_present_languages = [
        language_code
        for language_code in release_language_order
        if language_code in languages_present
    ]
    extra_languages = sorted(languages_present.difference(ordered_present_languages))
    return ordered_present_languages + extra_languages


def get_pos_key(entry: LemmaEntry, same_subtype: bool) -> tuple[str, ...]:
    """Return the POS grouping key for an entry."""
    if same_subtype:
        return (entry.pos_type, entry.pos_subtype)
    return (entry.pos_type,)


def find_partial_duplicates(
    entries: Iterable[LemmaEntry], languages: Sequence[str], same_subtype: bool
) -> list[PairCollision]:
    """Find candidate duplicate pairs and aggregate their colliding languages."""
    grouped_entries: DefaultDict[tuple[tuple[str, ...], str, str], list[LemmaEntry]] = defaultdict(
        list
    )
    for entry in entries:
        pos_key = get_pos_key(entry, same_subtype)
        for language_code in languages:
            translation = entry.translations.get(language_code, "").strip()
            normalized_translation = normalize_text(translation)
            if normalized_translation:
                grouped_entries[(pos_key, language_code, normalized_translation)].append(entry)

    collisions_by_pair: dict[tuple[str, str], PairCollision] = {}
    for (
        _pos_key,
        language_code,
        _normalized_translation,
    ), matching_entries in grouped_entries.items():
        distinct_english = {normalize_text(entry.english) for entry in matching_entries}
        if len(matching_entries) < 2 or len(distinct_english) < 2:
            continue

        for first_entry, second_entry in itertools.combinations(
            sorted(matching_entries, key=entry_sort_key), 2
        ):
            if normalize_text(first_entry.english) == normalize_text(second_entry.english):
                continue
            pair_key = (first_entry.guid, second_entry.guid)
            pair_collision = collisions_by_pair.get(pair_key)
            if pair_collision is None:
                pair_collision = PairCollision(
                    first_entry=first_entry,
                    second_entry=second_entry,
                )
                collisions_by_pair[pair_key] = pair_collision
            pair_collision.shared_translations[language_code] = first_entry.translations[
                language_code
            ].strip()

    return sorted(collisions_by_pair.values(), key=collision_sort_key)


def entry_sort_key(entry: LemmaEntry) -> tuple[str, str, str]:
    """Return a stable sort key for entries."""
    return (entry.pos_type, normalize_text(entry.english), entry.guid)


def collision_sort_key(collision: PairCollision) -> tuple[int, str, str, str]:
    """Sort likely duplicates first while keeping output stable."""
    return (
        -collision.shared_language_count,
        collision.first_entry.pos_type,
        normalize_text(collision.first_entry.english),
        normalize_text(collision.second_entry.english),
    )


def filter_collisions(
    collisions: Sequence[PairCollision], min_languages: int, limit: int | None
) -> list[PairCollision]:
    """Apply reporting filters to collisions."""
    filtered_collisions = [
        collision for collision in collisions if collision.shared_language_count >= min_languages
    ]
    if limit is not None:
        return filtered_collisions[:limit]
    return filtered_collisions


def entry_to_json(entry: LemmaEntry) -> dict[str, str]:
    """Convert an entry to JSON-serializable report data."""
    return {
        "guid": entry.guid,
        "english": entry.english,
        "pos_type": entry.pos_type,
        "pos_subtype": entry.pos_subtype,
        "concept_label": entry.concept_label,
        "concept_definition": entry.concept_definition,
        "source_path": str(entry.source_path),
    }


def print_json_report(
    entries: Sequence[LemmaEntry],
    languages: Sequence[str],
    collisions: Sequence[PairCollision],
    total_matching_collisions: int,
) -> None:
    """Print a machine-readable JSON report."""
    report = {
        "entries_scanned": len(entries),
        "languages_scanned": list(languages),
        "partial_duplicate_pairs_found": total_matching_collisions,
        "partial_duplicate_pairs_shown": len(collisions),
        "partial_duplicate_pairs": [
            {
                "shared_language_count": collision.shared_language_count,
                "shared_translations": dict(sorted(collision.shared_translations.items())),
                "entries": [
                    entry_to_json(collision.first_entry),
                    entry_to_json(collision.second_entry),
                ],
            }
            for collision in collisions
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


def format_entry(entry: LemmaEntry) -> str:
    """Format a lemma entry for human-readable output."""
    details = f"{entry.english} [{entry.guid}; {entry.pos_label}]"
    if entry.concept_definition:
        details = f"{details} :: {entry.concept_definition}"
    return details


def print_text_report(
    entries: Sequence[LemmaEntry],
    languages: Sequence[str],
    collisions: Sequence[PairCollision],
    total_matching_collisions: int,
) -> None:
    """Print a human-readable partial duplicate report."""
    print("Partial duplicate report")
    print(f"Entries scanned: {len(entries)}")
    print(f"Languages scanned: {', '.join(languages)}")
    print(f"Partial duplicate pairs found: {total_matching_collisions}")
    print(f"Partial duplicate pairs shown: {len(collisions)}")
    print()

    if not collisions:
        print("No partial duplicates found.")
        return

    for index, collision in enumerate(collisions, 1):
        first_entry = collision.first_entry
        second_entry = collision.second_entry
        shared_summary = ", ".join(
            f'{language_code}="{translation}"'
            for language_code, translation in sorted(collision.shared_translations.items())
        )
        print(
            f"{index}. {first_entry.english} ↔ {second_entry.english} "
            f"({first_entry.pos_type}; {collision.shared_language_count} language(s))"
        )
        print(f"   Shared translations: {shared_summary}")
        print(f"   - {format_entry(first_entry)}")
        print(f"   - {format_entry(second_entry)}")
        print()


def main() -> int:
    """Run the partial duplicate finder."""
    parser = get_argument_parser()
    args = parser.parse_args()
    if args.min_languages < 1:
        parser.error("--min-languages must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    entries = load_entries(args.data_dir)
    languages = parse_languages(args.languages, entries)
    all_collisions = find_partial_duplicates(entries, languages, args.same_subtype)
    matching_collisions = filter_collisions(all_collisions, args.min_languages, None)
    collisions = filter_collisions(all_collisions, args.min_languages, args.limit)

    if args.json:
        print_json_report(entries, languages, collisions, len(matching_collisions))
    else:
        print_text_report(entries, languages, collisions, len(matching_collisions))

    if args.fail_on_found and collisions:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
