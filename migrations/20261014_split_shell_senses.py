#!/usr/bin/env python3
"""Split noun "shell" into a general covering, seashell and carapace.

shell (N03_103) was "a hard outer covering of an animal, especially a mollusk,
crustacean, egg, or nut", filed under body_part; the subtype review then wanted
it in animal.  Most languages have one broad word for the covering of an egg or
a nut that is also the one in "come out of one's shell" (coquille, guscio,
kabuk, kiautas, 壳), so shell keeps that sense and its translations and moves to
natural_object, which gives it a new GUID.  The other two meanings get their
own words, which most languages also have:

- seashell: the shell of a sea creature, found on a beach (concha, coquillage,
  conchiglia, Muschel, kriauklė, 贝壳), natural_object, with beach and rock
  in Nature and Landscape.
- carapace: a turtle's or crab's armor (caparazón, carapace, Panzer, šarvas),
  body_part, with claw in Advanced Biology and Anatomy.

The pt translation of shell is concha, which belongs to seashell; it should be
casca.  The new senses have no translations; run the translation agent on them
after.  shell is skipped once it carries the new definition and subtype, and an
addition is skipped when a noun with its text exists, so the script is safe to
rerun.

Defaults to a rollback-only preview.  Use --apply after reviewing the plan.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy.orm import Session

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.lemma import add_lemma, handle_lemma_type_subtype_change
from storage.crud.operation_log import FieldChange, log_entity_operation, log_field_changes
from storage.models.schema import Lemma
from storage.utils.guid import run_lemma_write

SOURCE = "migration/20261014-split-shell-senses"

SHELL_GUID = "N03_103"
SHELL_DEFINITION = (
    "A hard outer covering, such as that of an egg, a nut or a snail " "(come out of one's shell)."
)
SHELL_SUBTYPE = "natural_object"


@dataclass(frozen=True)
class NewSense:
    """A meaning of the old shell that gets its own word."""

    lemma_text: str
    definition: str
    pos_subtype: str
    level: int


ADDED: Tuple[NewSense, ...] = (
    NewSense(
        "seashell",
        "The shell of a sea creature such as a clam or a sea snail, especially one "
        "found on a beach.",
        "natural_object",
        135,
    ),
    NewSense(
        "carapace",
        "The hard shell on the back of a turtle, a crab or a similar animal.",
        "body_part",
        1010,
    ),
)


def narrow_shell(session: Session) -> Optional[Lemma]:
    """Give shell its general sense and subtype; None when already done."""
    lemma = session.query(Lemma).filter(Lemma.guid == SHELL_GUID).one_or_none()
    if lemma is None:
        lemma = (
            session.query(Lemma)
            .filter(
                Lemma.lemma_text == "shell",
                Lemma.pos_type == "noun",
                Lemma.definition_text == SHELL_DEFINITION,
                Lemma.pos_subtype == SHELL_SUBTYPE,
            )
            .one_or_none()
        )
        if lemma is not None:
            return None
        raise ValueError(f"{SHELL_GUID} is gone and no narrowed shell exists; refusing to guess")
    if lemma.lemma_text != "shell":
        raise ValueError(f"{SHELL_GUID} is not 'shell'; refusing to edit it")
    if lemma.definition_text != SHELL_DEFINITION:
        log_field_changes(
            session,
            source=SOURCE,
            operation_type="lemma_update",
            entity_guid=lemma.guid,
            lemma_id=lemma.id,
            changes=[FieldChange("definition_text", lemma.definition_text, SHELL_DEFINITION)],
        )
        lemma.definition_text = SHELL_DEFINITION
    if lemma.pos_subtype != SHELL_SUBTYPE:
        handle_lemma_type_subtype_change(
            session,
            lemma,
            lemma.pos_type,
            SHELL_SUBTYPE,
            source=SOURCE,
            notes="General covering sense; seashell and carapace split off.",
        )
    return lemma


def add_sense(session: Session, sense: NewSense) -> Optional[Lemma]:
    """Add one split-off meaning, unless a noun with its text exists."""
    existing = (
        session.query(Lemma)
        .filter(Lemma.lemma_text == sense.lemma_text, Lemma.pos_type == "noun")
        .first()
    )
    if existing is not None:
        return None
    lemma = add_lemma(
        session,
        lemma_text=sense.lemma_text,
        definition_text=sense.definition,
        pos_type="noun",
        pos_subtype=sense.pos_subtype,
        difficulty_level=sense.level,
        notes=f"Split from shell ({SHELL_GUID}); translations needed.",
    )
    log_entity_operation(
        session,
        source=SOURCE,
        operation_type="lemma_create",
        entity_guid=lemma.guid,
        lemma_id=lemma.id,
        fact={
            "lemma_text": lemma.lemma_text,
            "pos_subtype": lemma.pos_subtype,
            "difficulty_level": lemma.difficulty_level,
            "split_from": SHELL_GUID,
        },
    )
    return lemma


def migrate(config: DataSourceConfig, *, apply: bool = False) -> int:
    """Preview or commit the split in a single transaction."""
    session = create_session(config)

    def write_all() -> int:
        shell = narrow_shell(session)
        if shell is None:
            print("shell: already narrowed")
        else:
            print(
                f"shell: {SHELL_GUID} -> {shell.guid} ({shell.pos_subtype}), {shell.definition_text!r}"
            )
        added = 0
        for sense in ADDED:
            lemma = add_sense(session, sense)
            if lemma is None:
                print(f"{sense.lemma_text}: already exists")
                continue
            added += 1
            print(
                f"{lemma.guid}: {lemma.lemma_text} ({lemma.pos_subtype}) "
                f"at level {lemma.difficulty_level}"
            )
        return added

    try:
        # The subtype move and the new lemmas take GUIDs, so all of it runs
        # under the lemma write lock.
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
