"""Build a reviewable proposal for rebalancing the vocabulary curriculum.

The proposal is written as CSV/JSON/Markdown artifacts; ``--apply`` then backs
up the database and writes the moves. The two bands it rebalances have
different shapes:

* **Core (1-30).** Levels 1-5 are hand-curated and fixed. From level 6 each
  level holds 30-40 words: two or three content subtypes, one to five verbs
  that go with them (by corpus co-occurrence lift), and a few function words,
  which are spread through the core rather than taught as a block. A headword
  keeps one sense here; see ``curriculum_sense_fixes``.
* **Named (100-499).** Each unit is one topic, ideally one subtype, of ~35
  words. A coherent group may run to 55 (all US states) rather than be split.
  Numbers in this band are not a teaching order, so a unit keeps the number
  most of its words already have.

The topic band (1000+) is never touched, and no word changes band except a
lesser sense leaving the core.

Missing frequency data always reads as uncommon, and the packer leans towards
the current layout whenever the evidence is not clear; see
``reports.curriculum_bands`` for both rules.
"""

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

import constants
from reports.curriculum_bands import (
    CORE_RULES,
    COUNTRY_COHORT_LEVEL,
    COUNTRY_LEVEL_CAPACITIES,
    NAMED_RULES,
    NO_TIER,
    PRESERVED_LEVEL_MAX,
    TIER_ORDER,
    UNRANKED_SENTINEL,
    US_STATE_COHORT_LEVEL,
    PlannedMove,
    RankEvidence,
    WarningRow,
    apply_moves,
    backup_database,
    band_of,
    current_level,
    effective_rank,
    family_reserved_level,
    is_function_pos,
    is_function_word,
    is_us_state,
    load_rank_evidence,
    load_verb_affinity,
    stable_commonness_key,
    subtype_key,
)
from reports.curriculum_sense_fixes import named_destinations, plan_core_polysemy
from reports.level_words import LevelWord, ambiguous_headwords, format_level_words
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.models.schema import (
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTier,
)
from storage.translation_helpers import RELEASE_LANGUAGES
from wordfreq.corpora.cooccurrence import HARDCODED_VERB_LEVELS
from wordfreq.tools.country_override_manager import CountryOverrideManager
from wordfreq.tools.country_word_priorities import (
    CONTINENT_NAMES,
    COUNTRY_NAMES,
    get_supported_languages as get_country_languages,
)
from wordfreq.tools.family_relation_override_manager import FamilyRelationOverrideManager
from wordfreq.tools.family_relation_priorities import (
    get_supported_languages as get_family_languages,
)

SOURCE = "curriculum/relevel"
DEFAULT_COOCCURRENCE = Path("data/wordfreq/cooccurrence.json")
BANDS = ("core", "named")
WORD_PATTERN = re.compile(r"[a-z0-9]+")

# Core content subtypes are cut into chunks of about this size, so that two or
# three of them make a level and the commonest words of a subtype come first.
CORE_CHUNK_TARGET = 12
CORE_CHUNK_MAX = 15
CORE_SUBTYPES_PER_LEVEL = (2, 3)
CORE_VERBS_PER_LEVEL = (1, 5)
# How far below / above its share a level's content may run before the
# function words even it out.
CORE_CONTENT_SLACK = (6, 3)
# How many chunks ahead the core may look for a different subtype to pull
# forward, so one big subtype does not fill several levels alone.
CORE_INTERLEAVE_WINDOW = 3
# Most content words one subtype may hold in the core (levels 1-5 included);
# the least common rest go to named units. Some subtypes are held far lower:
# ten drinks is plenty, and medicine is not early vocabulary for high school
# students.
CORE_SUBTYPE_CAP = 60
CORE_SUBTYPE_CAPS: Mapping[str, int] = {
    "food": 70,
    "beverage": 10,
    "disease_condition": 8,
    "medication_remedy": 2,
}
# A subtype listed here keeps a core word only if it is common by both
# measures: ranked better than this ceiling (missing corpus data counts as
# rare), and on a learner list -- any Cambridge YLE level, or CEFR
# CORE_MAX_CEFR or easier. A count cap alone kept brown sugar and beet; rank
# alone keeps turnip and walnut, and a tier alone keeps pancake, which no
# corpus lists.
CORE_RANK_CEILINGS: Mapping[str, int] = {
    "food": 5000,
    "body_part": 5000,
}
CORE_MAX_CEFR = "B1"
# A subtype with several core chunks has them spread through the core at
# least this many chunks apart (a level holds two or three), rather than
# kept together where the old curriculum had its food block.
CORE_SPREAD_MIN_GAP = 5
# A beverage whose definition mentions any of these is alcoholic, and never
# belongs in the core.
ALCOHOL_MARKERS = ("alcohol", "wine", "liquor")

# A verb pairs with a subtype when that subtype turns up this many times more
# often after it than after verbs in general. Moving a verb away from where
# its level-mates went takes a clearly better pairing, and more so for a move
# to a later level than an earlier one.
MIN_LIFT = 1.5
EARLIER_LIFT_FACTOR = 1.5
LATER_LIFT_FACTOR = 3.0

# Named units: a subtype below this size is merged with a sibling of the same
# theme, and a noun unit takes at most this many attached verbs.
NAMED_SMALL_GROUP = 15
NAMED_VERBS_PER_UNIT = 5
NAMED_ATTACH_MIN_LIFT = 2.0

# More than this share of NULL/sentinel ranks in a core level is suspicious:
# the core should be words with corpus evidence of being common.
CORE_UNRANKED_SHARE_WARNING = 0.5
# A core word rarer than this (or with no corpus evidence) is flagged for
# review: the core should be words a learner meets constantly.
CORE_LOW_FREQUENCY_RANK = 5000

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

LevelBounds = tuple[int, int, int]
SegmentCost = Callable[[Sequence[Sequence[Lemma]], int], float]


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
    #: The rank the packer used: NULL, or no corpus listing at all, reads as
    #: the unranked sentinel (see ``reports.curriculum_bands``).
    effective_rank: int
    old_level: int
    proposed_level: int
    tier_evidence: str
    reason: str


def _balanced_sizes(item_count: int, chunk_count: int) -> list[int]:
    """Return chunk sizes differing by at most one."""
    quotient, remainder = divmod(item_count, chunk_count)
    return [quotient + (index < remainder) for index in range(chunk_count)]


def _tier_evidence(tiers: Sequence[LemmaTier]) -> str:
    return "; ".join(
        f"{tier.source}:{tier.tier_name}"
        for tier in sorted(tiers, key=lambda item: (item.source, item.tier_name))
    )


def _theme_of(pos_type: str, pos_subtype: Optional[str]) -> str:
    """Return the broad curriculum theme for a stored subtype."""
    return THEME_BY_SUBTYPE.get(pos_subtype or pos_type, f"other_{pos_type}")


def _theme(lemma: Lemma) -> str:
    return _theme_of(lemma.pos_type, lemma.pos_subtype)


def _split_run(items: Sequence[Lemma], *, chunk_target: int, chunk_max: int) -> list[list[Lemma]]:
    """Cut an ordered run into balanced chunks no larger than ``chunk_max``."""
    if len(items) <= chunk_max:
        return [list(items)]
    chunk_count = max(math.ceil(len(items) / chunk_target), math.ceil(len(items) / chunk_max))
    runs: list[list[Lemma]] = []
    offset = 0
    for chunk_size in _balanced_sizes(len(items), chunk_count):
        runs.append(list(items[offset : offset + chunk_size]))
        offset += chunk_size
    return runs


def _unit_topic_members(items: Iterable[Lemma]) -> list[Lemma]:
    """The members that define a unit's topic.

    Verbs attached to a noun unit (mix, bake with food) do not change its
    topic, so a unit whose non-verbs are the majority is themed by them alone.
    """
    item_list = list(items)
    content = [lemma for lemma in item_list if lemma.pos_type != "verb"]
    return content if len(content) * 2 >= len(item_list) and content else item_list


def _unit_themes(items: Iterable[Lemma]) -> set[str]:
    return {_theme(lemma) for lemma in _unit_topic_members(items)}


def _unit_subtypes(items: Iterable[Lemma]) -> set[tuple[str, str]]:
    return {subtype_key(lemma) for lemma in _unit_topic_members(items)}


def _pack_numbered(
    runs: Sequence[Sequence[Lemma]],
    levels: Sequence[int],
    bounds: Callable[[int], LevelBounds],
    segment_cost: SegmentCost,
) -> Optional[tuple[float, dict[int, list[Lemma]]]]:
    """Partition ordered runs into exactly ``levels``, each within its bounds.

    Returns the total cost and the packing, or None when no partition fits.
    """
    best: list[dict[int, tuple[float, int]]] = [{0: (0.0, -1)}]
    for level in levels:
        minimum, maximum, target = bounds(level)
        current: dict[int, tuple[float, int]] = {}
        for start_index, (prior_cost, _prior_start) in best[-1].items():
            item_count = 0
            for end_index in range(start_index + 1, len(runs) + 1):
                item_count += len(runs[end_index - 1])
                if item_count > maximum:
                    break
                if item_count < minimum:
                    continue
                cost = prior_cost + segment_cost(runs[start_index:end_index], target)
                existing = current.get(end_index)
                if existing is None or cost < existing[0]:
                    current[end_index] = (cost, start_index)
        best.append(current)
    final = best[-1].get(len(runs))
    if final is None:
        return None

    packed: dict[int, list[Lemma]] = {}
    end_index = len(runs)
    for level_index in range(len(levels), 0, -1):
        start_index = best[level_index][end_index][1]
        packed[levels[level_index - 1]] = [
            lemma for run in runs[start_index:end_index] for lemma in run
        ]
        end_index = start_index
    return final[0], packed


def _core_segment_cost(segment: Sequence[Sequence[Lemma]], target: int) -> float:
    """Size deviation, plus penalties for a level outside 2-3 subtypes."""
    item_count = sum(len(run) for run in segment)
    subtype_count = len({subtype_key(lemma) for run in segment for lemma in run})
    theme_count = len({_theme(run[0]) for run in segment})
    fewest, most = CORE_SUBTYPES_PER_LEVEL
    return (
        abs(item_count - target)
        + 6 * max(0, fewest - subtype_count)
        + 6 * max(0, subtype_count - most)
        + 3 * max(0, theme_count - 1)
    )


def _order_core_runs(content: Sequence[Lemma], evidence: RankEvidence) -> list[list[Lemma]]:
    """Chunk each subtype by commonness and keep the current curriculum order.

    Runs are sequenced by the median current level of their words, so the
    hand-built order of topics survives. Within a subtype the chunks stay in
    commonness order across whatever positions that subtype occupies.
    """
    by_subtype: dict[tuple[str, str], list[Lemma]] = defaultdict(list)
    for lemma in content:
        by_subtype[subtype_key(lemma)].append(lemma)

    chunks: list[tuple[tuple[str, str], int, list[Lemma]]] = []
    for key, items in by_subtype.items():
        items.sort(key=lambda lemma: stable_commonness_key(lemma, evidence))
        split = _split_run(items, chunk_target=CORE_CHUNK_TARGET, chunk_max=CORE_CHUNK_MAX)
        for chunk_index, chunk in enumerate(split):
            chunks.append((key, chunk_index, chunk))

    positions = sorted(
        chunks,
        key=lambda item: (statistics.median(current_level(lemma) for lemma in item[2]), item[0]),
    )
    slots_by_subtype: dict[tuple[str, str], list[int]] = defaultdict(list)
    for position, (key, _chunk_index, _chunk) in enumerate(positions):
        slots_by_subtype[key].append(position)
    ordered: list[list[Lemma]] = [[] for _position in positions]
    for key, slots in slots_by_subtype.items():
        subtype_chunks = sorted(
            (chunk_index, chunk) for chunk_key, chunk_index, chunk in chunks if chunk_key == key
        )
        for slot, (_chunk_index, chunk) in zip(slots, subtype_chunks):
            ordered[slot] = chunk
    return _interleave_subtypes(_spread_subtypes(ordered))


def _spread_subtypes(runs: Sequence[list[Lemma]]) -> list[list[Lemma]]:
    """Space each subtype's chunks evenly from its first one to the core's end.

    A subtype's first (commonest) chunk keeps its place in the current order;
    the rest are spread over what follows, at least :data:`CORE_SPREAD_MIN_GAP`
    chunks apart, so food comes back every few levels instead of filling
    three in a row.
    """
    positions_by_subtype: dict[tuple[str, str], list[int]] = defaultdict(list)
    for position, run in enumerate(runs):
        positions_by_subtype[subtype_key(run[0])].append(position)
    desired: list[float] = [float(position) for position in range(len(runs))]
    for positions in positions_by_subtype.values():
        if len(positions) < 2:
            continue
        first = positions[0]
        gap = max(float(CORE_SPREAD_MIN_GAP), (len(runs) - first) / len(positions))
        for chunk_index, position in enumerate(positions):
            desired[position] = first + chunk_index * gap
    order = sorted(range(len(runs)), key=lambda position: (desired[position], position))
    return [runs[position] for position in order]


def _interleave_subtypes(runs: Sequence[list[Lemma]]) -> list[list[Lemma]]:
    """Pull a nearby different-subtype chunk forward between same-subtype chunks.

    Without this a big subtype (``quality`` has ~100 core adjectives) fills
    several consecutive levels on its own. Only chunks within
    :data:`CORE_INTERLEAVE_WINDOW` positions move, and only earlier.
    """
    remaining = list(runs)
    output: list[list[Lemma]] = []
    while remaining:
        choice = 0
        if output and subtype_key(remaining[0][0]) == subtype_key(output[-1][0]):
            for offset in range(1, min(CORE_INTERLEAVE_WINDOW + 1, len(remaining))):
                if subtype_key(remaining[offset][0]) != subtype_key(output[-1][0]):
                    choice = offset
                    break
        output.append(remaining.pop(choice))
    return output


def _core_level_bounds(level: int) -> LevelBounds:
    """Total-word (minimum, maximum, target) for a core level."""
    return COUNTRY_LEVEL_CAPACITIES.get(
        level, (CORE_RULES.minimum, CORE_RULES.maximum, CORE_RULES.target)
    )


def _core_bounds(
    extra_per_level: float, fixed_level_counts: Mapping[int, int]
) -> Callable[[int], LevelBounds]:
    """Content-word bounds for a core level, leaving room for verbs and grammar.

    The window is wider than the level's own, by :data:`CORE_CONTENT_SLACK`:
    content comes in subtype chunks of ~12, so a tight window has no solution,
    and the function words are apportioned afterwards to even the totals out.
    Words fixed at the level take their room first.
    """

    def bounds(level: int) -> LevelBounds:
        minimum, maximum, target = _core_level_bounds(level)
        taken = extra_per_level + fixed_level_counts.get(level, 0)
        low_slack, high_slack = CORE_CONTENT_SLACK
        return (
            max(1, round(minimum - taken - low_slack)),
            max(1, round(maximum - taken + high_slack)),
            max(1, round(target - taken)),
        )

    return bounds


def _apportion(total: int, weights: Sequence[float]) -> list[int]:
    """Split ``total`` in proportion to ``weights`` (largest remainder)."""
    weight_sum = sum(weights)
    if total <= 0 or not weights:
        return [0] * len(weights)
    if weight_sum <= 0:
        return _balanced_sizes(total, len(weights))
    shares = [total * weight / weight_sum for weight in weights]
    counts = [int(share) for share in shares]
    by_remainder = sorted(
        range(len(weights)), key=lambda index: (-(shares[index] - counts[index]), index)
    )
    for index in by_remainder[: total - sum(counts)]:
        counts[index] += 1
    return counts


def _verb_lift(
    verb: Lemma, subtypes: Iterable[str], affinity: Mapping[str, Mapping[str, float]]
) -> float:
    verb_affinity = affinity.get(verb.lemma_text.casefold(), {})
    return max((verb_affinity.get(subtype, 0.0) for subtype in subtypes), default=0.0)


def _attach_core_verbs(
    verbs: Sequence[Lemma],
    content_levels: Mapping[int, Sequence[Lemma]],
    evidence: RankEvidence,
    affinity: Mapping[str, Mapping[str, float]],
) -> dict[int, list[Lemma]]:
    """Give each core level 1-5 verbs that pair with its subtypes.

    A verb's home is the level most of its current level-mates went to. It
    leaves home only for a clearly better pairing, or to give a verbless level
    a verb.
    """
    levels = sorted(content_levels)
    subtypes_by_level = {
        level: {lemma.pos_subtype or lemma.pos_type for lemma in items}
        for level, items in content_levels.items()
    }
    destinations: dict[int, Counter[int]] = defaultdict(Counter)
    for level, items in content_levels.items():
        for lemma in items:
            destinations[current_level(lemma)][level] += 1

    def home_level(verb: Lemma) -> int:
        if not destinations:
            return levels[0]
        verb_level = current_level(verb)
        nearest = min(destinations, key=lambda old: (abs(old - verb_level), old))
        counts = destinations[nearest]
        return min(counts, key=lambda level: (-counts[level], level))

    def lift(verb: Lemma, level: int) -> float:
        return _verb_lift(verb, subtypes_by_level[level], affinity)

    most_verbs = CORE_VERBS_PER_LEVEL[1]
    placed: dict[int, list[Lemma]] = {level: [] for level in levels}
    for verb in sorted(verbs, key=lambda lemma: stable_commonness_key(lemma, evidence)):
        home = home_level(verb)
        home_lift = max(lift(verb, home), MIN_LIFT)
        with_room = [level for level in levels if len(placed[level]) < most_verbs]
        qualified = [
            level
            for level in with_room
            if level == home
            or lift(verb, level)
            >= home_lift * (EARLIER_LIFT_FACTOR if level < home else LATER_LIFT_FACTOR)
        ]
        if qualified:
            chosen = min(
                qualified, key=lambda level: (-lift(verb, level), abs(level - home), level)
            )
        elif with_room:
            chosen = min(with_room, key=lambda level: (abs(level - home), level > home, level))
        else:
            chosen = home
        placed[chosen].append(verb)

    for level in levels:
        if placed[level]:
            continue
        donors = [
            (verb, donor_level)
            for donor_level in levels
            if len(placed[donor_level]) > 1
            for verb in placed[donor_level]
        ]
        if not donors:
            continue
        verb, donor_level = min(
            donors,
            key=lambda pair: (-lift(pair[0], level), abs(pair[1] - level), pair[0].guid or ""),
        )
        placed[donor_level].remove(verb)
        placed[level].append(verb)
    return placed


def pack_core_levels(
    pool: Sequence[Lemma],
    evidence: RankEvidence,
    affinity: Mapping[str, Mapping[str, float]],
    *,
    fixed_level_counts: Optional[Mapping[int, int]] = None,
) -> dict[int, int]:
    """Assign core lemmas above the preserved levels; returns lemma id -> level.

    ``fixed_level_counts`` are words already pinned to a level above the
    preserved ones (the family tiers). They take room at their level, and the
    packed core always reaches the highest of them.
    """
    if not pool:
        return {}
    fixed = fixed_level_counts or {}
    function_words = sorted(
        (lemma for lemma in pool if is_function_word(lemma)),
        key=lambda lemma: stable_commonness_key(lemma, evidence),
    )
    verbs = [lemma for lemma in pool if lemma.pos_type == "verb" and not is_function_word(lemma)]
    content = [lemma for lemma in pool if lemma.pos_type != "verb" and not is_function_word(lemma)]
    runs = _order_core_runs(content, evidence)

    first_level = PRESERVED_LEVEL_MAX + 1
    available = constants.CORE_DIFFICULTY_LEVEL_MAX - PRESERVED_LEVEL_MAX
    fewest_levels = max([1, *(level - PRESERVED_LEVEL_MAX for level in fixed)])
    best: Optional[tuple[float, dict[int, list[Lemma]]]] = None
    for level_count in range(fewest_levels, available + 1):
        levels = list(range(first_level, first_level + level_count))
        extra_per_level = (len(verbs) + len(function_words)) / level_count
        result = _pack_numbered(
            runs, levels, _core_bounds(extra_per_level, fixed), _core_segment_cost
        )
        if result is not None and (best is None or result[0] < best[0]):
            best = result
    if best is None:
        raise ValueError(
            f"Could not pack {len(pool)} core words into levels "
            f"{first_level}-{constants.CORE_DIFFICULTY_LEVEL_MAX}"
        )
    content_levels = best[1]

    proposed: dict[int, int] = {}
    for level, items in content_levels.items():
        for lemma in items:
            proposed[lemma.id] = level
    placed_verbs = _attach_core_verbs(verbs, content_levels, evidence, affinity)
    for level, level_verbs in placed_verbs.items():
        for verb in level_verbs:
            proposed[verb.id] = level

    # Function words go most-common first, and each level takes enough of them
    # to bring it towards its target size -- at least one where possible.
    levels = sorted(content_levels)
    gaps = [
        max(
            0.0,
            _core_level_bounds(level)[2]
            - len(content_levels[level])
            - len(placed_verbs[level])
            - fixed.get(level, 0),
        )
        + 1.0
        for level in levels
    ]
    offset = 0
    for level, quota in zip(levels, _apportion(len(function_words), gaps)):
        for lemma in function_words[offset : offset + quota]:
            proposed[lemma.id] = level
        offset += quota
    return proposed


def _unit_qualifies(items: Sequence[Lemma]) -> bool:
    """Whether an existing named level is already a well-formed unit."""
    if len(_unit_themes(items)) != 1:
        return False
    single_subtype = len(_unit_subtypes(items)) == 1
    maximum = NAMED_RULES.coherent_maximum if single_subtype else NAMED_RULES.maximum
    return NAMED_RULES.minimum <= len(items) <= maximum


def _group_into_units(
    items: Sequence[Lemma], evidence: RankEvidence
) -> tuple[list[list[Lemma]], list[list[Lemma]]]:
    """Group by subtype; split oversized groups. Returns (units, small groups)."""
    by_subtype: dict[tuple[str, str], list[Lemma]] = defaultdict(list)
    for lemma in items:
        by_subtype[subtype_key(lemma)].append(lemma)
    units: list[list[Lemma]] = []
    small: list[list[Lemma]] = []
    for key in sorted(by_subtype):
        group = sorted(by_subtype[key], key=lambda lemma: stable_commonness_key(lemma, evidence))
        if len(group) < NAMED_SMALL_GROUP:
            small.append(group)
        elif len(group) <= NAMED_RULES.coherent_maximum:
            units.append(group)
        else:
            units.extend(
                _split_run(
                    group,
                    chunk_target=NAMED_RULES.target,
                    chunk_max=NAMED_RULES.maximum,
                )
            )
    return units, small


def _primary_subtype(unit: Sequence[Lemma]) -> str:
    counts = Counter(lemma.pos_subtype or lemma.pos_type for lemma in unit)
    return min(counts, key=lambda subtype: (-counts[subtype], subtype))


def _attach_named_verbs(
    verbs: Sequence[Lemma],
    units: list[list[Lemma]],
    affinity: Mapping[str, Mapping[str, float]],
) -> list[Lemma]:
    """Attach verbs to the noun unit they clearly pair with; return the rest."""
    candidates: list[tuple[float, str, Lemma, int]] = []
    for verb in verbs:
        lifts = [
            (_verb_lift(verb, [_primary_subtype(unit)], affinity), index)
            for index, unit in enumerate(units)
        ]
        best_lift, best_index = max(lifts, default=(0.0, -1), key=lambda pair: (pair[0], -pair[1]))
        if best_lift >= NAMED_ATTACH_MIN_LIFT:
            candidates.append((best_lift, verb.guid or "", verb, best_index))

    attached_ids: set[int] = set()
    verb_counts: Counter[int] = Counter()
    for _lift, _guid, verb, unit_index in sorted(candidates, key=lambda item: (-item[0], item[1])):
        unit = units[unit_index]
        if verb_counts[unit_index] >= NAMED_VERBS_PER_UNIT:
            continue
        if len(unit) >= NAMED_RULES.coherent_maximum:
            continue
        unit.append(verb)
        verb_counts[unit_index] += 1
        attached_ids.add(verb.id)
    return [verb for verb in verbs if verb.id not in attached_ids]


def _merge_small_groups(
    small: Sequence[Sequence[Lemma]],
    units: list[list[Lemma]],
    kept_units: Mapping[int, list[Lemma]],
) -> None:
    """Merge undersized subtype groups within a theme, else into a sibling unit.

    A subtype missing from :data:`THEME_BY_SUBTYPE` falls in ``other_<pos>``,
    so those merge by part of speech: a mixed adjective unit is better than a
    one-word "legal_concept" unit.

    A small group never stands alone if its theme has any sibling unit. When
    no sibling has room, the smallest new sibling takes the group and is
    re-split, which leaves the group in the last (least common) piece --
    beverages end up alongside the rarer foods rather than in a unit of six.
    """
    by_theme: dict[str, list[list[Lemma]]] = defaultdict(list)
    for group in small:
        by_theme[_theme(group[0])].append(list(group))

    for theme, groups in sorted(by_theme.items()):
        merged: list[list[Lemma]] = []
        for group in groups:
            if merged and len(merged[-1]) + len(group) <= NAMED_RULES.maximum:
                merged[-1].extend(group)
            else:
                merged.append(list(group))
        for group in merged:
            if len(group) >= NAMED_SMALL_GROUP:
                units.append(group)
                continue
            new_siblings = [unit for unit in units if _unit_themes(unit) == {theme}]
            kept_siblings = [unit for unit in kept_units.values() if _unit_themes(unit) == {theme}]
            fitting = [
                unit
                for unit in [*new_siblings, *kept_siblings]
                if len(unit) + len(group) <= NAMED_RULES.maximum
            ]
            if fitting:
                min(fitting, key=len).extend(group)
            elif new_siblings:
                sibling = min(new_siblings, key=len)
                units.remove(sibling)
                units.extend(
                    _split_run(
                        [*sibling, *group],
                        chunk_target=NAMED_RULES.target,
                        chunk_max=NAMED_RULES.maximum,
                    )
                )
            elif kept_siblings:
                # A kept unit keeps its number, so it takes the overflow whole.
                min(kept_siblings, key=len).extend(group)
            else:
                units.append(group)


def pack_named_units(
    pool: Sequence[Lemma],
    reserved_levels: set[int],
    evidence: RankEvidence,
    affinity: Mapping[str, Mapping[str, float]],
) -> dict[int, int]:
    """Build one-topic named units and number them; returns lemma id -> level."""
    pinned = {level for level in COUNTRY_LEVEL_CAPACITIES if band_of(level) == "named"}
    by_current: dict[int, list[Lemma]] = defaultdict(list)
    for lemma in pool:
        if band_of(lemma.difficulty_level) == "named":
            by_current[current_level(lemma)].append(lemma)
    kept_units: dict[int, list[Lemma]] = {
        level: list(items)
        for level, items in by_current.items()
        if level in pinned or _unit_qualifies(items)
    }
    kept_ids = {lemma.id for items in kept_units.values() for lemma in items}
    remaining = [lemma for lemma in pool if lemma.id not in kept_ids]

    units, small = _group_into_units(
        [lemma for lemma in remaining if lemma.pos_type != "verb"], evidence
    )
    loose_verbs = _attach_named_verbs(
        sorted(
            (lemma for lemma in remaining if lemma.pos_type == "verb"),
            key=lambda lemma: stable_commonness_key(lemma, evidence),
        ),
        units,
        affinity,
    )
    verb_units, verb_small = _group_into_units(loose_verbs, evidence)
    units.extend(verb_units)
    _merge_small_groups(
        [*small, *verb_small],
        units,
        {level: items for level, items in kept_units.items() if level not in pinned},
    )

    proposed: dict[int, int] = {}
    for level, items in kept_units.items():
        for lemma in items:
            proposed[lemma.id] = level

    # A pinned level only keeps what it has: it is capacity held for the
    # per-language country overrides, not a unit that can absorb more.
    free = {
        number
        for number in range(
            constants.NAMED_DIFFICULTY_LEVEL_MIN, constants.GENERAL_DIFFICULTY_LEVEL_MAX + 1
        )
        if number not in kept_units and number not in reserved_levels and number not in pinned
    }
    number_by_subtype: dict[str, int] = {
        _primary_subtype(items): level for level, items in sorted(kept_units.items())
    }

    def claim(unit: Sequence[Lemma]) -> tuple[int, int, str]:
        counts = Counter(
            current_level(lemma) for lemma in unit if band_of(lemma.difficulty_level) == "named"
        )
        if not counts:
            return (0, 0, min(lemma.guid or "" for lemma in unit))
        level = min(counts, key=lambda number: (-counts[number], number))
        return (-counts[level], level, min(lemma.guid or "" for lemma in unit))

    for unit in sorted(units, key=claim):
        named_levels = [
            current_level(lemma) for lemma in unit if band_of(lemma.difficulty_level) == "named"
        ]
        if named_levels:
            counts = Counter(named_levels)
            preferred = min(counts, key=lambda number: (-counts[number], number))
            target = preferred if preferred in free else int(statistics.median(named_levels))
        else:
            target = number_by_subtype.get(
                _primary_subtype(unit), constants.NAMED_DIFFICULTY_LEVEL_MIN
            )
        if not free:
            raise ValueError("Ran out of named-band level numbers")
        number = min(free, key=lambda candidate: (abs(candidate - target), candidate))
        free.discard(number)
        number_by_subtype.setdefault(_primary_subtype(unit), number)
        for lemma in unit:
            proposed[lemma.id] = number
    return proposed


def _active_lemmas(session: Session) -> list[Lemma]:
    return (
        session.query(Lemma)
        .filter(
            Lemma.guid.isnot(None),
            Lemma.difficulty_level.between(
                constants.MIN_DIFFICULTY_LEVEL,
                constants.GENERAL_DIFFICULTY_LEVEL_MAX,
            ),
        )
        .all()
    )


def reserved_level(lemma: Lemma) -> Optional[int]:
    """The level a lemma is pinned to regardless of packing, if any.

    ``HARDCODED_VERB_LEVELS`` pins only verbs already in the core: be and have
    sit in the named band until their per-language core levels exist.
    """
    family_level = family_reserved_level(lemma)
    if family_level is not None:
        return family_level
    if is_us_state(lemma):
        return US_STATE_COHORT_LEVEL
    if lemma.pos_subtype == "region" and lemma.lemma_text in (COUNTRY_NAMES | CONTINENT_NAMES):
        return COUNTRY_COHORT_LEVEL
    hardcoded = HARDCODED_VERB_LEVELS.get(lemma.lemma_text)
    if (
        hardcoded is not None
        and lemma.pos_type == "verb"
        and band_of(lemma.difficulty_level) == "core"
    ):
        return hardcoded
    return None


def is_alcoholic(lemma: Lemma) -> bool:
    """Whether a beverage is alcoholic, judged from its definition."""
    definition = lemma.definition_text.casefold().replace("non-alcoholic", "")
    return lemma.pos_subtype == "beverage" and any(
        marker in definition for marker in ALCOHOL_MARKERS
    )


def _on_core_learner_list(tiers: Sequence[LemmaTier]) -> bool:
    """Whether a tier puts the word on a beginner list (see CORE_RANK_CEILINGS)."""
    return any(
        tier.source == "cambridge_yle"
        or (
            tier.source == "cefr"
            and TIER_ORDER.get(tier.tier_name, NO_TIER) <= TIER_ORDER[CORE_MAX_CEFR]
        )
        for tier in tiers
    )


def _meets_core_evidence(lemma: Lemma, evidence: RankEvidence, rank_ceiling: int) -> bool:
    return effective_rank(lemma, evidence) < rank_ceiling and _on_core_learner_list(
        evidence.tiers_by_lemma.get(lemma.id, ())
    )


def spill_from_core(
    pool: Sequence[Lemma],
    evidence: RankEvidence,
    fixed_counts: Optional[Mapping[str, int]] = None,
) -> dict[int, str]:
    """Core words that belong in named units, with the reason for each.

    Alcoholic drinks never stay in the core, nor does a word of a
    :data:`CORE_RANK_CEILINGS` subtype without the evidence it asks for.
    Otherwise each content subtype holds at most its :data:`CORE_SUBTYPE_CAPS`
    entry (default :data:`CORE_SUBTYPE_CAP`) across the whole core;
    ``fixed_counts`` are the words of each subtype already in fixed levels
    1-5, which count against the cap but cannot move. The least common of the
    rest leave first.
    """
    spilled: dict[int, str] = {}
    by_subtype: dict[str, list[Lemma]] = defaultdict(list)
    for lemma in pool:
        subtype = lemma.pos_subtype or lemma.pos_type
        rank_ceiling = CORE_RANK_CEILINGS.get(subtype)
        if is_alcoholic(lemma):
            spilled[lemma.id] = "core excludes alcohol"
        elif lemma.pos_type == "verb" or is_function_word(lemma):
            continue
        elif rank_ceiling is not None and not _meets_core_evidence(lemma, evidence, rank_ceiling):
            spilled[lemma.id] = "core evidence floor"
        else:
            by_subtype[subtype].append(lemma)
    for subtype in sorted(by_subtype):
        cap = CORE_SUBTYPE_CAPS.get(subtype, CORE_SUBTYPE_CAP)
        room = max(0, cap - (fixed_counts or {}).get(subtype, 0))
        items = sorted(
            by_subtype[subtype], key=lambda lemma: stable_commonness_key(lemma, evidence)
        )
        for lemma in items[room:]:
            spilled[lemma.id] = "core subtype cap"
    return spilled


def build_assignments(
    session: Session,
    *,
    bands: Sequence[str] = BANDS,
    affinity: Mapping[str, Mapping[str, float]],
) -> tuple[list[Assignment], list[WarningRow]]:
    """Build the GUID-to-level proposal, plus the polysemy cases left alone."""
    lemmas = _active_lemmas(session)
    evidence = load_rank_evidence(session, lemmas)

    proposed = {lemma.id: current_level(lemma) for lemma in lemmas}
    reasons: dict[int, str] = {}
    reserved_ids: set[int] = set()
    for lemma in lemmas:
        reserved = reserved_level(lemma)
        if reserved is None:
            continue
        proposed[lemma.id] = reserved
        reserved_ids.add(lemma.id)
        reasons[lemma.id] = "reserved level"

    leaving: list[Lemma] = []
    polysemy_warnings: list[WarningRow] = []
    if "core" in bands:
        leaving, polysemy_warnings = plan_core_polysemy(
            [lemma for lemma in lemmas if lemma.id not in reserved_ids]
        )
    for lemma in leaving:
        reasons[lemma.id] = "core polysemy"

    if "core" in bands:
        leaving_ids = {lemma.id for lemma in leaving}
        core_pool = [
            lemma
            for lemma in lemmas
            if band_of(lemma.difficulty_level) == "core"
            and current_level(lemma) > PRESERVED_LEVEL_MAX
            and lemma.id not in reserved_ids
            and lemma.id not in leaving_ids
        ]
        pool_ids = {lemma.id for lemma in core_pool}
        # Words that stay in the core without being packed: hand-curated
        # levels 1-5 and reserved levels (family tiers, like at 4).
        fixed_in_core = [
            lemma
            for lemma in lemmas
            if lemma.id not in pool_ids
            and lemma.id not in leaving_ids
            and band_of(proposed[lemma.id]) == "core"
        ]
        spilled = spill_from_core(
            core_pool,
            evidence,
            Counter(lemma.pos_subtype or lemma.pos_type for lemma in fixed_in_core),
        )
        reasons.update(spilled)
        leaving.extend(lemma for lemma in core_pool if lemma.id in spilled)
        proposed.update(
            pack_core_levels(
                [lemma for lemma in core_pool if lemma.id not in spilled],
                evidence,
                affinity,
                fixed_level_counts=Counter(
                    proposed[lemma.id]
                    for lemma in fixed_in_core
                    if proposed[lemma.id] > PRESERVED_LEVEL_MAX
                ),
            )
        )

    if "named" in bands:
        named_pool = [
            lemma
            for lemma in lemmas
            if band_of(lemma.difficulty_level) == "named" and lemma.id not in reserved_ids
        ] + leaving
        reserved_levels = {
            proposed[lemma_id]
            for lemma_id in reserved_ids
            if band_of(proposed[lemma_id]) == "named"
        }
        proposed.update(pack_named_units(named_pool, reserved_levels, evidence, affinity))
    else:
        destinations = named_destinations(lemmas)
        for lemma in leaving:
            destination = destinations.get(subtype_key(lemma))
            if destination is not None:
                proposed[lemma.id] = destination

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
            effective_rank=effective_rank(lemma, evidence),
            old_level=current_level(lemma),
            proposed_level=proposed[lemma.id],
            tier_evidence=_tier_evidence(evidence.tiers_by_lemma.get(lemma.id, [])),
            reason=(
                ""
                if proposed[lemma.id] == current_level(lemma)
                else reasons.get(lemma.id, f"{band_of(proposed[lemma.id])} rebalance")
            ),
        )
        for lemma in lemmas
    ]
    return sorted(assignments, key=lambda item: (item.proposed_level, item.guid)), polysemy_warnings


def _is_unranked(assignment: Assignment) -> bool:
    return assignment.effective_rank >= UNRANKED_SENTINEL


def _structural_warnings(assignments: Sequence[Assignment]) -> list[WarningRow]:
    """Band-aware level shape warnings."""
    warnings: list[WarningRow] = []
    by_level: dict[int, list[Assignment]] = defaultdict(list)
    for assignment in assignments:
        by_level[assignment.proposed_level].append(assignment)

    for level, items in sorted(by_level.items()):
        guids = ";".join(item.guid for item in items)
        verbs = [item for item in items if item.pos_type == "verb"]
        band = band_of(level)
        if band == "core":
            if level == constants.MIN_DIFFICULTY_LEVEL and verbs:
                warnings.append(
                    WarningRow("core-verb-count", f"level {level}", guids, "level 1 has verbs")
                )
            for item in items:
                # English frequency says nothing about family terms: "older
                # brother" is rare in English and basic in Chinese, and the
                # family overrides already decide which languages get it.
                if (
                    item.effective_rank > CORE_LOW_FREQUENCY_RANK
                    and item.pos_subtype != "family_relation"
                ):
                    warnings.append(
                        WarningRow(
                            "core-low-frequency",
                            item.lemma_text,
                            item.guid,
                            f"level {level}, rank "
                            + ("unranked" if _is_unranked(item) else f"{item.effective_rank}")
                            + f" ({item.pos_type}/{item.pos_subtype})",
                        )
                    )
            if level <= PRESERVED_LEVEL_MAX:
                continue
            minimum, maximum, _target = COUNTRY_LEVEL_CAPACITIES.get(
                level, (CORE_RULES.minimum, CORE_RULES.maximum, CORE_RULES.target)
            )
            if not minimum <= len(items) <= maximum:
                warnings.append(
                    WarningRow(
                        "level-size",
                        f"level {level}",
                        guids,
                        f"{len(items)} senses; core target is {minimum}-{maximum}",
                    )
                )
            content_subtypes = {
                (item.pos_type, item.pos_subtype or item.pos_type)
                for item in items
                if item.pos_type != "verb" and not is_function_pos(item.pos_type, item.pos_subtype)
            }
            fewest, most = CORE_SUBTYPES_PER_LEVEL
            if not fewest <= len(content_subtypes) <= most:
                warnings.append(
                    WarningRow(
                        "core-subtype-count",
                        f"level {level}",
                        guids,
                        f"{len(content_subtypes)} content subtypes; target is {fewest}-{most}",
                    )
                )
            fewest_verbs, most_verbs = CORE_VERBS_PER_LEVEL
            if not fewest_verbs <= len(verbs) <= most_verbs:
                warnings.append(
                    WarningRow(
                        "core-verb-count",
                        f"level {level}",
                        guids,
                        f"{len(verbs)} verbs; target is {fewest_verbs}-{most_verbs}",
                    )
                )
            unranked = [item for item in items if _is_unranked(item)]
            if len(unranked) > CORE_UNRANKED_SHARE_WARNING * len(items):
                warnings.append(
                    WarningRow(
                        "unranked-share",
                        f"level {level}",
                        ";".join(item.guid for item in unranked),
                        f"{len(unranked)} of {len(items)} senses have no corpus rank",
                    )
                )
        elif band == "named":
            if level in (US_STATE_COHORT_LEVEL, COUNTRY_COHORT_LEVEL):
                continue
            if level in COUNTRY_LEVEL_CAPACITIES:
                continue
            content = [item for item in items if item.pos_type != "verb"] or items
            subtypes = {(item.pos_type, item.pos_subtype or item.pos_type) for item in content}
            themes = {_theme_of(item.pos_type, item.pos_subtype) for item in content}
            maximum = NAMED_RULES.coherent_maximum if len(subtypes) == 1 else NAMED_RULES.maximum
            if not NAMED_RULES.minimum <= len(items) <= maximum:
                warnings.append(
                    WarningRow(
                        "level-size",
                        f"level {level}",
                        guids,
                        f"{len(items)} senses; named target is {NAMED_RULES.minimum}-{maximum}",
                    )
                )
            if len(themes) > 1:
                warnings.append(
                    WarningRow(
                        "named-multi-theme",
                        f"level {level}",
                        guids,
                        "themes: " + ", ".join(sorted(themes)),
                    )
                )

    for assignment in assignments:
        hardcoded = HARDCODED_VERB_LEVELS.get(assignment.lemma_text)
        if (
            hardcoded is not None
            and assignment.pos_type == "verb"
            and assignment.proposed_level != hardcoded
        ):
            warnings.append(
                WarningRow(
                    "hardcoded-verb-level",
                    assignment.lemma_text,
                    assignment.guid,
                    f"at level {assignment.proposed_level}; HARDCODED_VERB_LEVELS says "
                    f"{hardcoded} (per-language core levels not implemented yet)",
                )
            )
    return warnings


def build_warnings(
    session: Session,
    assignments: Sequence[Assignment],
    extra_warnings: Sequence[WarningRow] = (),
) -> list[WarningRow]:
    """Build sense, definition, lemma/form, and level-shape review warnings."""
    warnings: list[WarningRow] = list(extra_warnings)
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
        owner = assignment_by_id.get(derivative_form.lemma_id)
        if owner is None or (
            derivative_form.derivative_form_text.casefold() == owner.lemma_text.casefold()
        ):
            continue
        matching_guids = [
            item.guid
            for item in active_text_to_assignments.get(
                derivative_form.derivative_form_text.casefold(), []
            )
            if item.lemma_id != derivative_form.lemma_id and item.pos_type == owner.pos_type
        ]
        if not matching_guids:
            continue
        warning_key = (derivative_form.derivative_form_text.casefold(), derivative_form.lemma_id)
        if warning_key in seen_inflections:
            continue
        seen_inflections.add(warning_key)
        warnings.append(
            WarningRow(
                "inflection-as-lemma",
                derivative_form.derivative_form_text,
                ";".join(sorted(matching_guids)),
                f"also an English {derivative_form.grammatical_form} form of {owner.lemma_text} ({owner.guid})",
            )
        )

    warnings.extend(_structural_warnings(assignments))
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


def _level_table(
    title: str,
    levels: Sequence[int],
    by_old: Mapping[int, Sequence[Assignment]],
    by_proposed: Mapping[int, Sequence[Assignment]],
) -> list[str]:
    lines = [
        "",
        f"## {title}",
        "",
        "| Level | Before | After | Unranked | Moved in | Verbs | Leading subtypes |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for level in levels:
        after = by_proposed.get(level, [])
        moved_in = sum(1 for item in after if item.old_level != level)
        unranked = sum(1 for item in after if _is_unranked(item))
        verbs = sum(1 for item in after if item.pos_type == "verb")
        lines.append(
            f"| {level} | {len(by_old.get(level, []))} | {len(after)} | {unranked} "
            f"| {moved_in} | {verbs} | {_themes(after)} |"
        )
    return lines


def write_report(
    session: Session,
    assignments: Sequence[Assignment],
    warnings: Sequence[WarningRow],
    output_dir: Path,
) -> None:
    """Write all review artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    assignment_fields = list(Assignment.__dataclass_fields__)
    with (output_dir / "assignments.csv").open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=assignment_fields)
        writer.writeheader()
        for assignment in assignments:
            writer.writerow(assignment.__dict__)

    mapping_payload = {
        "format": "greenland-curriculum-relevel-v2",
        "supported_level_max": constants.GENERAL_DIFFICULTY_LEVEL_MAX,
        "assignments": [
            {
                "guid": item.guid,
                "old_level": item.old_level,
                "proposed_level": item.proposed_level,
            }
            for item in assignments
            if item.old_level != item.proposed_level
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

    moves = [item for item in assignments if item.old_level != item.proposed_level]
    move_reasons = Counter(item.reason for item in moves)
    lines = [
        "# Vocabulary curriculum rebalance proposal",
        "",
        "Levels 1–5 are fixed. Core levels from 6 hold 2–3 content subtypes, 1–5 verbs "
        "and a few function words; named units hold one topic. The topic band (1000+) "
        "is not touched. `Unranked` counts senses with no corpus rank (NULL or the "
        "9783 sentinel), which sort as uncommon.",
        "",
        f"- Active mapped senses: {len(assignments)}",
        f"- Planned moves: {len(moves)}",
    ]
    lines.extend(f"  - {reason}: {count}" for reason, count in sorted(move_reasons.items()))
    lines.append(f"- Review warnings: {len(warnings)}")

    all_levels = sorted(set(by_old) | set(by_proposed))
    lines.extend(
        _level_table(
            "Core levels",
            [level for level in all_levels if band_of(level) == "core"],
            by_old,
            by_proposed,
        )
    )
    lines.extend(
        _level_table(
            "Named units",
            [level for level in all_levels if band_of(level) == "named"],
            by_old,
            by_proposed,
        )
    )
    warning_counts = Counter(warning.category for warning in warnings)
    lines.extend(["", "## Warning summary", ""])
    for category, count in sorted(warning_counts.items()):
        lines.append(f"- {category}: {count}")
    lines.extend(
        [
            "",
            "See `assignments.csv` for definitions and evidence, `warnings.csv` for review items, "
            "`effective-language-counts.csv` for the simulated post-script distribution, "
            "`mapping.json` for the moves, and `diff levels-before.txt levels-after.txt` "
            "for the words at each level.",
            "",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    ambiguous = ambiguous_headwords(session)
    for file_name, use_proposed in (("levels-before.txt", False), ("levels-after.txt", True)):
        level_words = [
            LevelWord(
                level=item.proposed_level if use_proposed else item.old_level,
                pos_type=item.pos_type,
                pos_subtype=item.pos_subtype,
                lemma_text=item.lemma_text,
                disambiguation=item.disambiguation,
                guid=item.guid,
            )
            for item in assignments
        ]
        (output_dir / file_name).write_text(
            format_level_words(level_words, ambiguous=ambiguous), encoding="utf-8"
        )


def main() -> None:
    """Write the rebalance proposal, and optionally back up and apply it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=Path(constants.WORDFREQ_DB_PATH))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--bands",
        default=",".join(BANDS),
        help="Comma-separated bands to rebalance (default: core,named)",
    )
    parser.add_argument(
        "--cooccurrence",
        type=Path,
        default=DEFAULT_COOCCURRENCE,
        help="Verb/subtype co-occurrence artifact (build_cooccurrence.py)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Back up the database and write the proposed levels",
    )
    args = parser.parse_args()
    bands = [band.strip() for band in args.bands.split(",") if band.strip()]
    unknown = sorted(set(bands) - set(BANDS))
    if unknown:
        parser.error(f"Unknown band(s): {', '.join(unknown)}")
    if not args.cooccurrence.exists():
        parser.error(
            f"{args.cooccurrence} not found. Build it first with "
            "src/wordfreq/corpora/build_cooccurrence.py"
        )
    affinity = load_verb_affinity(args.cooccurrence)

    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=str(args.db_path))
    session = create_session(config)
    try:
        assignments, polysemy_warnings = build_assignments(session, bands=bands, affinity=affinity)
        warnings = build_warnings(session, assignments, polysemy_warnings)
        write_report(session, assignments, warnings, args.output_dir)
        moves = [
            PlannedMove(
                lemma_id=item.lemma_id,
                guid=item.guid,
                old_level=item.old_level,
                new_level=item.proposed_level,
                reason=item.reason,
            )
            for item in assignments
            if item.old_level != item.proposed_level
        ]
        print(
            f"Wrote proposal for {len(assignments)} active senses "
            f"({len(moves)} moves) to {args.output_dir}"
        )
        if not args.apply or not moves:
            return
        backup_path = backup_database(args.db_path, "relevel")
        print(f"Created backup {backup_path}")
        apply_moves(session, moves, source=SOURCE)
        session.commit()
        print(f"Applied {len(moves)} moves")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
