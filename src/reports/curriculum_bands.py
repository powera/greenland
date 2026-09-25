"""Shared rules for rebalancing the vocabulary curriculum.

Two policies run through everything here, and both exist because the earlier
packer got them wrong:

**Missing data means uncommon.** A lemma with no ``frequency_rank``, or one
no corpus lists at all, sorts as :data:`UNRANKED_SENTINEL` -- never ahead of a
word with corpus evidence. The second case matters because the stored rank of
a word below every corpus cap comes from its tiers alone (vodka and anesthetic
both sit at 3758 from Basic English "extended"). Tier evidence (CEFR, Cambridge
YLE, Basic English) only breaks ties between equal ranks. The old packer sorted
on tier *first*, so a YLE-listed word with no wordfreq data jumped ahead of
every corpus-ranked word.

**Hysteresis.** When the evidence does not clearly favour a change, the
current level wins. :func:`stable_commonness_key` only lets a word jump ahead
of another if its rank is in a better power-of-two bucket (roughly twice as
frequent); inside a bucket the current curriculum order stands.
"""

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Mapping, Optional, Sequence

from sqlalchemy.orm import Session

import constants
from storage.crud.operation_log import FieldChange, log_field_changes
from storage.models.schema import Lemma, LemmaTier
from wordfreq.data.family_relations_sections import ALL_SECTIONS
from wordfreq.frequency.combined_rank import lemmas_without_corpus_evidence

# The rank the combined-rank rollup assigns a lemma no corpus lists. It is a
# harmonic mean of per-corpus unknown ranks, not a configured constant, so it
# only moves if the corpus set or their caps change.
UNRANKED_SENTINEL = 9783

PROMINENCE_ORDER: Mapping[Optional[str], int] = {
    "very_common": 0,
    "common": 1,
    None: 1,
    "uncommon": 2,
    "rare": 3,
}

TIER_ORDER: Mapping[str, int] = {
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
NO_TIER = 99

# Levels 1-5 are hand-curated and never repacked.
PRESERVED_LEVEL_MAX = 5

# Grammar words: taught a few per level through the core rather than as a block.
FUNCTION_POS_TYPES = frozenset(
    {"pronoun", "conjunction", "preposition", "determiner", "interjection"}
)
FUNCTION_SUBTYPES = frozenset({"adverb_other"})

# Where the two big name cohorts sit after the band renumbering (migration
# 20260919). Each is one coherent unit, larger than an ordinary level.
US_STATE_COHORT_LEVEL = 240
COUNTRY_COHORT_LEVEL = 245

# Country lemmas stay together at their base cohort, then move per language
# into these levels through LemmaDifficultyOverride. The base level keeps only
# (minimum, maximum, target) general words so the effective per-language size
# stays reasonable once the countries arrive.
COUNTRY_LEVEL_CAPACITIES: Mapping[int, tuple[int, int, int]] = {
    10: (25, 40, 30),
    18: (23, 38, 28),
    145: (0, 15, 5),
}

FAMILY_LEVEL_BY_TEXT: Mapping[str, int] = {
    variant.lemma_text.casefold(): variant.curriculum_level
    for section in ALL_SECTIONS
    for variant in section.variants
    if variant.curriculum_level is not None
}


@dataclass(frozen=True)
class BandRules:
    """Word-count bounds for one level in a band."""

    minimum: int
    target: int
    maximum: int
    #: Upper bound for a unit that is a single subtype or cohort (all US
    #: states, say): keeping it whole beats splitting it into two thin units.
    coherent_maximum: int


CORE_RULES = BandRules(minimum=30, target=35, maximum=40, coherent_maximum=40)
NAMED_RULES = BandRules(minimum=30, target=35, maximum=40, coherent_maximum=55)


@dataclass(frozen=True)
class PlannedMove:
    """One proposed level edit and its reason."""

    lemma_id: int
    guid: str
    old_level: int
    new_level: int
    reason: str


@dataclass(frozen=True)
class WarningRow:
    """One curriculum review warning."""

    category: str
    headword: str
    guids: str
    details: str


def band_of(level: Optional[int]) -> str:
    """Name the curriculum band a stored level falls in."""
    if level is None:
        return "unlevelled"
    if level == constants.EXCLUDE_DIFFICULTY_LEVEL:
        return "excluded"
    if constants.MIN_DIFFICULTY_LEVEL <= level <= constants.CORE_DIFFICULTY_LEVEL_MAX:
        return "core"
    if constants.NAMED_DIFFICULTY_LEVEL_MIN <= level <= constants.GENERAL_DIFFICULTY_LEVEL_MAX:
        return "named"
    if constants.TOPIC_DIFFICULTY_LEVEL_MIN <= level <= constants.MAX_DIFFICULTY_LEVEL:
        return "topic"
    return "gap"


def current_level(lemma: Lemma) -> int:
    """The lemma's stored level, with NULL read as 0."""
    return int(lemma.difficulty_level or 0)


def subtype_key(lemma: Lemma) -> tuple[str, str]:
    """The (pos_type, subtype) pair a unit is built around."""
    return (lemma.pos_type, lemma.pos_subtype or lemma.pos_type)


def is_function_pos(pos_type: str, pos_subtype: Optional[str]) -> bool:
    """Whether a POS pair marks a grammar word rather than content vocabulary."""
    return pos_type in FUNCTION_POS_TYPES or pos_subtype in FUNCTION_SUBTYPES


def is_function_word(lemma: Lemma) -> bool:
    """Whether the lemma is a grammar word rather than content vocabulary."""
    return is_function_pos(lemma.pos_type, lemma.pos_subtype)


@dataclass(frozen=True)
class RankEvidence:
    """What the ordering keys know about each lemma beyond its stored rank."""

    tiers_by_lemma: Mapping[int, Sequence[LemmaTier]] = field(default_factory=dict)
    #: Lemmas no corpus lists: their stored rank is tier-derived and is read
    #: as unranked. Empty means every stored rank is trusted.
    no_corpus_ids: frozenset[int] = frozenset()


def load_rank_evidence(session: Session, lemmas: Sequence[Lemma]) -> RankEvidence:
    """Tier rows and corpus coverage for ``lemmas``."""
    tiers_by_lemma: dict[int, list[LemmaTier]] = defaultdict(list)
    for tier_row in session.query(LemmaTier).all():
        tiers_by_lemma[tier_row.lemma_id].append(tier_row)
    return RankEvidence(
        tiers_by_lemma=tiers_by_lemma,
        no_corpus_ids=frozenset(
            lemmas_without_corpus_evidence(session, [lemma.id for lemma in lemmas])
        ),
    )


def effective_rank(lemma: Lemma, evidence: RankEvidence) -> int:
    """The lemma's rank for ordering, reading missing corpus data as unranked."""
    if lemma.frequency_rank is None:
        return UNRANKED_SENTINEL
    if lemma.id in evidence.no_corpus_ids:
        return max(int(lemma.frequency_rank), UNRANKED_SENTINEL)
    return int(lemma.frequency_rank)


def rank_bucket(rank: int) -> int:
    """Power-of-two bucket: a word must be ~2x as frequent to change bucket."""
    return int(math.log2(max(rank, 1)))


def best_tier_rank(tiers: Sequence[LemmaTier]) -> int:
    """The most elementary tier the lemma is listed in, or :data:`NO_TIER`."""
    return min((TIER_ORDER.get(tier.tier_name, NO_TIER) for tier in tiers), default=NO_TIER)


def commonness_key(lemma: Lemma, evidence: RankEvidence) -> tuple[int, int, int, int, str, str]:
    """Order lemmas most-common first; tiers only break rank ties."""
    return (
        effective_rank(lemma, evidence),
        best_tier_rank(evidence.tiers_by_lemma.get(lemma.id, ())),
        PROMINENCE_ORDER.get(lemma.sense_prominence, 1),
        current_level(lemma),
        lemma.lemma_text.casefold(),
        lemma.guid or "",
    )


def stable_commonness_key(
    lemma: Lemma, evidence: RankEvidence
) -> tuple[int, int, int, int, int, str, str]:
    """Like :func:`commonness_key`, but the current level wins inside a rank bucket."""
    rank = effective_rank(lemma, evidence)
    return (
        rank_bucket(rank),
        current_level(lemma),
        rank,
        best_tier_rank(evidence.tiers_by_lemma.get(lemma.id, ())),
        PROMINENCE_ORDER.get(lemma.sense_prominence, 1),
        lemma.lemma_text.casefold(),
        lemma.guid or "",
    )


def family_reserved_level(lemma: Lemma) -> Optional[int]:
    """Return the family generator's level for a matching live sense."""
    if lemma.pos_subtype != "family_relation":
        return None
    lemma_text = lemma.lemma_text.casefold()
    if lemma_text == "cousin":
        disambiguation = (lemma.disambiguation or "").casefold()
        if "male" in disambiguation:
            lemma_text = "male cousin"
        elif "female" in disambiguation:
            lemma_text = "female cousin"
    return FAMILY_LEVEL_BY_TEXT.get(lemma_text)


def is_us_state(lemma: Lemma) -> bool:
    """Whether the lemma is one of the US states cohort."""
    return lemma.pos_subtype == "region" and "state of the united states" in (
        lemma.definition_text.casefold()
    )


def load_verb_affinity(path: Path) -> dict[str, dict[str, float]]:
    """Read ``verb -> subtype -> lift`` from the co-occurrence artifact.

    The artifact is built by ``wordfreq/corpora/build_cooccurrence.py``; see
    ``wordfreq.corpora.cooccurrence`` for why lift rather than raw counts.
    """
    artifact = json.loads(path.read_text(encoding="utf-8"))
    return {
        verb: {entry["subtype"]: float(entry["lift"]) for entry in payload["subtypes"]}
        for verb, payload in artifact["verbs"].items()
    }


def backup_database(database_path: Path, label: str) -> Path:
    """Create a WAL-consistent dated SQLite backup before applying changes."""
    backup_path = database_path.with_name(f"{database_path.name}.bak-{date.today():%Y%m%d}-{label}")
    if backup_path.exists():
        raise FileExistsError(f"Refusing to replace existing backup: {backup_path}")
    with sqlite3.connect(database_path) as source_connection:
        with sqlite3.connect(backup_path) as backup_connection:
            source_connection.backup(backup_connection)
    return backup_path


def apply_moves(session: Session, moves: Sequence[PlannedMove], *, source: str) -> None:
    """Write planned level moves, refusing any lemma edited since the preview."""
    lemmas_by_id = {
        lemma.id: lemma
        for lemma in session.query(Lemma).filter(Lemma.id.in_([move.lemma_id for move in moves]))
    }
    for move in moves:
        lemma = lemmas_by_id[move.lemma_id]
        if lemma.guid != move.guid or lemma.difficulty_level != move.old_level:
            raise RuntimeError(f"Lemma changed after preview: {move.guid}")
        lemma.difficulty_level = move.new_level
        log_field_changes(
            session,
            source=source,
            operation_type="lemma_update",
            entity_guid=move.guid,
            changes=[FieldChange("difficulty_level", move.old_level, move.new_level)],
            extra={"reason": move.reason},
            lemma_id=move.lemma_id,
        )
