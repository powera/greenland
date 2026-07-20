#!/usr/bin/env python3
"""Generate English noun/adjective/adverb derivative forms mechanically.

Drives the rule-based builders in ``langtools.en.inflection`` directly and
writes the results as ``DerivativeForm`` rows.  Lemmas the rules decline to
handle are skipped rather than sent to an LLM: the bulk of them are proper
nouns ("Amsterdam", "February") that have no useful plural, and guessing at
the rest would store worse data than storing nothing.

Verbs are not handled here — they already go through
``langtools.en.conjugation`` via vilkas.

Usage:
    PYTHONPATH=src python3 scripts/generate_en_mechanical_forms.py
    PYTHONPATH=src python3 scripts/generate_en_mechanical_forms.py --yes

Runs as a dry run unless ``--yes`` is given.  Re-running is safe: a lemma that
already has a form for a given grammatical form is left untouched.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, NamedTuple, Optional, Tuple

if str(Path(__file__).parent.parent / "src") not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from langtools.en.inflection import (
    build_adjective_forms,
    build_adverb_forms,
    build_noun_forms,
)
from langtools.form_registry import FORM_SPECS
from storage.crud.derivative_form import add_derivative_form
from storage.models.schema import DerivativeForm, Lemma

LANGUAGE_CODE = "en"
GENERATION_NOTE = "mechanical langtools.en.inflection"


class Plan(NamedTuple):
    """One form the generator intends to write."""

    lemma: Lemma
    form_name: str
    grammatical_form: str
    form_text: str


def load_facts(session: Session) -> Dict[int, Dict[str, str]]:
    """Map ``lemma_id -> {fact_type: fact_value}`` for English grammar facts."""
    from storage.models.grammar_fact import GrammarFact

    facts: Dict[int, Dict[str, str]] = defaultdict(dict)
    rows = session.query(GrammarFact).filter(GrammarFact.language_code == LANGUAGE_CODE).all()
    for row in rows:
        if row.fact_value is not None:
            facts[row.lemma_id][row.fact_type] = row.fact_value
    return facts


def build_for(lemma: Lemma, lemma_facts: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Run the builder matching *lemma*'s part of speech."""
    pos_type = (lemma.pos_type or "").strip().lower()
    if pos_type == "noun":
        return build_noun_forms(
            lemma.lemma_text,
            countability=lemma_facts.get("countability"),
            number_type=lemma_facts.get("number_type"),
            irregular_plural=lemma_facts.get("plural"),
        )
    builder: Optional[Callable[..., Optional[Dict[str, str]]]] = {
        "adjective": build_adjective_forms,
        "adverb": build_adverb_forms,
    }.get(pos_type)
    if builder is None:
        return None
    return builder(
        lemma.lemma_text,
        gradability=lemma_facts.get("gradability"),
        comparative=lemma_facts.get("comparative"),
        superlative=lemma_facts.get("superlative"),
    )


def existing_forms(session: Session) -> Dict[Tuple[int, str], str]:
    """Index the English forms already stored, by ``(lemma_id, grammatical_form)``."""
    rows = session.query(DerivativeForm).filter(DerivativeForm.language_code == LANGUAGE_CODE).all()
    return {(row.lemma_id, row.grammatical_form): row.derivative_form_text for row in rows}


def build_plan(session: Session) -> Tuple[List[Plan], List[Lemma], List[Plan]]:
    """Return ``(to_write, skipped_lemmas, already_present)``."""
    facts = load_facts(session)
    present = existing_forms(session)

    to_write: List[Plan] = []
    skipped: List[Lemma] = []
    already: List[Plan] = []

    lemmas = (
        session.query(Lemma)
        .filter(Lemma.pos_type.in_(["noun", "adjective", "adverb"]))
        .order_by(Lemma.id)
        .all()
    )

    for lemma in lemmas:
        forms = build_for(lemma, facts.get(lemma.id, {}))
        if not forms:
            skipped.append(lemma)
            continue

        mapping = FORM_SPECS[(LANGUAGE_CODE, lemma.pos_type.strip().lower())].form_mapping
        for form_name, form_text in forms.items():
            grammatical_form = mapping.get(form_name)
            if grammatical_form is None:
                continue
            value = str(getattr(grammatical_form, "value", grammatical_form))
            plan = Plan(lemma, form_name, value, form_text)
            if (lemma.id, value) in present:
                already.append(plan)
                continue
            to_write.append(plan)

    return to_write, skipped, already


def report(to_write: List[Plan], skipped: List[Lemma], already: List[Plan]) -> None:
    by_form: Dict[str, int] = defaultdict(int)
    for plan in to_write:
        by_form[plan.grammatical_form] += 1

    print(f"Forms to write: {len(to_write)}")
    for grammatical_form, count in sorted(by_form.items()):
        print(f"  {grammatical_form:28s} {count}")
    print()
    print(f"Already present (left untouched): {len(already)}")
    print()

    by_pos: Dict[str, List[str]] = defaultdict(list)
    for lemma in skipped:
        by_pos[lemma.pos_type].append(lemma.lemma_text)
    print(f"Skipped — rules declined, not sent to an LLM: {len(skipped)}")
    for pos_type, texts in sorted(by_pos.items()):
        preview = ", ".join(sorted(texts)[:12])
        print(f"  {pos_type} ({len(texts)}): {preview}...")
    print()


def apply_plan(session: Session, to_write: List[Plan]) -> int:
    written = 0
    for plan in to_write:
        add_derivative_form(
            session,
            lemma=plan.lemma,
            derivative_form_text=plan.form_text,
            language_code=LANGUAGE_CODE,
            grammatical_form=plan.grammatical_form,
            is_base_form=plan.form_name in ("singular", "positive"),
            verified=False,
            notes=GENERATION_NOTE,
        )
        written += 1
    session.commit()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default="data/wordfreq/linguistics.sqlite",
        help="Path to SQLite database (default: data/wordfreq/linguistics.sqlite)",
    )
    parser.add_argument("--yes", action="store_true", help="Write the forms (default: dry run)")
    args = parser.parse_args()

    engine = create_engine(f"sqlite:///{args.db}")
    with Session(engine) as session:
        to_write, skipped, already = build_plan(session)
        report(to_write, skipped, already)

        if not args.yes:
            print("Dry run complete; re-run with --yes to write these forms.")
            return 0

        written = apply_plan(session, to_write)
        print(f"Wrote {written} derivative forms.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
