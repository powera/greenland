#!/usr/bin/env python3
"""Import missing senses exposed by the capitalized English token review.

All additions use existing level 1180, Advanced Everyday Words. This is a
mixed vocabulary repair, rather than a coherent legal or political topic.
Prominence is explicitly common: a topic-band level must not make ordinary
meanings such as political party or illumination look rare.

Uses the same add_sense workflow as the sport imports: existing senses can be
matched, preserved and tagged, and new senses receive translations. Each sense
has its own label and tag so multiple meanings of one word remain distinct on
reruns. Existing levels are preserved when a sense is matched.

The middle-point sense already exists as centre; normalize that headword to
center while retaining centre as a spelling variant before executing this
list. Only the missing facility sense is requested here. Pending convention
274 needs separate review; this script does not consume pending entries.

Reviewed capitalization alternatives are attached to the returned sense GUID
after creation or matching, including on reruns. They use spelling variants,
like existing River/Lake entries. Punctuation variants remain a separate pass.
Dr is attached as an abbreviation of the doctor honorific, not its medical
occupation sense. Mr, Mrs and Ms are independent honorifics; Miss exists.

Without --execute this only prints the plan and makes no HTTP requests.
Execution uses the local add_sense persistence path and variant CRUD on the
same configured database, rather than the HTTP facade (which has no variant
write endpoint). It takes a minor backup before paid LLM calls and writes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent.parent
for import_root in (ROOT / "src", ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from sqlalchemy.orm import Session

from scripts.wordlists.wordlist_import_helper import SenseEntry, SenseList, print_sense_plan
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.backup import create_backup
from storage.crud.variant_form import add_variant_form
from storage.models.schema import Lemma
from words.add_sense import add_sense

DIFFICULTY_LEVEL = 1180
SOURCE = "wordlist/capitalized-gaps-1180"

# Only attach the capitalized token to meanings reviewed for that usage.
# The physical constitution, personal journal and customary convention senses
# are deliberately excluded, as are the geometric cross and adjective prime.
CAPITALIZED_SENSES: dict[tuple[str, str], str] = {
    ("constitution", "governing rules"): "Constitution",
    ("congress", "legislature"): "Congress",
    ("congress", "formal assembly"): "Congress",
    ("academy", "educational institution"): "Academy",
    ("academy", "learned society"): "Academy",
    ("press", "news media"): "Press",
    ("press", "publisher"): "Press",
    ("general", "military officer"): "General",
    ("party", "political organization"): "Party",
    ("center", "facility"): "Center",
    ("journal", "periodical"): "Journal",
    ("county", "administrative division"): "County",
    ("senate", "legislative chamber"): "Senate",
    ("supreme", "highest authority"): "Supreme",
    ("convention", "formal gathering"): "Convention",
    ("act", "legislation"): "Act",
    ("justice", "judge title"): "Justice",
    ("public", "community access"): "Public",
    ("web", "World Wide Web"): "Web",
    ("cross", "Christian symbol"): "Cross",
    ("light", "illumination"): "Light",
    ("doctor", "honorific"): "Doctor",
}


class Gap(NamedTuple):
    """One reviewed meaning; key doubles as its stable rerun identity."""

    word: str
    key: str
    domain: str
    hint: str
    pos: str = "noun"
    subtype: str | None = None
    abbreviation: str | None = None


GAPS: tuple[Gap, ...] = (
    Gap(
        "constitution",
        "governing rules",
        "government and law",
        "the fundamental rules or document establishing how a state or organization is governed",
    ),
    Gap(
        "constitution",
        "physical makeup",
        "health and physiology",
        "a person's physical makeup and capacity to remain healthy or withstand hardship",
    ),
    Gap(
        "congress",
        "legislature",
        "government",
        "a national legislative body, including the United States Congress",
    ),
    Gap(
        "congress",
        "formal assembly",
        "professional and political meetings",
        "a formal assembly of delegates or representatives for discussion",
    ),
    Gap(
        "academy",
        "educational institution",
        "education",
        "a school or institution providing general or specialized education or training",
    ),
    Gap(
        "academy",
        "learned society",
        "scholarship and the arts",
        "a society established to promote learning, science, literature or the arts",
    ),
    Gap(
        "press",
        "news media",
        "journalism",
        "newspapers and news journalists collectively, not the act of pushing",
    ),
    Gap("press", "publisher", "publishing", "a publishing organization, as in a university press"),
    Gap(
        "general",
        "military officer",
        "military ranks",
        "a high-ranking commissioned army officer, not the adjective or a chess piece",
    ),
    Gap(
        "party",
        "political organization",
        "politics",
        "an organized political group seeking to influence or exercise government power",
    ),
    Gap(
        "center",
        "facility",
        "public and commercial facilities",
        "a building or place devoted to a particular activity or service, as in a research center",
    ),
    Gap(
        "journal",
        "periodical",
        "publishing",
        "a periodical containing scholarly or professional articles",
    ),
    Gap(
        "journal",
        "personal record",
        "personal writing",
        "a regularly kept written record of personal experiences, observations or activities",
    ),
    Gap(
        "county",
        "administrative division",
        "government and geography",
        "a territorial administrative division within a country or state",
    ),
    Gap(
        "senate",
        "legislative chamber",
        "government",
        "a legislative chamber, commonly the upper house of a legislature",
    ),
    Gap(
        "supreme",
        "highest authority",
        "authority and rank",
        "highest in authority, rank or degree",
        pos="adjective",
    ),
    Gap(
        "convention",
        "formal gathering",
        "organized meetings",
        "a large formal meeting of people with shared professional, political or cultural interests; include popular-culture conventions",
    ),
    Gap(
        "convention",
        "established custom",
        "social customs",
        "an established practice or accepted way of behaving or doing something",
    ),
    Gap(
        "act", "legislation", "law", "a law formally enacted by a legislature, not merely an action"
    ),
    Gap(
        "justice",
        "judge title",
        "judicial offices",
        "a judge, especially a member of a supreme court; also used as a title before a judge's name",
    ),
    Gap(
        "public",
        "community access",
        "public life",
        "relating to the community generally, or open or available to people generally rather than private",
        pos="adjective",
    ),
    Gap(
        "web",
        "World Wide Web",
        "internet technology",
        "the system of interlinked websites accessed over the internet, not a spider's web",
    ),
    Gap(
        "cross",
        "shape",
        "shapes and symbols",
        "a shape or mark consisting of two intersecting lines",
    ),
    Gap(
        "cross",
        "Christian symbol",
        "Christianity",
        "a representation of the structure on which Jesus was crucified, used as a Christian symbol",
    ),
    Gap(
        "light",
        "illumination",
        "physical phenomena",
        "visible radiation that makes things perceptible to sight, not a lamp or low weight",
    ),
    Gap(
        "prime",
        "main or most important",
        "importance and priority",
        "main, chief or most important, as in prime concern or prime minister",
        pos="adjective",
    ),
    Gap(
        "Mr",
        "male honorific",
        "personal titles",
        "a conventional title before a man's surname or full name without specifying marital status",
        subtype="honorific",
    ),
    Gap(
        "Mrs",
        "married female honorific",
        "personal titles",
        "a conventional title before the surname or full name of a married woman",
        subtype="honorific",
    ),
    Gap(
        "Ms",
        "female honorific",
        "personal titles",
        "a conventional title before a woman's surname or full name without specifying marital status",
        subtype="honorific",
    ),
    Gap(
        "doctor",
        "honorific",
        "personal titles",
        "a title used for someone holding a doctorate or for a qualified medical practitioner; distinguish the title from the medical occupation",
        subtype="honorific",
        abbreviation="Dr",
    ),
)


def sense_lists() -> tuple[SenseList, ...]:
    """Give each meaning independent tags for safe add_sense reruns."""
    return tuple(
        SenseList(
            level=DIFFICULTY_LEVEL,
            domain=gap.domain,
            label=gap.key,
            tags=("capitalized-token-gaps", f"token-gap:{gap.word}:{gap.key}"),
            entries=(
                SenseEntry(
                    gap.word,
                    hint=gap.hint,
                    pos=gap.pos,
                    prominence="common",
                    abbreviation=gap.abbreviation,
                ),
            ),
            pos_subtype=gap.subtype,
        )
        for gap in GAPS
    )


def attach_capitalized_variant(session: Session, gap: Gap, guid: str) -> None:
    """Attach the reviewed token to precisely the sense returned by add_sense."""
    capitalized = CAPITALIZED_SENSES.get((gap.word, gap.key))
    if capitalized is None:
        return
    lemma = session.query(Lemma).filter_by(guid=guid).one()
    if lemma.pos_type != gap.pos:
        raise ValueError(f"{guid}: expected {gap.pos}, got {lemma.pos_type}")
    slot = {"noun": "noun/en_singular", "adjective": "adjective/en_positive"}[gap.pos]
    add_variant_form(
        session,
        lemma,
        variant_form_text=capitalized,
        language_code="en",
        variant_key=capitalized,
        grammatical_form=slot,
        is_base_form=True,
        notes="Capitalized in titles or institutional names; reviewed for this sense.",
        source=SOURCE,
    )


def main() -> int:
    """Preview locally, or persist each sense and its capitalization variant."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--db-path")
    parser.add_argument("--limit", type=int, help="Maximum senses across the whole list")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    selected = list(zip(GAPS, sense_lists()))[: args.limit]
    for gap, sense_list in selected:
        print_sense_plan(sense_list)
        capitalized = CAPITALIZED_SENSES.get((gap.word, gap.key))
        if capitalized:
            print(f"  spelling variant: {capitalized}")
    if not args.execute:
        print("Preview only: no model calls or database writes.")
        return 0
    config = DataSourceConfig(sqlite_path=args.db_path, model=args.model)
    print(f"Minor backup: {create_backup(config, label='capitalized-gaps')}")
    failures = 0
    with create_session(config) as session:
        for gap, sense_list in selected:
            try:
                result = add_sense(
                    session,
                    gap.word,
                    domain=gap.domain,
                    disambiguation=gap.key,
                    config=config,
                    hint=gap.hint,
                    difficulty_level=DIFFICULTY_LEVEL,
                    tags=sense_list.tags,
                    abbreviation=gap.abbreviation,
                    pos_subtype=gap.subtype,
                    pos_type=gap.pos,
                    sense_prominence="common",
                    source=SOURCE,
                )
                if result.status == "error" or result.guid is None:
                    raise RuntimeError(result.error or f"No GUID returned: {result.status}")
                attach_capitalized_variant(session, gap, result.guid)
                session.commit()
                print(f"{gap.word} ({gap.key}): {result.status} {result.guid}", flush=True)
                if result.missing_languages:
                    print(f"  Missing translations: {', '.join(result.missing_languages)}")
            except Exception as error:
                session.rollback()
                failures += 1
                print(f"{gap.word} ({gap.key}): failed: {error}", file=sys.stderr, flush=True)
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
