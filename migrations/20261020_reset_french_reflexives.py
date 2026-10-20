#!/usr/bin/env python3
"""Reset ten malformed French reflexive paradigms and regenerate without an LLM.

Defaults to a read-only preview. --apply takes a major backup before deleting
any forms, then replaces only the ten named French verb paradigms in one
transaction. Correct paradigms are skipped, making reruns safe.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

if str(Path(__file__).resolve().parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy.orm import Session

from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.backup import create_backup
from storage.crud.grammar_fact import get_verb_form_overrides
from storage.crud.operation_log import DERIVATIVE_FORM_DELETE, log_entity_operation
from storage.models.schema import DerivativeForm, Lemma, LemmaTranslation
from words.mechanical_forms import build_for_lemma, generate_lemma_forms, resolve_grammatical_form

TARGETS: Dict[str, str] = {
    "vanish": "s'évanouir",
    "collapse": "s'effondrer",
    "worry": "s'inquiéter",
    "sit": "s'asseoir",
    "escape": "s'échapper",
    "approach": "s'approcher",
    "thicken": "s'épaissir",
    "self-identify": "s'identifier",
    "address": "s'adresser",
    "rocket": "s'envoler",
}


def plan_repairs(session: Session) -> List[Tuple[Lemma, List[DerivativeForm], Dict[str, str]]]:
    """Validate all candidates before scheduling any deletion."""
    repairs: List[Tuple[Lemma, List[DerivativeForm], Dict[str, str]]] = []
    candidates = (
        session.query(Lemma, LemmaTranslation)
        .join(LemmaTranslation, LemmaTranslation.lemma_id == Lemma.id)
        .filter(
            Lemma.pos_type == "verb",
            Lemma.lemma_text.in_(TARGETS),
            LemmaTranslation.language_code == "fr",
        )
        .all()
    )
    for lemma, translation in candidates:
        if translation.translation.replace("’", "'") != TARGETS[lemma.lemma_text]:
            continue
        if get_verb_form_overrides(session, lemma.id, "fr"):
            raise RuntimeError(f"Manual overrides need review: {lemma.lemma_text}")
        paradigm = build_for_lemma(session, lemma, "fr")
        if not paradigm:
            raise RuntimeError(f"Rules declined: {lemma.lemma_text}")
        expected: Dict[str, str] = {}
        for form_key, form_text in paradigm.items():
            slot = resolve_grammatical_form("fr", "verb", form_key)
            if slot is not None:
                expected[slot] = form_text
        if not expected.get("verb/fr_1s_present", "").startswith(("me ", "m'")):
            raise RuntimeError(f"Missing reflexive clitic: {lemma.lemma_text}")
        existing = (
            session.query(DerivativeForm)
            .filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == "fr",
                DerivativeForm.grammatical_form.like("verb/fr_%"),
            )
            .all()
        )
        # This repair only resets existing malformed paradigms.
        if not existing:
            continue
        if any(row.grammatical_form not in expected for row in existing):
            raise RuntimeError(f"Unrecognized slots need review: {lemma.lemma_text}")
        actual = {row.grammatical_form: row.derivative_form_text for row in existing}
        if actual == expected and len(existing) == len(expected):
            continue
        repairs.append((lemma, existing, expected))
    return repairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db-path")
    args = parser.parse_args()
    config = DataSourceConfig(sqlite_path=args.db_path)
    session = create_session(config, readonly=not args.apply)
    try:
        repairs = plan_repairs(session)
        for lemma, existing, expected in repairs:
            print(
                f"{lemma.id} {lemma.lemma_text}: reset {len(existing)} forms; generate {len(expected)}; {expected['verb/fr_1s_present']}"
            )
        if not args.apply or not repairs:
            print(f"{'Preview' if not args.apply else 'No changes'}: {len(repairs)} paradigms")
            return
        backup = create_backup(config, label="fr-reflex-reset", tier="major")
        print(f"Major backup: {backup}")
        for lemma, existing, expected in repairs:
            for old_form in existing:
                log_entity_operation(
                    session,
                    source="migration/french-reflexive-reset",
                    operation_type=DERIVATIVE_FORM_DELETE,
                    entity_guid=lemma.guid,
                    lemma_id=lemma.id,
                    fact={
                        "language_code": "fr",
                        "grammatical_form": old_form.grammatical_form,
                        "text": old_form.derivative_form_text,
                    },
                )
                session.delete(old_form)
            session.flush()
            counts = generate_lemma_forms(session, lemma, "fr")
            if counts["forms_added"] != len(expected):
                raise RuntimeError(f"Incomplete regeneration: {lemma.lemma_text}")
            persisted = (
                session.query(DerivativeForm).filter_by(lemma_id=lemma.id, language_code="fr").all()
            )
            actual = {
                row.grammatical_form: row.derivative_form_text
                for row in persisted
                if row.grammatical_form in expected
            }
            if actual != expected:
                raise RuntimeError(f"Verification failed: {lemma.lemma_text}")
        session.commit()
        print(f"Rebuilt {len(repairs)} paradigms; no LLM calls")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
