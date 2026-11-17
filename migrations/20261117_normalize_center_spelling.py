#!/usr/bin/env python3
"""Make center primary on the two existing centre senses, preserving GUIDs.

Preview by default. --apply takes a minor WAL-safe backup, preserves the full
British paradigm as a spelling variant, and updates the English headword,
translation, derivative forms and principal parts together. Safe to rerun.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.backup import create_backup
from storage.crud.derivative_form import update_derivative_form
from storage.crud.lemma import update_lemma
from storage.crud.operation_log import FieldChange, log_field_changes
from storage.crud.variant_form import add_variant_form
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import DerivativeForm, Lemma
from storage.token_forms import link_form_to_word_token
from storage.translation_helpers import set_translation

SOURCE = "migration/20261117-center-spelling"
SPELLINGS = {
    "centre": "center",
    "centres": "centers",
    "centre's": "center's",
    "centres'": "centers'",
    "centred": "centered",
    "centring": "centering",
}


def migrate(config: DataSourceConfig, *, apply: bool = False) -> None:
    """Normalize only the reviewed GUIDs, preserving all non-English data."""
    if apply:
        print(f"Minor backup: {create_backup(config, label='center-spelling')}")
    with create_session(config, readonly=not apply) as session:
        for guid in ("N37_028", "V18_004"):
            lemma = session.query(Lemma).filter_by(guid=guid).one()
            if lemma.lemma_text == "center":
                print(f"{guid}: already center")
                continue
            if lemma.lemma_text != "centre":
                raise ValueError(f"{guid}: unexpected headword {lemma.lemma_text!r}")
            forms = (
                session.query(DerivativeForm).filter_by(lemma_id=lemma.id, language_code="en").all()
            )
            for form in forms:
                if form.derivative_form_text not in SPELLINGS:
                    raise ValueError(f"Unexpected English form: {form.derivative_form_text!r}")
            print(f"{guid}: centre -> center; preserve {len(forms)} British forms")
            if not apply:
                continue
            for form in forms:
                old_text = form.derivative_form_text
                add_variant_form(
                    session,
                    lemma,
                    old_text,
                    "en",
                    "centre",
                    form.grammatical_form,
                    is_base_form=form.is_base_form,
                    ipa_pronunciation=form.ipa_pronunciation,
                    phonetic_pronunciation=form.phonetic_pronunciation,
                    notes="British spelling; center is the primary English spelling.",
                    source=SOURCE,
                )
                update_derivative_form(
                    session, form.id, derivative_form_text=SPELLINGS[old_text], source=SOURCE
                )
                form.word_token_id = None
                link_form_to_word_token(session, form)
            for fact in (
                session.query(GrammarFact).filter_by(lemma_id=lemma.id, language_code="en").all()
            ):
                if fact.fact_type not in ("past", "past_participle"):
                    continue
                old_value = fact.fact_value
                if old_value not in SPELLINGS:
                    raise ValueError(f"Unexpected principal part: {old_value!r}")
                assert old_value is not None
                fact.fact_value = SPELLINGS[old_value]
                log_field_changes(
                    session,
                    source=SOURCE,
                    operation_type="grammar_fact_update",
                    entity_guid=lemma.guid,
                    lemma_id=lemma.id,
                    changes=[FieldChange("fact_value", old_value, fact.fact_value)],
                    extra={"language_code": "en", "fact_type": fact.fact_type},
                )
            update_lemma(session, lemma.id, lemma_text="center", source=SOURCE)
            set_translation(session, lemma, "en", "center")
        if apply:
            session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--db-path")
    args = parser.parse_args()
    migrate(DataSourceConfig(sqlite_path=args.db_path), apply=args.apply)


if __name__ == "__main__":
    main()
