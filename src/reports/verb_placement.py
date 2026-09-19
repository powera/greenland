"""Summarize the verb co-occurrence artifact as something readable.

``data/wordfreq/cooccurrence.json`` holds every scored pairing for ~320 verbs,
which is too dense to read.  This turns it into a plain-text report answering
the questions the curriculum actually asks:

1. Are the most frequent verbs usable when they arrive -- is there anything
   yet for them to take as an object?
2. Which verbs are general-purpose enough to seed the early levels with?  A
   verb that goes with any noun makes example sentences possible for every
   group, and a flat affinity profile is what identifies one.
3. Which verbs does each noun group need, for when a named unit is cut?

Two things the report deliberately does *not* treat as problems:

* A verb arriving later than a group it suits.  Cows can be introduced
  without "steal"; what matters is whether a group has *enough* usable verbs,
  not all of them.
* A noun group at L1-L3 with no verbs at all.  Those levels are noun-only on
  purpose, building 50-100 memorized words before sentences start.

The report is read-only and writes a text file.  It takes the levels from the
database so the "taught at" column reflects reality rather than the artifact.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.common.common_args import add_backend_args, get_data_source_config
from storage.backend import create_session
from storage.models.schema import Lemma, LemmaDifficultyOverride

DEFAULT_ARTIFACT = Path("data/wordfreq/cooccurrence.json")
DEFAULT_OUTPUT = Path("verb_placement_report.txt")

#: How many verbs the headline section covers.
DEFAULT_TOP_VERBS = 50

#: How many subtypes to show per verb.
TOP_SUBTYPES = 3

#: A pairing below this lift is not worth naming as an attachment.
MIN_LIFT = 1.5

# A general-purpose verb ("like", "see", "want") combines with almost any noun,
# so it leans on nothing in particular and its top lift stays low.  These are
# the verbs the early levels need: a few of them make an example sentence
# possible for every group, even an awkward one.  Rare verbs also look flat --
# thin evidence, not versatility -- so a frequency floor comes with it.
GENERAL_VERB_MAX_LIFT = 2.5
GENERAL_VERB_MIN_COUNT = 1000

# Levels at or below this are deliberately noun-only (or nearly so): the course
# builds a base of 50-100 memorized nouns before verbs and sentences start.
# The database matches that intent -- 41 nouns after L1, 83 after L2, 117 after
# L3, with the first verbs at L3 -- so a group arriving here with no verb is
# the design working, not a gap, and the report must not flag it.
NOUN_ONLY_LEVEL_MAX = 3

# Subtypes that are not things a verb takes as an object.  A high lift for one
# of these is a real fact about the verb's company -- "say" does occur near
# honorifics -- but it is not a prerequisite: a learner does not need to have
# been taught an honorific before "say" is usable.  Treating them as objects
# made the prerequisite check report almost every verb, which is the same as
# reporting none of them.
NON_OBJECT_SUBTYPES = frozenset(
    {
        "honorific",
        "nationality",
        "human",
        "family_relation",
        "occupation",
        "group_people",
        "city",
        "region",
        "place_name",
        "geographic_place",
        "temporal_name",
        "time_period",
        "relative_time",
        "specific_time",
        "duration",
        "unit_of_measurement",
        "quantitative_concept",
        "abstract_condition",
        "concept_idea",
        "mental_construct",
        "knowledge_domain",
        "symbolic_element",
        "process_event",
        "activity",
        "quality_attribute",
        "social_institution",
        "chemical_compound",
    }
)


def load_levels(session: Any, language_code: str) -> Tuple[Dict[str, int], Dict[str, str]]:
    """Return ``(level_by_word, subtype_by_word)`` for every leveled lemma.

    Levels are the language-effective ones, so a per-language override is
    respected exactly as the exporter would apply it.
    """
    overrides: Dict[int, int] = {
        lemma_id: difficulty_level
        for lemma_id, difficulty_level in session.query(
            LemmaDifficultyOverride.lemma_id, LemmaDifficultyOverride.difficulty_level
        ).filter(LemmaDifficultyOverride.language_code == language_code)
    }

    level_by_word: Dict[str, int] = {}
    subtype_by_word: Dict[str, str] = {}
    for lemma in session.query(Lemma).filter(Lemma.difficulty_level.isnot(None)):
        level = overrides.get(lemma.id, lemma.difficulty_level)
        if level is None or level < 0:
            continue
        word = lemma.lemma_text.lower()
        # Several senses share a surface form; the earliest level is when the
        # learner first meets the word, which is what placement cares about.
        if word not in level_by_word or level < level_by_word[word]:
            level_by_word[word] = level
            if lemma.pos_subtype:
                subtype_by_word[word] = lemma.pos_subtype
    return level_by_word, subtype_by_word


def first_level_of_subtype(
    subtype: str, level_by_word: Mapping[str, int], subtype_by_word: Mapping[str, str]
) -> Optional[int]:
    """The earliest level at which any noun of *subtype* is taught."""
    levels = [
        level_by_word[word]
        for word, word_subtype in subtype_by_word.items()
        if word_subtype == subtype and word in level_by_word
    ]
    return min(levels) if levels else None


def _format_subtypes(entry: Mapping[str, Any], limit: int = TOP_SUBTYPES) -> str:
    parts = [
        f"{item['subtype']} ({item['lift']:.1f}x)"
        for item in entry["subtypes"][:limit]
        if item["lift"] >= MIN_LIFT
    ]
    return ", ".join(parts) if parts else "(no strong affinity)"


def write_report(
    artifact: Mapping[str, Any],
    level_by_word: Mapping[str, int],
    subtype_by_word: Mapping[str, str],
    *,
    top_verbs: int,
    output: Path,
) -> None:
    """Write the plain-text summary."""
    verbs: Dict[str, Any] = artifact["verbs"]
    lines: List[str] = []

    lines.append("VERB PLACEMENT REPORT")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Sources        : {', '.join(artifact['sources'])}")
    lines.append(f"Documents      : {artifact['documents_scanned']:,}")
    lines.append(f"Window         : {artifact['window']} tokens after the verb")
    lines.append(f"Verbs scored   : {len(verbs)}")
    lines.append("")
    lines.append("A 'lift' of 5.0x means the subtype follows this verb five times as")
    lines.append("often as it follows verbs in general. Raw counts are useless here:")
    lines.append("concept_idea and time_period sit near every verb, so they top an")
    lines.append("unscaled ranking for almost everything. Lift is what surfaces the")
    lines.append("real object.")
    lines.append("")
    lines.append(artifact["caveat"])
    lines.append("")

    # --- Section 1: the top verbs -------------------------------------
    ranked = sorted(verbs.items(), key=lambda pair: -pair[1]["occurrences"])[:top_verbs]

    lines.append("")
    lines.append(f"1. THE {len(ranked)} MOST FREQUENT VERBS")
    lines.append("-" * 72)
    lines.append("")
    lines.append("'Taught' is the verb's current level; '-' means it is not in the")
    lines.append("curriculum. 'Objects at' is the earliest level a noun of its best")
    lines.append("*concrete* subtype is taught -- when that is later than 'Taught',")
    lines.append("the verb arrives before anything it can take as an object.")
    lines.append("")
    lines.append("People, places, times and abstractions are skipped when picking that")
    lines.append("subtype. 'say' really does occur near honorifics, but a learner does")
    lines.append("not need an honorific before 'say' is usable, and counting those as")
    lines.append("objects flagged nearly every verb -- which says nothing at all.")
    lines.append("")
    lines.append(f"{'verb':<14}{'taught':>7}{'objects at':>12}  {'top subtypes by lift'}")
    lines.append(f"{'-' * 14}{'-' * 7:>7}{'-' * 12:>12}  {'-' * 34}")

    flagged: List[str] = []
    for verb, entry in ranked:
        level = level_by_word.get(verb)
        level_text = str(level) if level is not None else "-"
        concrete = [
            item
            for item in entry["subtypes"]
            if item["lift"] >= MIN_LIFT and item["subtype"] not in NON_OBJECT_SUBTYPES
        ]
        # The earliest object of *any* of its concrete subtypes, not just the
        # best-lift one: "put" is usable as soon as there is something to put,
        # whether or not that thing is an appliance.
        candidate_levels = [
            candidate
            for candidate in (
                first_level_of_subtype(item["subtype"], level_by_word, subtype_by_word)
                for item in concrete
            )
            if candidate is not None
        ]
        object_level = min(candidate_levels) if candidate_levels else None
        object_text = str(object_level) if object_level is not None else "-"
        marker = ""
        if level is not None and object_level is not None and level < object_level:
            marker = "  <-- before its objects"
            flagged.append(f"{verb} (L{level}, objects at L{object_level})")
        lines.append(
            f"{verb:<14}{level_text:>7}{object_text:>12}  {_format_subtypes(entry)}{marker}"
        )

    lines.append("")
    if flagged:
        lines.append(f"{len(flagged)} of these arrive before their objects:")
        for item in flagged:
            lines.append(f"  - {item}")
    else:
        lines.append("None of these arrive before their objects.")
    lines.append("")

    # --- Section 2: general-purpose verbs -----------------------------
    general: List[Tuple[float, str, int, Optional[int]]] = []
    for verb, entry in verbs.items():
        subtypes_for_verb: List[Dict[str, Any]] = entry["subtypes"]
        if not subtypes_for_verb or entry["occurrences"] < GENERAL_VERB_MIN_COUNT:
            continue
        top_lift = subtypes_for_verb[0]["lift"]
        if top_lift <= GENERAL_VERB_MAX_LIFT:
            general.append((top_lift, verb, entry["occurrences"], level_by_word.get(verb)))
    general.sort()

    lines.append("")
    lines.append("2. GENERAL-PURPOSE VERBS (the ones to seed the core with)")
    lines.append("-" * 72)
    lines.append("")
    lines.append("A verb that combines with almost any noun has a *flat* profile: it")
    lines.append("sits near many subtypes without leaning hard on any, so its top lift")
    lines.append("is low. That is the opposite of what section 4 rewards, and it is")
    lines.append("exactly what the early levels need -- a few of these make example")
    lines.append("sentences possible for every group, even if the sentences are")
    lines.append("awkward. 'I like the cow' is a usable card; a group with no verb at")
    lines.append("all is not.")
    lines.append("")
    lines.append("Frequency matters as well as flatness: a rare verb looks flat because")
    lines.append("its evidence is thin, not because it is versatile.")
    lines.append("")
    lines.append("This list is a starting point, not the answer. It misses verbs whose")
    lines.append("spelling is shared with something else: 'like' belongs here on any")
    lines.append("reading, but scores 4.3x on animal because of 'animals like wolves'")
    lines.append("-- the preposition, not the verb. Check the obvious candidates by")
    lines.append("hand before trusting an omission.")
    lines.append("")
    lines.append(f"{'verb':<14}{'top lift':>10}{'occurrences':>13}{'taught':>9}")
    lines.append(f"{'-' * 14}{'-' * 10:>10}{'-' * 13:>13}{'-' * 9:>9}")
    for top_lift, verb, occurrences, verb_level in general[:20]:
        level_text = f"L{verb_level}" if verb_level is not None else "-"
        lines.append(f"{verb:<14}{top_lift:>9.1f}x{occurrences:>13,}{level_text:>9}")
    lines.append("")

    # --- Section 3: hardcoded verbs -----------------------------------
    lines.append("")
    lines.append("3. HARDCODED VERBS (not measured)")
    lines.append("-" * 72)
    lines.append("")
    lines.append("These are placed by hand. Their English counts are mostly auxiliary")
    lines.append("uses -- 'I have seen', 'I was going' -- which is periphrastic tense,")
    lines.append("not the verb, and other languages do not build tenses that way. They")
    lines.append("are also too polysemous to gloss word-for-word early.")
    lines.append("")
    for verb, level in sorted(artifact["hardcoded_verbs"].items(), key=lambda p: p[1]):
        current = level_by_word.get(verb)
        current_text = f"currently L{current}" if current is not None else "NOT IN DATABASE"
        lines.append(f"  {verb:<8} proposed L{level:<5} ({current_text})")
    lines.append("")

    # --- Section 3: verbs each noun group needs -----------------------
    by_subtype: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
    for group_verb, group_entry in verbs.items():
        subtypes: List[Dict[str, Any]] = group_entry["subtypes"]
        for subtype_item in subtypes:
            if subtype_item["lift"] >= MIN_LIFT:
                by_subtype[subtype_item["subtype"]].append((group_verb, subtype_item["lift"]))

    lines.append("")
    lines.append("4. WHICH VERBS EACH NOUN GROUP NEEDS")
    lines.append("-" * 72)
    lines.append("")
    lines.append("Read this when cutting a named unit: these are the verbs that lean")
    lines.append("on the group, so they are the candidates to introduce alongside it.")
    lines.append("A verb appears under every group it leans on, which is the point --")
    lines.append("'wear' belongs with clothing and with body parts.")
    lines.append("")
    lines.append("A verb arriving later than the group is normal and mostly fine: you")
    lines.append("can introduce cows without 'steal'. What matters is whether the group")
    lines.append("has ENOUGH usable verbs when it arrives, so each group is marked with")
    lines.append("how many of its verbs are taught by then.")
    lines.append("")
    lines.append(f"Groups first taught at L{NOUN_ONLY_LEVEL_MAX} or earlier are marked")
    lines.append("'noun-only stage' and are never flagged. Those levels deliberately")
    lines.append("hold nouns alone, building a base of 50-100 memorized words before")
    lines.append("verbs and sentences start -- 41 nouns after L1, 83 after L2. A food")
    lines.append("group at L1 with no verb is the design working, not a gap.")
    lines.append("")

    starved: List[Tuple[str, int, int]] = []
    for subtype in sorted(by_subtype):
        entries = sorted(by_subtype[subtype], key=lambda pair: -pair[1])[:10]
        first_level = first_level_of_subtype(subtype, level_by_word, subtype_by_word)
        if first_level is None:
            level_note = "not taught"
        else:
            ready = sum(
                1
                for verb, _lift in by_subtype[subtype]
                if (level_by_word.get(verb) or 10**9) <= first_level
            )
            if first_level <= NOUN_ONLY_LEVEL_MAX:
                level_note = f"first taught L{first_level}, noun-only stage"
            else:
                level_note = f"first taught L{first_level}, ready {ready}"
                if ready < 2:
                    starved.append((subtype, first_level, ready))
        lines.append(f"{subtype}  ({level_note})")
        for verb, lift in entries:
            verb_level = level_by_word.get(verb)
            verb_level_text = f"L{verb_level}" if verb_level is not None else "-"
            marker = ""
            if first_level is not None and verb_level is not None and verb_level <= first_level:
                marker = "  *"
            lines.append(f"    {verb:<16}{lift:>6.1f}x   taught {verb_level_text}{marker}")
        lines.append("")

    if starved:
        lines.append("")
        lines.append("GROUPS ARRIVING WITH FEWER THAN TWO USABLE VERBS")
        lines.append("-" * 72)
        lines.append("")
        lines.append("These are the ones worth fixing -- either pull a verb down, or move")
        lines.append("the group later.")
        lines.append("")
        for subtype, first_level, ready in sorted(starved, key=lambda item: item[1]):
            lines.append(f"  L{first_level:<5} {subtype:<28} {ready} usable verb(s)")
        lines.append("")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_backend_args(parser)
    parser.add_argument(
        "--cooccurrence",
        type=Path,
        default=DEFAULT_ARTIFACT,
        help=f"Co-occurrence artifact to summarize (default: {DEFAULT_ARTIFACT})",
    )
    parser.add_argument(
        "--language",
        default="lt",
        help="Language whose difficulty overrides are applied (default: lt)",
    )
    parser.add_argument(
        "--top-verbs",
        type=int,
        default=DEFAULT_TOP_VERBS,
        help=f"Verbs in the headline section (default: {DEFAULT_TOP_VERBS})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Text file to write (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if not args.cooccurrence.exists():
        parser.error(
            f"{args.cooccurrence} not found. Build it first with "
            "src/wordfreq/corpora/build_cooccurrence.py"
        )
    artifact = json.loads(args.cooccurrence.read_text(encoding="utf-8"))

    session = create_session(get_data_source_config(args))
    try:
        level_by_word, subtype_by_word = load_levels(session, args.language)
    finally:
        session.close()

    write_report(
        artifact,
        level_by_word,
        subtype_by_word,
        top_verbs=args.top_verbs,
        output=args.output,
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
