#!/usr/bin/env python3
"""Rename four verb lemmas that were stored as participles to their base form.

``scattering``, ``forming``, ``infected`` and ``tailored`` were imported as
verb lemmas, so the mechanical conjugator treated the participle as an
infinitive ("scatteringing", "will scattering"). No verb lemma exists for the
base forms, so each is renamed in place (keeping its GUID) rather than
tombstoned.

For each lemma this:

* sets ``lemma_text`` to the base form and rewrites the definition to
  describe the verb rather than the participle;
* deletes its English derivative forms -- all of them derive from the wrong
  headword -- so Vilkas regenerates them;
* deletes its translations, which were participles or past tenses
  ("esparciendo", "infectó"), so Voras regenerates them.

The stored English ``past``/``past_participle`` grammar facts are already
right for the base verbs (scattered, formed, infected, tailored) and are kept.
Sentence word hints keep their ``english_text``: that is the sentence's
surface form, which really is "scattering".

Rerunning is safe: a lemma whose text is no longer the participle is skipped,
so a second run cannot delete regenerated forms or translations.

    GREENLAND_TEST_MODE=1 python migrations/20260924_fix_participle_verb_lemmas.py --dry-run
    GREENLAND_DISABLE_LLM=1 python migrations/20260924_fix_participle_verb_lemmas.py

Afterwards regenerate forms and translations:

    GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python src/agents/vilkas.py \
        --task en-verb-conjugations --populate --throttle 0 --yes
    PYTHONPATH=src python src/agents/voras.py --populate --guid <GUID> --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy.orm import Session

from storage.backend import DataSourceConfig, create_session
from storage.crud.derivative_form import delete_derivative_form
from storage.crud.lemma import update_lemma
from storage.crud.operation_log import FieldChange, log_field_changes, log_translation_change
from storage.models.schema import DerivativeForm, Lemma, LemmaTranslation

SOURCE = "migration/20260924_fix_participle_verb_lemmas"


class LemmaFix(NamedTuple):
    guid: str
    old_text: str
    new_text: str
    definition: str


FIXES: List[LemmaFix] = [
    LemmaFix(
        "V01_104",
        "scattering",
        "scatter",
        "To throw or distribute things loosely over an area.",
    ),
    LemmaFix(
        "V02_014",
        "forming",
        "form",
        "To create, shape, or bring something into existence.",
    ),
    LemmaFix(
        "V08_022",
        "infected",
        "infect",
        "To pass a disease-causing organism, such as a virus or bacterium, to a person, "
        "animal, or thing.",
    ),
    LemmaFix(
        "V02_020",
        "tailored",
        "tailor",
        "To make or alter clothing by cutting and sewing it to fit a particular person.",
    ),
]


def fix_lemma(session: Session, fix: LemmaFix, dry_run: bool) -> None:
    lemma: Optional[Lemma] = session.query(Lemma).filter(Lemma.guid == fix.guid).first()
    if lemma is None:
        print(f"{fix.guid}: not found, skipping")
        return
    if lemma.lemma_text != fix.old_text:
        print(f"{fix.guid}: text is {lemma.lemma_text!r}, not {fix.old_text!r}; skipping")
        return

    forms = (
        session.query(DerivativeForm)
        .filter(DerivativeForm.lemma_id == lemma.id, DerivativeForm.language_code == "en")
        .all()
    )
    translations = (
        session.query(LemmaTranslation).filter(LemmaTranslation.lemma_id == lemma.id).all()
    )
    print(
        f"{fix.guid}: {fix.old_text} -> {fix.new_text}; "
        f"deleting {len(forms)} en forms, {len(translations)} translations"
    )
    if dry_run:
        return

    for form in forms:
        delete_derivative_form(session, form.id, source=SOURCE)

    for translation in translations:
        log_translation_change(
            session=session,
            source=SOURCE,
            operation_type="translation",
            lemma_id=lemma.id,
            language_code=translation.language_code,
            old_translation=translation.translation,
            new_translation=None,
        )
        session.delete(translation)

    log_field_changes(
        session,
        source=SOURCE,
        operation_type="lemma_update",
        entity_guid=lemma.guid,
        changes=[
            FieldChange("lemma_text", lemma.lemma_text, fix.new_text),
            FieldChange("definition_text", lemma.definition_text, fix.definition),
        ],
        lemma_id=lemma.id,
    )
    # update_lemma commits, which also commits the translation deletes above.
    update_lemma(session, lemma.id, lemma_text=fix.new_text, definition_text=fix.definition)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = DataSourceConfig(sqlite_path=str(args.db_path)) if args.db_path else DataSourceConfig()
    session = create_session(config)
    try:
        for fix in FIXES:
            fix_lemma(session, fix, args.dry_run)
    finally:
        session.close()


if __name__ == "__main__":
    main()
