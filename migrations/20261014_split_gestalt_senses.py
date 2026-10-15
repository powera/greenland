#!/usr/bin/env python3
"""Split the noun senses the subtype review marked "gestalt" into one sense each.

The second-opinion pass of the subtype review (src/quality/subtype_review.py)
marks a sense "gestalt" when its definition runs two meanings together.  For
each one here, the existing lemma keeps one meaning (its GUID, level and
translations are untouched) and the other meaning is added as a new lemma at
the given level.  justice is narrowed only: the legal-system sense was not
wanted.  A lemma whose definition is already the narrowed text is skipped, and
an addition is skipped when a sense with that disambiguation already exists,
so the script is safe to rerun.

The new senses have no translations; run the translation agent on them after.

Defaults to a rollback-only preview.  Use --apply after reviewing the plan and
making a WAL-safe SQLite backup (sqlite3 ... ".backup <dest>").
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.lemma import add_lemma
from storage.crud.operation_log import FieldChange, log_entity_operation, log_field_changes
from storage.models.schema import Lemma
from storage.utils.guid import run_lemma_write

SOURCE = "migration/20261014-split-gestalt-senses"


@dataclass(frozen=True)
class AddedSense:
    """The meaning split off into a new lemma."""

    disambiguation: str
    definition: str
    pos_subtype: str
    level: int


@dataclass(frozen=True)
class GestaltSplit:
    """One gestalt lemma: the meaning it keeps, and the one split off, if any."""

    guid: str
    lemma_text: str
    definition: str
    #: Set on the existing lemma when it has none, so the two senses can be told apart.
    disambiguation: Optional[str]
    added: Optional[AddedSense]


SPLITS: Tuple[GestaltSplit, ...] = (
    GestaltSplit(
        "N17_114",
        "direction",
        "The way something moves or faces, such as north or left.",
        "way",
        AddedSense(
            "guidance",
            "The management or guidance of someone or something, such as a film or a project.",
            "process_event",
            450,
        ),
    ),
    GestaltSplit(
        "N17_190",
        "mark",
        "A visible spot, scratch or stain on a surface.",
        None,
        AddedSense(
            "sign",
            "A sign or indication of a quality or feeling (a mark of respect).",
            "symbolic_element",
            450,
        ),
    ),
    GestaltSplit(
        "N17_213",
        "justice",
        "The quality of being fair and reasonable.",
        None,
        None,
    ),
    GestaltSplit(
        "N17_118",
        "job",
        "A paid position of regular work.",
        "employment",
        AddedSense(
            "task",
            "A piece of work to be done (a good job, odd jobs).",
            "concept_idea",
            300,
        ),
    ),
    GestaltSplit(
        "N17_028",
        "truth",
        "What is true; the real facts about something (tell the truth).",
        "facts",
        AddedSense(
            "quality",
            "The quality of being true or accurate (the truth of a statement).",
            "quality_attribute",
            450,
        ),
    ),
    GestaltSplit(
        "N17_280",
        "waste",
        "Material that is not wanted and is thrown away.",
        "material",
        AddedSense(
            "careless use",
            "Using something carelessly or when there is no need (a waste of time).",
            "process_event",
            300,
        ),
    ),
    GestaltSplit(
        "N20_005",
        "sense",
        "One of the body's abilities to perceive: sight, hearing, smell, taste and touch.",
        None,
        AddedSense(
            "awareness",
            "A feeling or understanding of something (a sense of humour, a sense of urgency).",
            "mental_construct",
            300,
        ),
    ),
    GestaltSplit(
        "N22_024",
        "mass",
        "The amount of matter in an object, measured in kilograms.",
        None,
        AddedSense(
            "large amount",
            "A large amount or body of something (a mass of people).",
            "collection_things",
            450,
        ),
    ),
)


def narrow_existing(session: Session, split: GestaltSplit) -> List[FieldChange]:
    """Give the existing lemma its one meaning; return the fields changed."""
    lemma = session.query(Lemma).filter(Lemma.guid == split.guid).one_or_none()
    if lemma is None or lemma.lemma_text != split.lemma_text:
        raise ValueError(f"{split.guid} is not {split.lemma_text!r}; refusing to edit it")
    changes: List[FieldChange] = []
    if lemma.definition_text != split.definition:
        changes.append(FieldChange("definition_text", lemma.definition_text, split.definition))
        lemma.definition_text = split.definition
    if split.disambiguation and not lemma.disambiguation:
        changes.append(FieldChange("disambiguation", lemma.disambiguation, split.disambiguation))
        lemma.disambiguation = split.disambiguation
    log_field_changes(
        session,
        source=SOURCE,
        operation_type="lemma_update",
        entity_guid=lemma.guid,
        lemma_id=lemma.id,
        changes=changes,
    )
    return changes


def add_split_sense(session: Session, split: GestaltSplit) -> Optional[Lemma]:
    """Add the split-off meaning, unless a sense with its disambiguation exists."""
    if split.added is None:
        return None
    sense = split.added
    existing = (
        session.query(Lemma)
        .filter(
            Lemma.lemma_text == split.lemma_text,
            Lemma.pos_type == "noun",
            Lemma.disambiguation == sense.disambiguation,
        )
        .first()
    )
    if existing is not None:
        return None
    lemma = add_lemma(
        session,
        lemma_text=split.lemma_text,
        definition_text=sense.definition,
        pos_type="noun",
        pos_subtype=sense.pos_subtype,
        difficulty_level=sense.level,
        notes=f"Split from {split.guid} (subtype review gestalt); translations needed.",
    )
    lemma.disambiguation = sense.disambiguation
    log_entity_operation(
        session,
        source=SOURCE,
        operation_type="lemma_create",
        entity_guid=lemma.guid,
        lemma_id=lemma.id,
        fact={
            "lemma_text": lemma.lemma_text,
            "disambiguation": lemma.disambiguation,
            "pos_subtype": lemma.pos_subtype,
            "difficulty_level": lemma.difficulty_level,
            "split_from": split.guid,
        },
    )
    return lemma


def migrate(config: DataSourceConfig, *, apply: bool = False) -> int:
    """Preview or commit every split in a single transaction."""
    session = create_session(config)

    def write_all() -> int:
        added = 0
        for split in SPLITS:
            for change in narrow_existing(session, split):
                print(f"{split.guid} {split.lemma_text}: {change.field} -> {change.new_value!r}")
            lemma = add_split_sense(session, split)
            if lemma is not None:
                added += 1
                print(
                    f"{lemma.guid}: {lemma.lemma_text} [{lemma.disambiguation}] "
                    f"({lemma.pos_subtype}) at level {lemma.difficulty_level}"
                )
        return added

    try:
        # New lemmas take GUIDs, so the set is written under the lemma write lock.
        added = run_lemma_write(session, write_all, commit=apply)
        print(f"{'Added' if apply else 'Would add'} {added} senses.")
        return added
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH)
    parser.add_argument(
        "--apply", action="store_true", help="Commit the changes (default: rollback preview)"
    )
    args = parser.parse_args()
    migrate(
        DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path),
        apply=args.apply,
    )


if __name__ == "__main__":
    main()
