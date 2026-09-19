"""Summarize the verb co-occurrence artifact as something readable.

``data/wordfreq/cooccurrence.json`` holds every scored pairing for ~300 verbs,
which is too dense to read.  This turns it into a plain-text report answering
the two questions the curriculum actually asks:

1. Which verbs does each noun group need?  A named unit (Animals 3, Food 2)
   should pull its verbs in with it, and that means knowing which verbs lean
   on it.
2. How do the most frequent verbs get introduced?  In the core there are no
   verb groups to attach to, so each one has to be placed against the nouns
   it needs -- and a verb taught before its objects has nothing to say.

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
        object_level = (
            first_level_of_subtype(concrete[0]["subtype"], level_by_word, subtype_by_word)
            if concrete
            else None
        )
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

    # --- Section 2: hardcoded verbs -----------------------------------
    lines.append("")
    lines.append("2. HARDCODED VERBS (not measured)")
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
    lines.append("3. WHICH VERBS EACH NOUN GROUP NEEDS")
    lines.append("-" * 72)
    lines.append("")
    lines.append("Read this when cutting a named unit: these are the verbs that lean")
    lines.append("on the group, so they are the candidates to introduce alongside it.")
    lines.append("A verb appears under every group it leans on, which is the point --")
    lines.append("'wear' belongs with clothing and with body parts.")
    lines.append("")
    for subtype in sorted(by_subtype):
        entries = sorted(by_subtype[subtype], key=lambda pair: -pair[1])[:10]
        first_level = first_level_of_subtype(subtype, level_by_word, subtype_by_word)
        level_note = f"first taught L{first_level}" if first_level is not None else "not taught"
        lines.append(f"{subtype}  ({level_note})")
        for verb, lift in entries:
            verb_level = level_by_word.get(verb)
            verb_level_text = f"L{verb_level}" if verb_level is not None else "-"
            lines.append(f"    {verb:<16}{lift:>6.1f}x   taught {verb_level_text}")
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
