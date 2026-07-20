#!/usr/bin/env python3
"""Migrate English lexical word lists out of inflection.py into grammar facts.

``langtools.en.inflection`` used to carry hand-written surface-text tables of
uncountable nouns, pluralia tantum, irregular plurals, non-gradable adjectives
and adverbs, and so on.  Those are lexical properties of a *lemma*, not of a
spelling — "iron" the metal is uncountable while "iron" the appliance is not —
so they now live in the ``grammar_facts`` table keyed per lemma.

This script performs the one-time data load.  The word lists below are the
verbatim pre-deletion contents of those tables; this is the one legitimate
place for them.

Facts written:
    number_type=uncountable      from UNCOUNTABLE_NOUNS         (noun)
    number_type=plurale_tantum   from PLURALIA_TANTUM           (noun)
    plural=<form>                from IRREGULAR_PLURALS         (noun)
    gradability=non_gradable     from NON_GRADABLE_ADJECTIVES   (adjective)
    gradability=periphrastic     from PERIPHRASTIC_ADJECTIVES   (adjective)
    gradability=non_gradable     from NON_GRADABLE_ADVERBS      (adverb)
    gradability=synthetic        from FLAT_ADVERBS              (adverb)

All facts are inserted with ``verified=False`` for later human review.

Entries are only written when the surface form matches exactly one lemma of
the required part of speech.  Unmatched entries and multi-sense conflicts
(where one spelling has several lemmas of the right POS) are reported rather
than guessed at.

Usage:
    PYTHONPATH=src python3 scripts/migrate_inflection_lists_to_facts.py
    PYTHONPATH=src python3 scripts/migrate_inflection_lists_to_facts.py --yes

Runs as a dry run unless ``--yes`` is given.  Re-running is safe: facts that
already exist for a lemma/language/type are skipped.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

if str(Path(__file__).parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.config.grammar_fact_registry import GRAMMAR_FACT_DEFINITIONS
from storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from storage.models.schema import Lemma

MIGRATION_NOTE = "migrated from langtools.en.inflection word list"

# ---------------------------------------------------------------------------
# Verbatim pre-deletion word lists from src/langtools/en/inflection.py
# ---------------------------------------------------------------------------

IRREGULAR_PLURALS: Dict[str, str] = {
    "aircraft": "aircraft",
    "album": "albums",
    "analysis": "analyses",
    "apparatus": "apparatuses",
    "avocado": "avocados",
    "axis": "axes",
    "bacterium": "bacteria",
    "basis": "bases",
    "belief": "beliefs",
    "bus": "buses",
    "cactus": "cacti",
    "calf": "calves",
    "cargo": "cargoes",
    "chef": "chefs",
    "chief": "chiefs",
    "child": "children",
    "crisis": "crises",
    "criterion": "criteria",
    "deer": "deer",
    "diagnosis": "diagnoses",
    "die": "dice",
    "dwarf": "dwarves",
    "echo": "echoes",
    "elf": "elves",
    "fish": "fish",
    "flamingo": "flamingos",
    "foot": "feet",
    "fungus": "fungi",
    "goose": "geese",
    "gulf": "gulfs",
    "half": "halves",
    "handkerchief": "handkerchiefs",
    "hero": "heroes",
    "hoof": "hooves",
    "hypothesis": "hypotheses",
    "index": "indices",
    "kilo": "kilos",
    "knife": "knives",
    "leaf": "leaves",
    "life": "lives",
    "loaf": "loaves",
    "louse": "lice",
    "man": "men",
    "mango": "mangoes",
    "means": "means",
    "medium": "media",
    "memo": "memos",
    "mosquito": "mosquitoes",
    "mouse": "mice",
    "museum": "museums",
    "nucleus": "nuclei",
    "oasis": "oases",
    "octopus": "octopuses",
    "ox": "oxen",
    "parenthesis": "parentheses",
    "person": "people",
    "phenomenon": "phenomena",
    "photo": "photos",
    "piano": "pianos",
    "potato": "potatoes",
    "proof": "proofs",
    "radio": "radios",
    "rhinoceros": "rhinoceroses",
    "roof": "roofs",
    "salmon": "salmon",
    "scarf": "scarves",
    "self": "selves",
    "series": "series",
    "sheaf": "sheaves",
    "sheep": "sheep",
    "shelf": "shelves",
    "shrimp": "shrimp",
    "solo": "solos",
    "species": "species",
    "stadium": "stadiums",
    "stimulus": "stimuli",
    "studio": "studios",
    "swine": "swine",
    "syllabus": "syllabi",
    "synthesis": "syntheses",
    "thesis": "theses",
    "thief": "thieves",
    "tomato": "tomatoes",
    "tooth": "teeth",
    "trout": "trout",
    "tuna": "tuna",
    "veto": "vetoes",
    "virus": "viruses",
    "volcano": "volcanoes",
    "wharf": "wharves",
    "wife": "wives",
    "wolf": "wolves",
    "woman": "women",
    "zero": "zeros",
    "zoo": "zoos",
}

UNCOUNTABLE_NOUNS: Tuple[str, ...] = (
    "advice",
    "aluminum",
    "ammonia",
    "anger",
    "archery",
    "art",
    "asphalt",
    "bacon",
    "badminton",
    "baking",
    "baseball",
    "basketball",
    "beef",
    "behavior",
    "biology",
    "blood",
    "boredom",
    "brass",
    "bread",
    "bronze",
    "butter",
    "calmness",
    "camping",
    "cardboard",
    "cash",
    "cement",
    "chalk",
    "chaos",
    "charcoal",
    "cheerfulness",
    "chemistry",
    "chess",
    "chlorine",
    "clay",
    "clothing",
    "coal",
    "compassion",
    "concrete",
    "consciousness",
    "cooking",
    "copper",
    "corn",
    "cotton",
    "courage",
    "curiosity",
    "cycling",
    "dancing",
    "darkness",
    "dust",
    "education",
    "electricity",
    "energy",
    "evidence",
    "evil",
    "fiberglass",
    "fiction",
    # Not in the original list: as a foodstuff ("I am eating fish") this is a
    # mass noun.  SUBTYPE_OVERRIDES keeps it off the animal sense.
    "fish",
    "fishing",
    "flesh",
    "flour",
    "fog",
    "folk",
    "food",
    "freedom",
    "fun",
    "fur",
    "furniture",
    "gardening",
    "geography",
    "gold",
    "golf",
    "grass",
    "gratitude",
    "gravity",
    "guilt",
    "gymnastics",
    "happiness",
    "hardware",
    "harmony",
    "hate",
    "health",
    "hearing",
    "hiking",
    "history",
    "hockey",
    "homework",
    "honey",
    "humor",
    "hydrogen",
    "ice",
    "information",
    "ink",
    "iron",
    "jealousy",
    "jewelry",
    "justice",
    "knowledge",
    "laundry",
    "leather",
    "limestone",
    "linen",
    "literature",
    "loneliness",
    "luck",
    "luggage",
    "magic",
    "marble",
    "mathematics",
    "mayonnaise",
    "meat",
    "methane",
    "milk",
    "money",
    "moss",
    "music",
    "mustard",
    "nervousness",
    "news",
    "nitrogen",
    "nylon",
    "oxygen",
    "pasta",
    "patience",
    "photography",
    "physics",
    "plastic",
    "pollen",
    "pork",
    "pottery",
    "poverty",
    "programming",
    "progress",
    "prose",
    "reading",
    "research",
    "rice",
    "rubber",
    "rugby",
    "running",
    "sadness",
    "safety",
    "salt",
    "sand",
    "science",
    "sewing",
    "shame",
    "shopping",
    "silence",
    "silk",
    "silver",
    "singing",
    "skateboarding",
    "skiing",
    "snow",
    "soccer",
    "software",
    "spinach",
    "steam",
    "steel",
    "strength",
    "sugar",
    "sunshine",
    "surfing",
    "sweat",
    "swimming",
    "tar",
    "teaching",
    "tennis",
    "terror",
    "tiredness",
    "traffic",
    "training",
    "trash",
    "traveling",
    "underwear",
    "violence",
    "volleyball",
    "waste",
    "water",
    "wax",
    "weather",
    "wisdom",
    "wood",
    "wool",
    "wrestling",
    "writing",
    "yoga",
)

PLURALIA_TANTUM: Tuple[str, ...] = (
    "chopsticks",
    "clothes",
    "eyeglasses",
    "glasses",
    "groceries",
    "headphones",
    "jeans",
    "leftovers",
    "pajamas",
    "pants",
    "pliers",
    "sales",
    "scissors",
    "shorts",
    "slippers",
    "sports",
    "stairs",
    "sunglasses",
    "surroundings",
    "trousers",
)

NON_GRADABLE_ADJECTIVES: Tuple[str, ...] = (
    "alive",
    "automatic",
    "bent",
    "boiling",
    "broken",
    "circular",
    "closed",
    "complete",
    "conical",
    "cubic",
    "curved",
    "cylindrical",
    "daily",
    "dead",
    "dependent",
    "due",
    "elastic",
    "electric",
    "equal",
    "favorite",
    "female",
    "final",
    "fixed",
    "floating",
    "following",
    "front",
    "frozen",
    "gone",
    "hanging",
    "hexagonal",
    "hidden",
    "impossible",
    "last",
    "left",
    "local",
    "lost",
    "made",
    "main",
    "major",
    "male",
    "married",
    "material",
    "medical",
    "medium",
    "middle",
    "miniature",
    "missing",
    "mixed",
    "named",
    "next",
    "octagonal",
    "opposite",
    "outer",
    "oval",
    "own",
    "parallel",
    "pentagonal",
    "physical",
    "political",
    "possible",
    "present",
    "previous",
    "private",
    "pyramidal",
    "rectangular",
    "right",
    "separate",
    "shaped",
    "shut",
    "single",
    "sole",
    "spherical",
    "spiral",
    "square",
    "triangular",
    "unique",
    "unknown",
    "wooden",
    "wrong",
)

PERIPHRASTIC_ADJECTIVES: Tuple[str, ...] = (
    "afraid",
    "alert",
    "aware",
    "bored",
    "certain",
    "confused",
    "correct",
    "eager",
    "excited",
    "famous",
    "glad",
    "ill",
    "loyal",
    "pleased",
    "real",
    "scared",
    "sure",
    "tired",
    "worried",
    "wounded",
)

NON_GRADABLE_ADVERBS: Tuple[str, ...] = (
    "absolutely",
    "actually",
    "afterward",
    "again",
    "ago",
    "ahead",
    "all",
    "almost",
    "alone",
    "along",
    "already",
    "also",
    "always",
    "anyway",
    "anywhere",
    "apart",
    "apparently",
    "around",
    "aside",
    "away",
    "barely",
    "beforehand",
    "below",
    "certainly",
    "completely",
    "daily",
    "down",
    "east",
    "else",
    "enough",
    "entirely",
    "especially",
    "even",
    "everywhere",
    "evidently",
    "exactly",
    "extremely",
    "finally",
    "forever",
    "forth",
    "forward",
    "fully",
    "hardly",
    "here",
    "however",
    "immediately",
    "indeed",
    "inside",
    "instead",
    "just",
    "likewise",
    "meanwhile",
    "merely",
    "momentarily",
    "nearly",
    "never",
    "north",
    "now",
    "nowhere",
    "obviously",
    "off",
    "once",
    "online",
    "only",
    "otherwise",
    "out",
    "outside",
    "overhead",
    "partly",
    "perhaps",
    "permanently",
    "possibly",
    "presently",
    "probably",
    "quite",
    "rather",
    "really",
    "recently",
    "right",
    "simply",
    "slightly",
    "somehow",
    "sometimes",
    "somewhere",
    "south",
    "still",
    "suddenly",
    "surely",
    "temporarily",
    "there",
    "therefore",
    "this afternoon",
    "this evening",
    "this morning",
    "thus",
    "today",
    "together",
    "tomorrow",
    "tonight",
    "too",
    "totally",
    "twice",
    "up",
    "upstairs",
    "usually",
    "very",
    "west",
    "yesterday",
)

FLAT_ADVERBS: Tuple[str, ...] = (
    "close",
    "deep",
    "early",
    "fast",
    "hard",
    "high",
    "late",
    "long",
    "loud",
    "low",
    "near",
    "quick",
    "slow",
    "soon",
    "straight",
    "tight",
    "wide",
)


# ---------------------------------------------------------------------------
# Migration plan
# ---------------------------------------------------------------------------


class FactSpec(NamedTuple):
    """One (surface form -> fact) assignment the migration wants to make."""

    source: str
    pos_type: str
    fact_type: str
    surface: str
    fact_value: str


def build_plan() -> List[FactSpec]:
    """Expand the word lists into a flat list of intended fact assignments."""
    plan: List[FactSpec] = []

    for surface in UNCOUNTABLE_NOUNS:
        plan.append(FactSpec("UNCOUNTABLE_NOUNS", "noun", "number_type", surface, "uncountable"))
    for surface in PLURALIA_TANTUM:
        plan.append(FactSpec("PLURALIA_TANTUM", "noun", "number_type", surface, "plurale_tantum"))
    for surface, plural in IRREGULAR_PLURALS.items():
        plan.append(FactSpec("IRREGULAR_PLURALS", "noun", "plural", surface, plural))

    for surface in NON_GRADABLE_ADJECTIVES:
        plan.append(
            FactSpec("NON_GRADABLE_ADJECTIVES", "adjective", "gradability", surface, "non_gradable")
        )
    for surface in PERIPHRASTIC_ADJECTIVES:
        plan.append(
            FactSpec("PERIPHRASTIC_ADJECTIVES", "adjective", "gradability", surface, "periphrastic")
        )

    for surface in NON_GRADABLE_ADVERBS:
        plan.append(
            FactSpec("NON_GRADABLE_ADVERBS", "adverb", "gradability", surface, "non_gradable")
        )
    for surface in FLAT_ADVERBS:
        plan.append(FactSpec("FLAT_ADVERBS", "adverb", "gradability", surface, "synthetic"))

    return plan


# Senses that share a spelling but not a lexical property.  Keyed by
# (surface, pos_type, fact_type) -> {pos_subtype: fact_value}.  A subtype
# mapped to ``None`` is deliberately left without this fact.
#
# This is a one-off disambiguation table for THIS migration only: it exists
# because a surface-text list cannot say that "iron" the metal is uncountable
# while "iron" the appliance is not.  Going forward the facts themselves carry
# that information per lemma, which is the whole point of the refactor.
SUBTYPE_OVERRIDES: Dict[Tuple[str, str, str], Dict[str, Optional[str]]] = {
    # The metal is a mass noun; the household appliance is an ordinary count noun.
    ("iron", "noun", "number_type"): {
        "material_substance": "uncountable",
        "appliance": None,
    },
    # Both senses are countable and share the same irregular plural.
    ("child", "noun", "plural"): {
        "human": "children",
        "family_relation": "children",
    },
    # The animal has the zero plural "fish"; the foodstuff is a mass noun.
    ("fish", "noun", "plural"): {
        "animal": "fish",
        "food": None,
    },
    ("fish", "noun", "number_type"): {
        "animal": None,
        "food": "uncountable",
    },
    # "left" is non-gradable in every sense, adjective and adverb alike.
    ("left", "adjective", "gradability"): {
        "quality": "non_gradable",
        "physical_property": "non_gradable",
    },
}


def index_lemmas(session: Session) -> Dict[Tuple[str, str], List[Lemma]]:
    """Index every lemma by ``(lowercased lemma_text, lowercased pos_type)``."""
    index: Dict[Tuple[str, str], List[Lemma]] = defaultdict(list)
    for lemma in session.query(Lemma).all():
        if not lemma.lemma_text or not lemma.pos_type:
            continue
        index[(lemma.lemma_text.strip().lower(), lemma.pos_type.strip().lower())].append(lemma)
    return index


def lemma_label(lemma: Lemma) -> str:
    disambiguation = f" ({lemma.disambiguation})" if lemma.disambiguation else ""
    return f"{lemma.lemma_text}{disambiguation} [id={lemma.id}, guid={lemma.guid}]"


class Outcome(NamedTuple):
    """What the migration decided to do with one planned fact."""

    spec: FactSpec
    status: str  # "insert", "exists", "unmatched", "conflict"
    lemma: Optional[Lemma]
    candidates: List[Lemma]


def resolve_by_subtype(spec: "FactSpec", candidates: List[Lemma]) -> Optional[List[Outcome]]:
    """Split a multi-sense match using :data:`SUBTYPE_OVERRIDES`.

    Returns one outcome per candidate when every sense is covered, or ``None``
    when no override applies, so the caller can fall back to reporting a
    conflict for manual review.
    """
    overrides = SUBTYPE_OVERRIDES.get((spec.surface.lower(), spec.pos_type, spec.fact_type))
    if overrides is None:
        return None

    subtypes = [(lemma.pos_subtype or "").strip().lower() for lemma in candidates]
    if not all(subtype in overrides for subtype in subtypes):
        # An unlisted sense appeared since the table was written; do not guess.
        return None

    resolved: List[Outcome] = []
    for lemma, subtype in zip(candidates, subtypes):
        fact_value = overrides[subtype]
        if fact_value is None:
            resolved.append(Outcome(spec, "skipped_by_subtype", lemma, candidates))
            continue
        resolved.append(Outcome(spec._replace(fact_value=fact_value), "insert", lemma, candidates))
    return resolved


def resolve(
    session: Session, plan: List[FactSpec], index: Dict[Tuple[str, str], List[Lemma]]
) -> List[Outcome]:
    """Match each planned fact to a lemma and classify the result."""

    def classify(outcome: Outcome) -> Outcome:
        """Downgrade an ``insert`` to ``exists`` when the fact is already set."""
        if outcome.status != "insert" or outcome.lemma is None:
            return outcome
        existing = get_grammar_fact_value(session, outcome.lemma.id, "en", outcome.spec.fact_type)
        if existing is not None:
            return outcome._replace(status="exists")
        return outcome

    outcomes: List[Outcome] = []
    for spec in plan:
        candidates = index.get((spec.surface.lower(), spec.pos_type), [])
        if not candidates:
            outcomes.append(Outcome(spec, "unmatched", None, []))
            continue
        if len(candidates) > 1:
            # Several senses share this spelling and the correct fact may
            # differ per sense.  pos_subtype tells them apart where the
            # override table covers every sense; otherwise a human decides.
            resolved = resolve_by_subtype(spec, candidates)
            if resolved is None:
                outcomes.append(Outcome(spec, "conflict", None, candidates))
            else:
                outcomes.extend(classify(item) for item in resolved)
            continue
        outcomes.append(classify(Outcome(spec, "insert", candidates[0], candidates)))
    return outcomes


def apply_inserts(session: Session, outcomes: List[Outcome]) -> Tuple[int, int]:
    """Write the ``insert`` outcomes; returns ``(written, failed)``."""
    written = 0
    failed = 0
    for outcome in outcomes:
        if outcome.status != "insert" or outcome.lemma is None:
            continue
        fact = add_grammar_fact(
            session,
            lemma_id=outcome.lemma.id,
            language_code="en",
            fact_type=outcome.spec.fact_type,
            fact_value=outcome.spec.fact_value,
            notes=f"{MIGRATION_NOTE} {outcome.spec.source}",
            verified=False,
        )
        if fact is None:
            failed += 1
            print(
                f"  FAILED {outcome.spec.fact_type}={outcome.spec.fact_value} "
                f"for {lemma_label(outcome.lemma)}",
                file=sys.stderr,
            )
        else:
            written += 1
    return written, failed


def report(outcomes: List[Outcome], dry_run: bool) -> None:
    """Print the per-fact-type summary plus every skipped entry."""
    by_status: Dict[str, List[Outcome]] = defaultdict(list)
    for outcome in outcomes:
        by_status[outcome.status].append(outcome)

    verb = "would insert" if dry_run else "inserted"
    print(f"Planned assignments: {len(outcomes)}\n")

    print(f"Facts to insert ({verb}), by fact type and value:")
    counts: Dict[Tuple[str, str], int] = defaultdict(int)
    for outcome in by_status["insert"]:
        # "plural" stores a distinct form per lemma, so it is counted as a
        # single bucket rather than one bucket per plural string.
        value_key = (
            "<per-lemma plural form>"
            if outcome.spec.fact_type == "plural"
            else outcome.spec.fact_value
        )
        counts[(outcome.spec.fact_type, value_key)] += 1
    if not counts:
        print("  (none)")
    for (fact_type, fact_value), count in sorted(counts.items()):
        print(f"  {fact_type}={fact_value}: {count}")
    print(f"  TOTAL: {len(by_status['insert'])}\n")

    print(f"Already present (idempotent skip): {len(by_status['exists'])}")
    for outcome in sorted(by_status["exists"], key=lambda o: (o.spec.fact_type, o.spec.surface)):
        assert outcome.lemma is not None
        print(f"  {outcome.spec.fact_type} {lemma_label(outcome.lemma)}")
    print()

    unmatched = by_status["unmatched"]
    print(f"Unmatched (no lemma of the required POS with that spelling): {len(unmatched)}")
    by_source: Dict[str, List[str]] = defaultdict(list)
    for outcome in unmatched:
        by_source[outcome.spec.source].append(outcome.spec.surface)
    for source, surfaces in sorted(by_source.items()):
        print(f"  {source} ({len(surfaces)}): {', '.join(sorted(surfaces))}")
    print()

    subtype_skips = by_status["skipped_by_subtype"]
    print(f"Multi-sense senses deliberately left without the fact: {len(subtype_skips)}")
    for outcome in sorted(subtype_skips, key=lambda o: (o.spec.surface, o.spec.fact_type)):
        assert outcome.lemma is not None
        print(
            f"  {outcome.spec.fact_type} not set for {lemma_label(outcome.lemma)} "
            f"[{outcome.lemma.pos_subtype}]"
        )
    print()

    conflicts = by_status["conflict"]
    print(f"MULTI-SENSE CONFLICTS needing manual review: {len(conflicts)}")
    for outcome in sorted(conflicts, key=lambda o: (o.spec.pos_type, o.spec.surface)):
        print(
            f"  [{outcome.spec.pos_type}] {outcome.spec.surface!r} -> "
            f"{outcome.spec.fact_type}={outcome.spec.fact_value} "
            f"(from {outcome.spec.source})"
        )
        for candidate in sorted(outcome.candidates, key=lambda c: c.id):
            print(f"      {lemma_label(candidate)}: {candidate.definition_text}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default="data/wordfreq/linguistics.sqlite",
        help="Path to SQLite database file (default: data/wordfreq/linguistics.sqlite)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually write the facts. Without this the script is a dry run.",
    )
    args = parser.parse_args()

    # Guard against the registry drifting away from what this script writes.
    for fact_type in ("number_type", "plural", "gradability"):
        definition = GRAMMAR_FACT_DEFINITIONS.get(fact_type)
        if definition is None or "en" not in definition.languages:
            print(
                f"ERROR: grammar fact type {fact_type!r} is not registered for English.",
                file=sys.stderr,
            )
            return 1

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 1

    dry_run = not args.yes
    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'APPLY'}\n")

    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        plan = build_plan()
        index = index_lemmas(session)
        outcomes = resolve(session, plan, index)

        written = 0
        failed = 0
        if not dry_run:
            written, failed = apply_inserts(session, outcomes)

        report(outcomes, dry_run)

        if not dry_run:
            print(f"Wrote {written} grammar facts ({failed} failed).")
        else:
            print("Dry run complete; re-run with --yes to write these facts.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
