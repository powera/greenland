"""Build a reviewable proposal for renumbering the vocabulary curriculum.

This command is deliberately read-only. It writes temporary CSV/JSON/Markdown
artifacts, but never changes the database. The generated ``mapping.json`` is a
temporary application artifact rather than a new curriculum source of truth.
"""

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

import constants
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.models.schema import (
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTier,
)
from storage.translation_helpers import RELEASE_LANGUAGES
from wordfreq.tools.country_override_manager import CountryOverrideManager
from wordfreq.tools.country_word_priorities import (
    get_supported_languages as get_country_languages,
)
from wordfreq.tools.family_relation_priorities import (
    get_supported_languages as get_family_languages,
)
from wordfreq.tools.family_relation_override_manager import FamilyRelationOverrideManager

TARGET_LEVEL_SIZE = 45
MIN_LEVEL_SIZE = 40
MAX_LEVEL_SIZE = 55
PRESERVED_LEVEL_MAX = 5
WORD_PATTERN = re.compile(r"[a-z0-9]+")
PROMINENCE_ORDER = {"very_common": 0, "common": 1, None: 1, "uncommon": 2, "rare": 3}

# These are intentionally broad curriculum themes, not a replacement taxonomy.
# The stored POS subtype remains the unit kept together inside each theme.
THEME_BY_SUBTYPE = {
    "food": "food_and_drink",
    "beverage": "food_and_drink",
    "emotion": "descriptions_and_feelings",
    "emotion_feeling": "descriptions_and_feelings",
    "emotional_state": "descriptions_and_feelings",
    "color": "descriptions_and_feelings",
    "shape": "descriptions_and_feelings",
    "size": "descriptions_and_feelings",
    "quality": "descriptions_and_feelings",
    "quality_attribute": "descriptions_and_feelings",
    "physical_property": "descriptions_and_feelings",
    "personal_quality": "descriptions_and_feelings",
    "style": "descriptions_and_feelings",
    "intensity": "descriptions_and_feelings",
    "completeness": "descriptions_and_feelings",
    "body_part": "body_and_health",
    "disease_condition": "body_and_health",
    "medication_remedy": "body_and_health",
    "building_structure": "home_and_buildings",
    "building_part": "home_and_buildings",
    "furniture": "home_and_buildings",
    "appliance": "home_and_buildings",
    "animal": "nature",
    "animal_grouping_term": "nature",
    "plant": "nature",
    "plant_part": "nature",
    "natural_feature": "nature",
    "material_substance": "objects_and_materials",
    "small_movable_object": "objects_and_materials",
    "clothing_accessory": "objects_and_materials",
    "electronic_device": "objects_and_materials",
    "technology_digital": "objects_and_materials",
    "tool": "objects_and_materials",
    "weapon": "objects_and_materials",
    "vehicle": "objects_and_materials",
    "artwork_artifact": "objects_and_materials",
    "region": "places_and_geography",
    "nationality": "places_and_geography",
    "city": "places_and_geography",
    "place_name": "places_and_geography",
    "geographic_place": "places_and_geography",
    "location": "places_and_geography",
    "path_infrastructure": "places_and_geography",
    "direction": "places_and_geography",
    "occupation": "people_and_society",
    "human": "people_and_society",
    "group_people": "people_and_society",
    "family_relation": "people_and_society",
    "honorific": "people_and_society",
    "social_institution": "people_and_society",
    "organization_name": "people_and_society",
    "knowledge_domain": "people_and_society",
    "physical_action": "actions",
    "directional_movement": "actions",
    "change": "actions",
    "existence": "actions",
    "possession": "actions",
    "perception": "actions",
    "mental_state": "actions",
    "communication": "actions",
    "creation_action": "actions",
    "destruction_action": "actions",
    "development": "actions",
    "activity": "ideas_and_events",
    "concept_idea": "ideas_and_events",
    "mental_construct": "ideas_and_events",
    "abstract_condition": "ideas_and_events",
    "process_event": "ideas_and_events",
    "communication_information": "ideas_and_events",
    "quantitative_concept": "numbers_and_time",
    "unit_of_measurement": "numbers_and_time",
    "cardinal": "numbers_and_time",
    "ordinal": "numbers_and_time",
    "sequence": "numbers_and_time",
    "time_period": "numbers_and_time",
    "temporal_name": "numbers_and_time",
    "relative_time": "numbers_and_time",
    "specific_time": "numbers_and_time",
    "duration": "numbers_and_time",
    "definite_frequency": "numbers_and_time",
    "preposition_other": "grammar_words",
    "conjunction_other": "grammar_words",
    "pronoun_other": "grammar_words",
    "determiner_other": "grammar_words",
    "adverb_other": "grammar_words",
    "interjection_other": "grammar_words",
}


@dataclass(frozen=True)
class Assignment:
    """One proposed base-level assignment."""

    lemma_id: int
    guid: str
    lemma_text: str
    definition_text: str
    disambiguation: Optional[str]
    sense_prominence: Optional[str]
    pos_type: str
    pos_subtype: Optional[str]
    frequency_rank: Optional[int]
    old_level: int
    proposed_level: int
    tier_evidence: str


@dataclass(frozen=True)
class WarningRow:
    """One curriculum review warning."""

    category: str
    headword: str
    guids: str
    details: str


def _balanced_sizes(item_count: int, chunk_count: int) -> list[int]:
    """Return chunk sizes differing by at most one."""
    quotient, remainder = divmod(item_count, chunk_count)
    return [quotient + (index < remainder) for index in range(chunk_count)]


def _semantic_key(lemma: Lemma, tiers: Mapping[int, Sequence[LemmaTier]]) -> tuple:
    """Order concepts into evidence-ranked semantic blocks."""
    tier_rows = tiers.get(lemma.id, ())
    tier_order = {
        "starters": 1,
        "movers": 2,
        "flyers": 3,
        "A1": 1,
        "basic": 1,
        "A2": 2,
        "extended": 2,
        "B1": 3,
        "B2": 4,
        "C1": 5,
        "C2": 6,
    }
    evidence_rank = min(
        (tier_order.get(tier.tier_name, 99) for tier in tier_rows),
        default=99,
    )
    semantic_block = lemma.pos_subtype or lemma.pos_type
    frequency_rank = lemma.frequency_rank if lemma.frequency_rank is not None else 10**9
    return (
        evidence_rank,
        semantic_block,
        frequency_rank,
        lemma.lemma_text.casefold(),
        lemma.guid or "",
    )


def _tier_evidence(tiers: Sequence[LemmaTier]) -> str:
    return "; ".join(
        f"{tier.source}:{tier.tier_name}"
        for tier in sorted(tiers, key=lambda item: (item.source, item.tier_name))
    )


def _theme(lemma: Lemma) -> str:
    """Return the broad curriculum theme for a stored subtype."""
    subtype = lemma.pos_subtype or lemma.pos_type
    return THEME_BY_SUBTYPE.get(subtype, f"other_{lemma.pos_type}")


def _split_subtype_run(items: Sequence[Lemma]) -> list[list[Lemma]]:
    """Split a subtype into movable groups of 5-10 whenever possible."""
    if len(items) < 5:
        return [list(items)]
    chunk_count = math.ceil(len(items) / 10)
    sizes = _balanced_sizes(len(items), chunk_count)
    runs: list[list[Lemma]] = []
    offset = 0
    for chunk_size in sizes:
        runs.append(list(items[offset : offset + chunk_size]))
        offset += chunk_size
    return runs


def _pack_runs(runs: Sequence[Sequence[Lemma]]) -> list[list[Lemma]]:
    """Partition ordered subtype groups into coherent 40-55-sense levels."""
    run_list = [list(run) for run in runs]
    best: list[Optional[tuple[int, int]]] = [None] * (len(run_list) + 1)
    best[0] = (0, -1)
    for end_index in range(1, len(run_list) + 1):
        item_count = 0
        for start_index in range(end_index - 1, -1, -1):
            item_count += len(run_list[start_index])
            if item_count > MAX_LEVEL_SIZE:
                break
            prior_result = best[start_index]
            if item_count < MIN_LEVEL_SIZE or prior_result is None:
                continue
            segment = run_list[start_index:end_index]
            subtype_count = len(
                {
                    (lemma.pos_type, lemma.pos_subtype or lemma.pos_type)
                    for run in segment
                    for lemma in run
                }
            )
            theme_count = len({_theme(run[0]) for run in segment})
            segment_cost = (
                abs(item_count - TARGET_LEVEL_SIZE)
                + max(0, subtype_count - 1) * 3
                + max(0, theme_count - 1) * 25
            )
            prior_cost = prior_result[0]
            candidate = (prior_cost + segment_cost, start_index)
            current_result = best[end_index]
            if current_result is None or candidate[0] < current_result[0]:
                best[end_index] = candidate
    if best[-1] is None:
        raise ValueError("Could not partition subtype runs into 40-55-sense levels")

    boundaries: list[tuple[int, int]] = []
    end_index = len(run_list)
    while end_index > 0:
        result = best[end_index]
        if result is None:
            raise AssertionError("Broken curriculum partition path")
        start_index = result[1]
        boundaries.append((start_index, end_index))
        end_index = start_index
    boundaries.reverse()
    return [
        [lemma for run in run_list[start_index:end_index] for lemma in run]
        for start_index, end_index in boundaries
    ]


def build_assignments(session: Session, *, mode: str = "auto") -> list[Assignment]:
    """Build the deterministic GUID-to-level proposal from the current database."""
    lemmas = (
        session.query(Lemma)
        .filter(
            Lemma.guid.isnot(None),
            Lemma.difficulty_level.between(
                constants.MIN_DIFFICULTY_LEVEL,
                constants.MAX_DIFFICULTY_LEVEL,
            ),
        )
        .all()
    )
    tier_rows = session.query(LemmaTier).all()
    tiers_by_lemma: dict[int, list[LemmaTier]] = defaultdict(list)
    for tier_row in tier_rows:
        tiers_by_lemma[tier_row.lemma_id].append(tier_row)

    proposed_by_id: dict[int, int] = {}
    for lemma in lemmas:
        if lemma.difficulty_level is not None and lemma.difficulty_level <= PRESERVED_LEVEL_MAX:
            proposed_by_id[lemma.id] = lemma.difficulty_level

    current_max_level = max(int(lemma.difficulty_level or 0) for lemma in lemmas)
    resolved_mode = "incremental" if mode == "auto" and current_max_level > 33 else mode
    if resolved_mode not in {"rebuild", "incremental"}:
        raise ValueError(f"Unknown curriculum layout mode: {mode}")
    if resolved_mode == "incremental":
        for lemma in lemmas:
            proposed_by_id[lemma.id] = int(lemma.difficulty_level or 0)

    relevel_lemmas = [
        lemma
        for lemma in lemmas
        if lemma.difficulty_level is not None and lemma.difficulty_level > PRESERVED_LEVEL_MAX
    ]
    if resolved_mode == "rebuild":
        by_theme: dict[str, list[Lemma]] = defaultdict(list)
        for lemma in relevel_lemmas:
            by_theme[_theme(lemma)].append(lemma)
        ordered_themes = sorted(
            by_theme,
            key=lambda theme_name: (
                sum(int(lemma.difficulty_level or 0) for lemma in by_theme[theme_name])
                / len(by_theme[theme_name]),
                min(int(lemma.difficulty_level or 0) for lemma in by_theme[theme_name]),
                theme_name,
            ),
        )
        subtype_runs: list[list[Lemma]] = []
        for theme_name in ordered_themes:
            theme_lemmas = by_theme[theme_name]
            by_subtype: dict[tuple[str, str], list[Lemma]] = defaultdict(list)
            for lemma in theme_lemmas:
                by_subtype[(lemma.pos_type, lemma.pos_subtype or lemma.pos_type)].append(lemma)
            ordered_subtypes = sorted(
                by_subtype,
                key=lambda subtype_key: (
                    sum(int(lemma.difficulty_level or 0) for lemma in by_subtype[subtype_key])
                    / len(by_subtype[subtype_key]),
                    subtype_key,
                ),
            )
            for subtype_key in ordered_subtypes:
                subtype_lemmas = by_subtype[subtype_key]
                subtype_lemmas.sort(key=lambda lemma: _semantic_key(lemma, tiers_by_lemma))
                subtype_runs.extend(_split_subtype_run(subtype_lemmas))

        next_level = PRESERVED_LEVEL_MAX + 1
        for packed_level in _pack_runs(subtype_runs):
            for lemma in packed_level:
                proposed_by_id[lemma.id] = next_level
            next_level += 1

    assignments = [
        Assignment(
            lemma_id=lemma.id,
            guid=lemma.guid or "",
            lemma_text=lemma.lemma_text,
            definition_text=lemma.definition_text,
            disambiguation=lemma.disambiguation,
            sense_prominence=lemma.sense_prominence,
            pos_type=lemma.pos_type,
            pos_subtype=lemma.pos_subtype,
            frequency_rank=lemma.frequency_rank,
            old_level=int(lemma.difficulty_level or 0),
            proposed_level=proposed_by_id[lemma.id],
            tier_evidence=_tier_evidence(tiers_by_lemma.get(lemma.id, [])),
        )
        for lemma in lemmas
    ]
    return sorted(assignments, key=lambda item: (item.proposed_level, item.guid))


def build_warnings(session: Session, assignments: Sequence[Assignment]) -> list[WarningRow]:
    """Build sense, definition, and lemma/form review warnings."""
    warnings: list[WarningRow] = []
    by_headword: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        by_headword[assignment.lemma_text.casefold()].append(assignment)

    for senses in by_headword.values():
        if len(senses) < 2:
            continue
        headword = senses[0].lemma_text
        guids = ";".join(sorted(sense.guid for sense in senses))
        warnings.append(WarningRow("polysemy", headword, guids, f"{len(senses)} active senses"))
        missing = [sense.guid for sense in senses if not sense.disambiguation]
        if missing:
            warnings.append(
                WarningRow(
                    "missing-disambiguation",
                    headword,
                    ";".join(missing),
                    "Polysemous sense has no disambiguation",
                )
            )
        ordered = sorted(senses, key=lambda item: (item.old_level, item.guid))
        for earlier, later in zip(ordered, ordered[1:]):
            if PROMINENCE_ORDER.get(later.sense_prominence, 1) < PROMINENCE_ORDER.get(
                earlier.sense_prominence, 1
            ):
                warnings.append(
                    WarningRow(
                        "suspicious-sense-order",
                        headword,
                        f"{earlier.guid};{later.guid}",
                        f"more prominent sense was later ({earlier.old_level} before {later.old_level})",
                    )
                )
        for left_index, left in enumerate(senses):
            left_words = set(WORD_PATTERN.findall(left.definition_text.casefold()))
            for right in senses[left_index + 1 :]:
                right_words = set(WORD_PATTERN.findall(right.definition_text.casefold()))
                union = left_words | right_words
                overlap = len(left_words & right_words) / len(union) if union else 0.0
                if overlap >= 0.55:
                    warnings.append(
                        WarningRow(
                            "overlapping-definition",
                            headword,
                            f"{left.guid};{right.guid}",
                            f"definition token similarity {overlap:.0%}",
                        )
                    )

    active_text_to_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        active_text_to_assignments[assignment.lemma_text.casefold()].append(assignment)
    english_forms = (
        session.query(DerivativeForm)
        .filter(
            DerivativeForm.language_code == "en", DerivativeForm.is_base_form == False
        )  # noqa: E712
        .all()
    )
    seen_inflections: set[tuple[str, int]] = set()
    assignment_by_id = {assignment.lemma_id: assignment for assignment in assignments}
    for derivative_form in english_forms:
        matching_assignments = [
            item
            for item in active_text_to_assignments.get(
                derivative_form.derivative_form_text.casefold(), []
            )
            if item.lemma_id != derivative_form.lemma_id
        ]
        matching_guids = [item.guid for item in matching_assignments]
        if not matching_guids or derivative_form.lemma_id not in assignment_by_id:
            continue
        warning_key = (derivative_form.derivative_form_text.casefold(), derivative_form.lemma_id)
        if warning_key in seen_inflections:
            continue
        seen_inflections.add(warning_key)
        owner = assignment_by_id[derivative_form.lemma_id]
        warnings.append(
            WarningRow(
                "inflection-as-lemma",
                derivative_form.derivative_form_text,
                ";".join(sorted(matching_guids)),
                f"also an English {derivative_form.grammatical_form} form of {owner.lemma_text} ({owner.guid})",
            )
        )

    fashion_senses = by_headword.get("fashion", [])
    if len(fashion_senses) == 1:
        warnings.append(
            WarningRow(
                "sense-inventory-watch",
                "fashion",
                fashion_senses[0].guid,
                "Only one stored sense; review whether the verb sense is intentionally absent",
            )
        )
    by_proposed_level: dict[int, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        by_proposed_level[assignment.proposed_level].append(assignment)
    for proposed_level, level_assignments in sorted(by_proposed_level.items()):
        if proposed_level <= PRESERVED_LEVEL_MAX:
            continue
        if not MIN_LEVEL_SIZE <= len(level_assignments) <= MAX_LEVEL_SIZE:
            warnings.append(
                WarningRow(
                    "level-size",
                    f"level {proposed_level}",
                    ";".join(item.guid for item in level_assignments),
                    f"{len(level_assignments)} senses; target is {MIN_LEVEL_SIZE}-{MAX_LEVEL_SIZE}",
                )
            )
        subtype_counts = Counter(
            (item.pos_type, item.pos_subtype or item.pos_type) for item in level_assignments
        )
        for (pos_type, pos_subtype), subtype_count in subtype_counts.items():
            if subtype_count >= 5:
                continue
            matching_guids = [
                item.guid
                for item in level_assignments
                if (item.pos_type, item.pos_subtype or item.pos_type) == (pos_type, pos_subtype)
            ]
            warnings.append(
                WarningRow(
                    "thin-subtype-group",
                    f"level {proposed_level}: {pos_type}/{pos_subtype}",
                    ";".join(matching_guids),
                    f"only {subtype_count} senses from this subtype",
                )
            )
    return sorted(warnings, key=lambda item: (item.category, item.headword.casefold(), item.guids))


def _themes(assignments: Iterable[Assignment]) -> str:
    counts = Counter((item.pos_subtype or item.pos_type) for item in assignments)
    return ", ".join(f"{theme} ({count})" for theme, count in counts.most_common(5))


def _scripted_effective_levels(
    session: Session,
    assignments: Sequence[Assignment],
) -> dict[str, Counter[int]]:
    """Simulate current manual overrides followed by country/family configuration."""
    levels_by_id = {item.lemma_id: item.proposed_level for item in assignments}
    assignments_by_id = {item.lemma_id: item for item in assignments}
    assignments_by_guid = {item.guid: item for item in assignments}
    stored: dict[tuple[int, str], int] = {
        (row.lemma_id, row.language_code): row.difficulty_level
        for row in session.query(LemmaDifficultyOverride).all()
    }
    country_languages = set(get_country_languages())
    family_languages = set(get_family_languages())
    country_manager = CountryOverrideManager(session)
    for language_code in country_languages:
        country_summary = country_manager.preview_changes(language_code, include_unchanged=True)
        for country_change in country_summary.changes:
            matching_assignment = assignments_by_guid.get(country_change.guid)
            if matching_assignment is not None:
                stored[(matching_assignment.lemma_id, language_code)] = (
                    country_change.proposed_level
                )

    family_manager = FamilyRelationOverrideManager(session)
    for language_code in family_languages:
        family_summary = family_manager.preview_changes(language_code, include_unchanged=True)
        for family_change in family_summary.changes:
            matching_assignment = assignments_by_guid.get(family_change.guid)
            if matching_assignment is None:
                continue
            override_key = (matching_assignment.lemma_id, language_code)
            if family_change.is_exclusion:
                stored[override_key] = constants.EXCLUDE_DIFFICULTY_LEVEL
            else:
                stored.pop(override_key, None)

    counts_by_language: dict[str, Counter[int]] = {}
    for language_code in RELEASE_LANGUAGES:
        language_counts: Counter[int] = Counter()
        for lemma_id, base_level in levels_by_id.items():
            if lemma_id not in assignments_by_id:
                continue
            effective_level = stored.get((lemma_id, language_code), base_level)
            language_counts[effective_level] += 1
        counts_by_language[language_code] = language_counts
    return counts_by_language


def write_report(
    session: Session,
    assignments: Sequence[Assignment],
    warnings: Sequence[WarningRow],
    output_dir: Path,
) -> None:
    """Write all temporary review artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    assignment_fields = list(Assignment.__dataclass_fields__)
    with (output_dir / "assignments.csv").open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=assignment_fields)
        writer.writeheader()
        for assignment in assignments:
            writer.writerow(assignment.__dict__)

    mapping_payload = {
        "format": "greenland-curriculum-relevel-v1",
        "supported_level_max": constants.MAX_DIFFICULTY_LEVEL,
        "assignments": [
            {
                "guid": item.guid,
                "old_level": item.old_level,
                "proposed_level": item.proposed_level,
            }
            for item in assignments
        ],
    }
    (output_dir / "mapping.json").write_text(
        json.dumps(mapping_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with (output_dir / "warnings.csv").open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(WarningRow.__dataclass_fields__))
        writer.writeheader()
        for warning in warnings:
            writer.writerow(warning.__dict__)

    by_old: dict[int, list[Assignment]] = defaultdict(list)
    by_proposed: dict[int, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        by_old[assignment.old_level].append(assignment)
        by_proposed[assignment.proposed_level].append(assignment)

    effective_counts = _scripted_effective_levels(session, assignments)
    with (output_dir / "effective-language-counts.csv").open(
        "w", encoding="utf-8", newline=""
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=("language_code", "level", "effective_count"),
        )
        writer.writeheader()
        for language_code, level_counts in effective_counts.items():
            for level, count in sorted(level_counts.items()):
                writer.writerow(
                    {
                        "language_code": language_code,
                        "level": level,
                        "effective_count": count,
                    }
                )

    lines = [
        "# Vocabulary curriculum relevel proposal",
        "",
        "This is a read-only proposal generated from SQLite. Levels 1–5 are fixed; "
        "later levels are assembled from contiguous subtype runs inside broad curriculum themes. "
        "No excluded (`-1`) or unlevelled (`NULL`) lemma is mapped.",
        "",
        f"- Active mapped senses: {len(assignments)}",
        f"- Proposed populated range: 1–{max(by_proposed)}",
        f"- Reserved empty range: {max(by_proposed) + 1}–{constants.MAX_DIFFICULTY_LEVEL}",
        f"- Review warnings: {len(warnings)}",
        "",
        "## Current levels",
        "",
        "| Level | Count | Leading themes |",
        "|---:|---:|---|",
    ]
    for level in range(constants.MIN_DIFFICULTY_LEVEL, constants.MAX_DIFFICULTY_LEVEL + 1):
        level_assignments = by_old.get(level, [])
        lines.append(f"| {level} | {len(level_assignments)} | {_themes(level_assignments)} |")
    lines.extend(
        [
            "",
            "## Proposed levels",
            "",
            "| Level | Count | Source levels | Leading themes |",
            "|---:|---:|---|---|",
        ]
    )
    for level in range(constants.MIN_DIFFICULTY_LEVEL, constants.MAX_DIFFICULTY_LEVEL + 1):
        level_assignments = by_proposed.get(level, [])
        source_levels = ", ".join(
            str(value) for value in sorted({a.old_level for a in level_assignments})
        )
        lines.append(
            f"| {level} | {len(level_assignments)} | {source_levels} | {_themes(level_assignments)} |"
        )
    warning_counts = Counter(warning.category for warning in warnings)
    lines.extend(["", "## Warning summary", ""])
    for category, count in sorted(warning_counts.items()):
        lines.append(f"- {category}: {count}")
    lines.extend(
        [
            "",
            "See `assignments.csv` for definitions and evidence, `warnings.csv` for review items, "
            "`effective-language-counts.csv` for the simulated post-script distribution, and "
            "`mapping.json` for the migration input.",
            "",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Generate a temporary curriculum relevel report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=constants.WORDFREQ_DB_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("auto", "rebuild", "incremental"),
        default="auto",
        help="Auto rebuilds the legacy <=33 layout and preserves an established >33 layout",
    )
    args = parser.parse_args()
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)
    session = create_session(config)
    try:
        assignments = build_assignments(session, mode=args.mode)
        warnings = build_warnings(session, assignments)
        write_report(session, assignments, warnings, args.output_dir)
    finally:
        session.close()
    print(f"Wrote read-only proposal for {len(assignments)} active senses to {args.output_dir}")


if __name__ == "__main__":
    main()
