#!/usr/bin/env python3
"""LLM placement of a new word into a curriculum level.

``reports.level_candidates`` ranks levels by rule (subtype, theme, rank) and
``wordfreq.frequency.level_profile.suggest_levels`` by corpus lean; neither
reads the word's definition or a level's title, so neither can tell "bat" the
animal from "bat" the club, or "Events and Processes" from its third volume.
This module asks a model, giving it both:

* **Every level title**, in the system context.  About 200 titles are a couple
  of thousand tokens, identical for every word, so the provider caches them;
  a first pass over a shortlist with a "none of these" retry over the full
  list would cost a second call to save tokens that are already cheap.
* **A shortlist** from the two rankers, in the per-word prompt.  Shortlisted
  levels carry what a title cannot: why the data picked them, how full they
  are, and sample words.  The model may still choose any listed level.

The model may also answer "none fit"; such a word is parked (``level`` None)
until a unit exists for it, rather than forced into the nearest title.

Levels 1-5 (hand-curated), fixed sets (``wordfreq.data.cohorts``) and levels
with no ``curriculum_levels`` title are not offered.  Nothing is written.

    GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/words/level_placement.py \\
        --pending --limit 5 --dry-run
    PYTHONPATH=src python src/words/level_placement.py --lemma-guid N14_001 \\
        --profiles-json /tmp/level_profiles.json
"""

import argparse
import csv
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

import constants
import util.prompt_loader
from clients.unified_client import UnifiedLLMClient
from reports.curriculum_bands import PRESERVED_LEVEL_MAX, band_of
from reports.level_candidates import (
    LevelIndex,
    PlacementQuery,
    core_evidence,
    level_candidates,
    load_level_index,
    query_for_lemma,
    query_for_pending,
)
from storage.backend import BackendType, DataSourceConfig, create_session
from storage.crud.curriculum_level import list_curriculum_levels
from storage.models.imports import TARGET_KIND_LEMMA, PendingImport
from storage.models.schema import Lemma
from wordfreq.data.cohorts import COHORT_LEVELS
from wordfreq.frequency.corpus import get_enabled_corpus_names
from wordfreq.frequency.level_profile import (
    GENERAL,
    LevelProfile,
    build_level_profiles,
    get_corpus_zipf_floors,
    load_level_profiles,
    measure_token_weights,
    profile_lemma,
    suggest_levels,
)
from words.level_naming import level_words

logger = logging.getLogger(__name__)

#: Candidates taken from each ranker before merging.
RULE_CANDIDATES = 4
CORPUS_CANDIDATES = 4
#: Most levels in the merged shortlist.
MAX_SHORTLIST = 6
#: Sample words shown per shortlisted level.
SAMPLE_WORDS = 12
#: A corpus match weaker than this many times the average level is not
#: evidence of anything.
MIN_CORPUS_LIFT = 1.5
#: Corpora shown in the word's own lean.
MAX_LEAN_CORPORA = 3

FIT_VALUES = ("good", "acceptable", "none")

PLACEMENT_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "fit": {"type": "string", "enum": list(FIT_VALUES)},
        "level": {"type": "integer"},
        "alternatives": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["reasoning", "fit", "level", "alternatives"],
}


@dataclass(frozen=True)
class MenuLevel:
    """One level the model may choose."""

    level: int
    name: str
    cefr: Optional[str] = None


@dataclass(frozen=True)
class ShortlistEntry:
    """A level the data suggests, with what the prompt says about it."""

    level: int
    reasons: tuple[str, ...]
    level_size: Optional[int] = None
    capacity: Optional[int] = None
    sample_words: tuple[str, ...] = ()

    @property
    def full(self) -> bool:
        return (
            self.level_size is not None
            and self.capacity is not None
            and self.level_size >= self.capacity
        )


@dataclass(frozen=True)
class PlacementSuggestion:
    """The model's answer, checked against the menu."""

    #: None when nothing fits, or the answer was unusable (see ``problems``).
    level: Optional[int]
    fit: str
    alternatives: tuple[int, ...]
    reasoning: str
    #: Levels that were shortlisted, in shortlist order.
    shortlist: tuple[int, ...]
    #: Why part of the answer was discarded; empty when it was used whole.
    problems: tuple[str, ...] = ()

    @property
    def from_shortlist(self) -> bool:
        return self.level is not None and self.level in self.shortlist


# -- Pure prompt building ---------------------------------------------------


def offered(level: int) -> bool:
    """Whether a new word may be placed at ``level`` at all."""
    return (
        band_of(level) in ("core", "named", "topic")
        and level > PRESERVED_LEVEL_MAX
        and level not in COHORT_LEVELS
    )


def menu_from_rows(rows: Sequence[Any]) -> List[MenuLevel]:
    """Menu entries for the offered levels among ``curriculum_levels`` rows."""
    return [
        MenuLevel(int(row.level), str(row.name), row.cefr)
        for row in rows
        if offered(int(row.level)) and row.name
    ]


def format_menu(menu: Sequence[MenuLevel]) -> str:
    """The full level list, grouped by band."""
    headings = {
        "core": "Core (taught in order):",
        "named": "Named units:",
        "topic": "Topic units (specialist, opt-in):",
    }
    lines: List[str] = []
    current: Optional[str] = None
    for item in sorted(menu, key=lambda entry: entry.level):
        band = band_of(item.level)
        if band != current:
            if lines:
                lines.append("")
            lines.append(headings[band])
            current = band
        lines.append(f"{item.level} | {item.name} | {item.cefr or '?'}")
    return "\n".join(lines)


def build_context(menu: Sequence[MenuLevel]) -> str:
    """The system context: instructions and every level title, the same for every word."""
    template = util.prompt_loader.get_context("curriculum", "level_placement")
    return template.replace("{{level_menu}}", format_menu(menu))


def describe_lean(weights: Optional[Mapping[str, float]]) -> str:
    """The word's corpus lean, in one line."""
    if not weights:
        return "Corpus lean: no corpus data"
    topical = sorted(
        ((name, weight) for name, weight in weights.items() if name != GENERAL and weight > 0),
        key=lambda pair: (-pair[1], pair[0]),
    )
    if not topical:
        return "Corpus lean: none (even across corpora; general vocabulary)"
    shown = ", ".join(f"{name} {weight:.0%}" for name, weight in topical[:MAX_LEAN_CORPORA])
    return f"Corpus lean (of this spelling): {shown}"


def describe_evidence(query: PlacementQuery, weights: Optional[Mapping[str, float]]) -> str:
    """Rank, learner lists, tags and corpus lean, one per line."""
    lines = [f"Frequency rank: {query.rank}"]
    if query.tiers:
        lines.append("Learner lists: " + ", ".join(f"{src} {tier}" for src, tier in query.tiers))
    if query.tags:
        lines.append("Tags: " + ", ".join(query.tags))
    lines.append(describe_lean(weights))
    return "\n".join(lines)


def format_shortlist(shortlist: Sequence[ShortlistEntry], menu: Sequence[MenuLevel]) -> str:
    """The shortlist block of the prompt."""
    if not shortlist:
        return "(none - the data has no suggestion; choose from the full list)"
    names = {item.level: item for item in menu}
    blocks: List[str] = []
    for entry in shortlist:
        item = names.get(entry.level)
        title = f"{item.name} | {item.cefr or '?'}" if item else "(untitled)"
        head = f"{entry.level} | {title}"
        if entry.level_size is not None and entry.capacity is not None:
            head += f" | {entry.level_size}/{entry.capacity} words"
            if entry.full:
                head += " (full)"
        lines = [head, *(f"  - {reason}" for reason in entry.reasons)]
        if entry.sample_words:
            lines.append("  words: " + ", ".join(entry.sample_words))
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def build_prompt(
    query: PlacementQuery,
    shortlist: Sequence[ShortlistEntry],
    menu: Sequence[MenuLevel],
    weights: Optional[Mapping[str, float]],
    core_block: Optional[str],
) -> str:
    """The per-word prompt; the level list is in :func:`build_context`."""
    pos = query.pos_type + (f" / {query.pos_subtype}" if query.pos_subtype else "")
    core_status = "open" if core_block is None else f"closed ({core_block})"
    template = util.prompt_loader.get_prompt("curriculum", "level_placement")
    replacements = {
        "{{word}}": query.lemma_text,
        "{{pos}}": pos,
        "{{definition}}": query.definition or "(none)",
        "{{evidence}}": describe_evidence(query, weights),
        "{{core_status}}": core_status,
        "{{shortlist}}": format_shortlist(shortlist, menu),
    }
    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)
    return template


def merge_shortlist(
    rule_reasons: Sequence[tuple[int, str]],
    corpus_reasons: Sequence[tuple[int, str]],
    menu_levels: Sequence[int],
    limit: int = MAX_SHORTLIST,
) -> List[tuple[int, tuple[str, ...]]]:
    """Interleave the two rankers' levels, best first, joining reasons for a shared level.

    Interleaving rather than concatenating keeps a strong corpus match from
    being cut by four weak subtype ones.  Levels not on the menu are dropped.
    """
    allowed = set(menu_levels)
    reasons: Dict[int, List[str]] = {}
    order: List[int] = []
    for position in range(max(len(rule_reasons), len(corpus_reasons))):
        for source in (rule_reasons, corpus_reasons):
            if position >= len(source):
                continue
            level, reason = source[position]
            if level not in allowed:
                continue
            if level not in reasons:
                reasons[level] = []
                order.append(level)
            reasons[level].append(reason)
    return [(level, tuple(reasons[level])) for level in order[:limit]]


def parse_placement(
    payload: Mapping[str, Any],
    menu_levels: Sequence[int],
    shortlist: Sequence[int],
    core_block: Optional[str],
) -> PlacementSuggestion:
    """Check the model's answer against what it was allowed to choose.

    A level off the menu, or in a closed core, is discarded (the word parks)
    rather than trusted: either means the model ignored the instructions.
    """
    allowed = set(menu_levels)
    problems: List[str] = []

    def usable(value: Any, label: str) -> Optional[int]:
        try:
            level = int(value)
        except (TypeError, ValueError):
            problems.append(f"{label} {value!r} is not a level number")
            return None
        if level not in allowed:
            problems.append(f"{label} {level} is not an offered level")
            return None
        if core_block is not None and band_of(level) == "core":
            problems.append(f"{label} {level} is in the closed core")
            return None
        return level

    fit = str(payload.get("fit") or "").strip()
    if fit not in FIT_VALUES:
        problems.append(f"fit {fit!r} is not one of {', '.join(FIT_VALUES)}")
        fit = "none"
    level = usable(payload.get("level"), "level") if fit != "none" else None
    if level is None:
        fit = "none"

    alternatives: List[int] = []
    for value in payload.get("alternatives") or []:
        alternative = usable(value, "alternative")
        if alternative is not None and alternative != level and alternative not in alternatives:
            alternatives.append(alternative)

    return PlacementSuggestion(
        level=level,
        fit=fit,
        alternatives=tuple(alternatives),
        reasoning=str(payload.get("reasoning") or "").strip(),
        shortlist=tuple(shortlist),
        problems=tuple(problems),
    )


# -- Database and LLM -------------------------------------------------------


class LevelPlacer:
    """Holds the per-run state (level index, corpus profiles, menu) and places words."""

    def __init__(
        self,
        session: Session,
        level_profiles: Mapping[int, LevelProfile],
        client: Optional[UnifiedLLMClient] = None,
    ) -> None:
        self.session = session
        self.level_profiles = dict(level_profiles)
        self.client = client
        self.index: LevelIndex = load_level_index(session)
        self.menu = menu_from_rows(list_curriculum_levels(session))
        self.menu_levels = [item.level for item in self.menu]
        self.corpus_names = get_enabled_corpus_names()
        self.floors = get_corpus_zipf_floors(session, self.corpus_names)
        self.context = build_context(self.menu)

    def word_weights(self, query: PlacementQuery) -> Optional[Dict[str, float]]:
        """The query's corpus weights: a lemma's sense-split rollup, else its spelling's."""
        if query.exclude_lemma_id is not None:
            lemma = self.session.get(Lemma, query.exclude_lemma_id)
            if lemma is not None:
                measured = profile_lemma(self.session, lemma, self.corpus_names, self.floors)
                if measured is not None:
                    return measured.weights
        return measure_token_weights(
            self.session, query.lemma_text, corpus_names=self.corpus_names, floors=self.floors
        )

    def shortlist(
        self, query: PlacementQuery, weights: Optional[Mapping[str, float]]
    ) -> List[ShortlistEntry]:
        """Merge both rankers' suggestions and attach level details."""
        rule = level_candidates(query, self.index, limit=RULE_CANDIDATES)
        rule_reasons = [(candidate.level, candidate.reason) for candidate in rule]
        corpus_reasons: List[tuple[int, str]] = []
        if weights:
            for match in suggest_levels(self.level_profiles, dict(weights)):
                if match.lift < MIN_CORPUS_LIFT:
                    break
                if not offered(match.level):
                    continue
                corpus_reasons.append(
                    (
                        match.level,
                        f"corpus match: {match.share:.0%} of its topical words lean the "
                        f"same way ({match.lift:.1f}x an average level)",
                    )
                )
                if len(corpus_reasons) >= CORPUS_CANDIDATES:
                    break

        entries: List[ShortlistEntry] = []
        for level, reasons in merge_shortlist(rule_reasons, corpus_reasons, self.menu_levels):
            rule_match = next((item for item in rule if item.level == level), None)
            samples = [
                lemma.lemma_text
                for lemma in level_words(self.session, level, limit=SAMPLE_WORDS + 1)
                if lemma.id != query.exclude_lemma_id
            ][:SAMPLE_WORDS]
            entries.append(
                ShortlistEntry(
                    level=level,
                    reasons=reasons,
                    level_size=(
                        rule_match.level_size if rule_match else self.index.level_size(level, query)
                    ),
                    capacity=rule_match.capacity if rule_match else None,
                    sample_words=tuple(samples),
                )
            )
        return entries

    def prepare(self, query: PlacementQuery) -> tuple[str, List[ShortlistEntry], Optional[str]]:
        """Build the per-word prompt. Returns ``(prompt, shortlist, core_block)``."""
        weights = self.word_weights(query)
        shortlist = self.shortlist(query, weights)
        core_block = core_evidence(query, self.index)
        prompt = build_prompt(query, shortlist, self.menu, weights, core_block)
        return prompt, shortlist, core_block

    def place(self, query: PlacementQuery) -> PlacementSuggestion:
        """Ask the model for a level for ``query``."""
        if self.client is None:
            raise RuntimeError("LevelPlacer was built without an LLM client")
        prompt, shortlist, core_block = self.prepare(query)
        response = self.client.generate_chat(
            prompt=prompt, context=self.context, json_schema=PLACEMENT_JSON_SCHEMA
        )
        payload = response.structured_data
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            payload = {}
        return parse_placement(
            payload, self.menu_levels, [entry.level for entry in shortlist], core_block
        )


def load_profiles(session: Session, profiles_json: Optional[Path]) -> Dict[int, LevelProfile]:
    """Level corpus profiles, from a saved file when given (measuring takes minutes)."""
    if profiles_json is not None:
        level_profiles, _ = load_level_profiles(str(profiles_json))
    else:
        logger.info("Measuring level corpus profiles; pass --profiles-json to reuse a saved run")
        level_profiles, _ = build_level_profiles(session)
    return level_profiles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pending", action="store_true", help="Every pending lemma import")
    target.add_argument("--pending-id", type=int, help="One pending import")
    target.add_argument("--lemma-guid", help="A stored lemma, placed as if new")
    parser.add_argument("--limit", type=int, help="Most pending rows to place")
    parser.add_argument(
        "--profiles-json",
        type=Path,
        help="Level corpus profiles saved by scripts/level_corpus_profile.py --json",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the prompts instead of calling the model"
    )
    parser.add_argument("--model", help="Model to use (default: the configured default)")
    parser.add_argument("--output", type=Path, help="TSV path (default: stdout)")
    parser.add_argument("--db-path", type=Path, default=Path(constants.WORDFREQ_DB_PATH))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = DataSourceConfig(
        backend_type=BackendType.SQLITE, sqlite_path=str(args.db_path), model=args.model
    )
    session = create_session(config)
    client = None if args.dry_run else UnifiedLLMClient.from_config(config)
    placer = LevelPlacer(session, load_profiles(session, args.profiles_json), client)

    queries: List[tuple[str, PlacementQuery]] = []
    if args.lemma_guid:
        lemma = session.query(Lemma).filter(Lemma.guid == args.lemma_guid).one()
        queries.append((lemma.guid or "", query_for_lemma(session, lemma, placer.index)))
    else:
        pending_query = session.query(PendingImport).filter(
            PendingImport.target_kind == TARGET_KIND_LEMMA
        )
        if args.pending_id is not None:
            pending_query = pending_query.filter(PendingImport.id == args.pending_id)
        pending_query = pending_query.order_by(PendingImport.id)
        if args.limit:
            pending_query = pending_query.limit(args.limit)
        queries.extend(
            (str(pending.id), query_for_pending(session, pending)) for pending in pending_query
        )

    if args.dry_run:
        print("=== CONTEXT ===\n" + placer.context)
        for row_id, query in queries:
            print(f"\n=== PROMPT {row_id} ===\n" + placer.prepare(query)[0])
        return 0

    handle = args.output.open("w", encoding="utf-8", newline="") if args.output else sys.stdout
    writer = csv.writer(handle, delimiter="\t")
    writer.writerow(
        ["id", "word", "subtype", "level", "fit", "alternatives", "shortlist", "reasoning"]
    )
    for row_id, query in queries:
        suggestion = placer.place(query)
        writer.writerow(
            [
                row_id,
                query.lemma_text,
                query.pos_subtype or "",
                suggestion.level if suggestion.level is not None else "",
                suggestion.fit,
                ",".join(str(level) for level in suggestion.alternatives),
                ",".join(str(level) for level in suggestion.shortlist),
                " ".join([suggestion.reasoning, *suggestion.problems]).strip(),
            ]
        )
        handle.flush()
    if args.output:
        handle.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
