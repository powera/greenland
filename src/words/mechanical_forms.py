#!/usr/bin/env python3

"""Generate derivative forms that follow mechanically from spelling.

The rule-based builders in ``langtools`` reproduce most paradigms from a word
plus its stored grammar facts.  Forms a rule can regenerate do not need to be
stored in ``data/release``; this script puts them back after a release import,
so the release files only have to carry the ones the rules cannot derive.

Currently covers English (nouns, adjectives, adverbs, verbs), Lithuanian
(nouns, adjectives, adverbs, verbs), French (nouns, adjectives, verbs) and both stored Spanish
varieties, es and es-419 (nouns, adjectives, verbs).  For English the lemma text is the word; for
the others it is the lemma's translation into that language -- es-419 has its
own translations, so it is conjugated from its own text rather than from es's.

No LLM is involved.  The builders are called directly rather than through
``LinguisticClient``, whose ``query_*_forms`` entry points fall back to a model
when the rules decline.  Here a declining rule means "skip this lemma", which
is the whole point: a word the rules are unsure about is a word whose forms
belong in ``data/release``.

Run it against a database that already holds lemmas and grammar facts -- the
builders read countability, number_type, gradability, irregular forms and the
Lithuanian principal parts per lemma, and those facts are themselves loaded
from the release files.

Some builders also report what they worked out about the paradigm.  Lithuanian
``decline_noun`` infers gender from the ending it matched, and that is written
back as a ``grammatical_gender`` fact when the noun has none: gender is
recomputable, but it is also what other languages get from an LLM, and a
release file holding only the exceptions would read as "no fact" for every
regular noun rather than "regular".  A noun whose gender was already stored
keeps it -- that fact is what selected the pattern, so re-reporting it would
claim the generator derived what it was told.

Existing forms and facts are never overwritten, so re-running is safe and
additive.

The session-wide pass preloads each batch's builder inputs and bulk-writes
tokens, forms, derived facts and operation logs. Interactive single-lemma
generation continues to use the ordinary CRUD path.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session, object_session

from langtools import mechanical_forms
from langtools.mechanical_forms import (
    build_for_lemma_with_metadata,
    is_mechanically_safe_translation,
    resolve_grammatical_form,
)
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.grammar_fact import add_grammar_fact, get_grammar_fact_value
from storage.crud.operation_log import log_operation
from storage.crud.word_token import add_word_token
from storage.models.schema import DerivativeForm, Lemma
from storage.models.variant_form import VariantForm
from words.mechanical_batch import MechanicalBatch, current_batch

__all__ = [
    "BASE_FORM_KEY",
    "SUPPORTED",
    "build_for_lemma",
    "build_for_lemma_with_metadata",
    "derivable_variant_slots",
    "generate",
    "generate_for_session",
    "generate_lemma_forms",
    "generate_variant_forms",
    "resolve_grammatical_form",
]

# The per-language rules live in langtools/<lang>/mechanical.py; see
# langtools.mechanical_forms for the contract.

# Which (language, POS) pairs have a rule-based builder at all.  A builder
# returns None for input it cannot inflect reliably (multi-word phrases,
# loanword endings, proper nouns), and that lemma keeps its stored forms.
SUPPORTED: Dict[str, Tuple[str, ...]] = mechanical_forms.supported()

# The form that carries is_base_form, per (language, POS).
BASE_FORM_KEY: Dict[Tuple[str, str], str] = mechanical_forms.base_form_keys()

# Paradigm metadata worth keeping as a grammar fact, mapped from the builder's
# key to the registered fact_type.  ``declension_class`` is deliberately absent:
# it is the one fact the registry keeps out of data/release, because
# decline_noun recomputes it from the noun plus its gender.
METADATA_FACT_TYPES: Dict[str, str] = {"gender": "grammatical_gender"}


def build_for_lemma(
    session: Session, lemma: Lemma, language_code: str = "en"
) -> Optional[Dict[str, str]]:
    """Return the mechanical paradigm for *lemma* in *language_code*, or None.

    For English the lemma text is the word itself; for other languages the
    word is the lemma's translation, so a lemma with no translation in that
    language has nothing to inflect.

    Callers that also want the paradigm metadata a builder inferred (Lithuanian
    gender, say) should use :func:`build_for_lemma_with_metadata`.
    """
    return build_for_lemma_with_metadata(session, lemma, language_code)[0]


def _build_variant_paradigm(
    session: Session, lemma: Lemma, base_form: VariantForm, language_code: str
) -> Optional[Dict[str, str]]:
    """Inflect one variant's base form with the builder its lemma would use.

    A variant is the same lexeme spelled differently, so it inflects by the
    same rules: "grey" gives "greyer"/"greyest" exactly as "gray" gives
    "grayer"/"grayest".  Only the spelling of the base form differs, and that
    spelling is the one thing no rule can derive -- nothing takes "gray" to
    "grey" -- which is why the base form itself is always kept in the release
    files and only its inflections are regenerated here.

    Returns None when the variant's base form does not occupy a slot the
    builders model.  Compass words are stored as ``adjective/en_base``, a
    placeholder slot with no paradigm behind it, and inflecting it would invent
    forms rather than recover them.
    """
    # Only English has variant rules (langtools/en/mechanical.py).  Other
    # languages' variants take their word from the lemma's translation, which
    # is the lemma's spelling and not the variant's; there is no equivalent of
    # lemma_text to substitute.  Nothing writes one today.
    pos_type = lemma.pos_type.lower()
    base_key = BASE_FORM_KEY.get((language_code, pos_type))
    expected_base_slot = (
        resolve_grammatical_form(language_code, pos_type, base_key) if base_key else None
    )
    if not expected_base_slot or base_form.grammatical_form != expected_base_slot:
        return None

    text = (base_form.variant_form_text or "").strip()
    if not text or not is_mechanically_safe_translation(text):
        return None

    return mechanical_forms.build_variant_paradigm(session, lemma, language_code, text)


def derivable_variant_slots(variant_form: VariantForm) -> frozenset[str]:
    """The slots :func:`generate_variant_forms` would rebuild for this paradigm.

    Takes any row of a variant paradigm and reports what regenerating that
    paradigm would produce, so the release export can withhold exactly those
    and no more.  Empty when the rules decline the variant -- the caller must
    then keep every form it has, since nothing would put them back.

    Uses the paradigm's own base form as the input, not the row passed in: an
    inflection is derived from the base form, never from another inflection.
    """
    lemma = variant_form.lemma
    if lemma is None:
        return frozenset()

    session = object_session(variant_form)
    if session is None:
        return frozenset()

    base_form = (
        session.query(VariantForm)
        .filter(
            VariantForm.lemma_id == variant_form.lemma_id,
            VariantForm.language_code == variant_form.language_code,
            VariantForm.variant_kind == variant_form.variant_kind,
            VariantForm.variant_key == variant_form.variant_key,
            VariantForm.is_base_form.is_(True),
        )
        .first()
    )
    if base_form is None:
        return frozenset()

    paradigm = _build_variant_paradigm(session, lemma, base_form, variant_form.language_code)
    if not paradigm:
        return frozenset()

    pos_type = lemma.pos_type.lower()
    slots = {
        resolve_grammatical_form(variant_form.language_code, pos_type, form_key)
        for form_key in paradigm
    }
    return frozenset(slot for slot in slots if slot is not None)


def generate_variant_forms(
    session: Session, language_code: str, dry_run: bool = False, batch_size: Optional[int] = None
) -> Dict[str, int]:
    """Add the mechanically-derivable inflections of each variant paradigm.

    Mirrors the lemma pass: a variant's base form is the irreducible fact and
    stays in ``data/release``, while the slots a rule reproduces are rebuilt
    here so the release does not carry "greyer" beside a "grayer" it withholds.

    Only inflections are ever written; a base form is read, never created.
    """
    from sqlalchemy.orm import selectinload

    if batch_size is not None and batch_size < 1:
        raise ValueError("batch_size must be positive")
    counts = {"variants_seen": 0, "forms_added": 0, "rules_declined": 0}
    base_ids = [
        row.id
        for row in session.query(VariantForm.id)
        .filter(VariantForm.language_code == language_code, VariantForm.is_base_form.is_(True))
        .order_by(VariantForm.id)
    ]
    chunk_size = batch_size or 100
    for start in range(0, len(base_ids), chunk_size):
        base_forms = (
            session.query(VariantForm)
            .options(selectinload(VariantForm.lemma))
            .filter(VariantForm.id.in_(base_ids[start : start + chunk_size]))
            .order_by(VariantForm.id)
            .all()
        )
        lemma_ids = sorted({row.lemma_id for row in base_forms})
        existing: dict[tuple[int, str, str], set[str]] = {}
        for row in session.query(
            VariantForm.lemma_id,
            VariantForm.variant_kind,
            VariantForm.variant_key,
            VariantForm.grammatical_form,
        ).filter(VariantForm.lemma_id.in_(lemma_ids), VariantForm.language_code == language_code):
            existing.setdefault((row.lemma_id, row.variant_kind, row.variant_key), set()).add(
                row.grammatical_form
            )
        with MechanicalBatch(session, lemma_ids, language_code) as batch:
            for base_form in base_forms:
                counts["variants_seen"] += 1
                lemma = base_form.lemma
                if lemma is None:
                    continue
                paradigm = _build_variant_paradigm(session, lemma, base_form, language_code)
                if not paradigm:
                    counts["rules_declined"] += 1
                    continue
                slots = existing.setdefault(
                    (lemma.id, base_form.variant_kind, base_form.variant_key), set()
                )
                for form_key, form_text in paradigm.items():
                    grammatical_form = resolve_grammatical_form(
                        language_code, lemma.pos_type.lower(), form_key
                    )
                    if grammatical_form is None or grammatical_form in slots:
                        continue
                    if not form_text or not form_text.strip():
                        continue
                    if not dry_run:
                        batch.variants.append(
                            dict(
                                lemma_id=lemma.id,
                                language_code=language_code,
                                variant_kind=base_form.variant_kind,
                                variant_key=base_form.variant_key,
                                grammatical_form=grammatical_form,
                                variant_form_text=form_text,
                                is_base_form=False,
                                verified=False,
                                grammatical_gender=base_form.grammatical_gender,
                            )
                        )
                        slots.add(grammatical_form)
                    counts["forms_added"] += 1
            if not dry_run:
                batch.flush()
        if batch_size and not dry_run:
            session.commit()
    return counts


def generate(
    config: DataSourceConfig,
    dry_run: bool = False,
    languages: Optional[List[str]] = None,
    pos_types: Optional[List[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Add missing mechanical forms for every supported language.

    Opens a session from *config* and hands it to :func:`generate_for_session`.
    Callers that already hold a session -- the golden loader works against an
    temporary database owned by the JSONL storage -- should call that
    directly.

    Returns per-language counts of lemmas examined, forms written, and lemmas
    the rules declined to inflect.
    """
    session = create_session(config)
    try:
        return generate_for_session(
            session, dry_run=dry_run, languages=languages, pos_types=pos_types
        )
    finally:
        session.close()


def generate_lemma_forms(
    session: Session, lemma: Lemma, language_code: str = "en", dry_run: bool = False
) -> Dict[str, int]:
    """Add the missing mechanical forms of one lemma, without committing.

    The per-lemma step of :func:`generate_for_session`, also called when a
    lemma is created so it starts with its regular forms rather than waiting
    for the next full pass.  A lemma whose POS has no builder, or whose text
    the rules decline, gets nothing.

    Returns counts keyed like the session-wide stats: ``lemmas_written``,
    ``forms_added``, ``rules_declined`` and ``facts_added``.
    """
    counts = {"lemmas_written": 0, "forms_added": 0, "rules_declined": 0, "facts_added": 0}
    batch = current_batch(session)
    pos_type = lemma.pos_type.lower()
    if pos_type not in SUPPORTED.get(language_code, ()):
        counts["rules_declined"] += 1
        return counts

    paradigm, metadata = build_for_lemma_with_metadata(session, lemma, language_code)
    if not paradigm:
        counts["rules_declined"] += 1
        return counts

    # Persist what the builder worked out about the paradigm.  The gender
    # decline_noun infers is worth storing even though it is recomputable:
    # other languages get gender from an LLM, and a release file that carried
    # only the exceptions would be read as "no fact" for every regular noun
    # rather than "regular".
    for metadata_key, fact_type in METADATA_FACT_TYPES.items():
        fact_value = metadata.get(metadata_key)
        if not fact_value:
            continue
        value = (
            batch.inputs.fact_value(lemma.id, language_code, fact_type)
            if batch
            else get_grammar_fact_value(session, lemma.id, language_code, fact_type)
        )
        if value:
            continue
        if not dry_run:
            if batch:
                batch.add_fact(lemma.id, fact_type, fact_value)
            else:
                add_grammar_fact(
                    session,
                    lemma_id=lemma.id,
                    language_code=language_code,
                    fact_type=fact_type,
                    fact_value=fact_value,
                    notes="derived mechanically by generate_mechanical_forms",
                )
        counts["facts_added"] += 1

    existing = (
        set(batch.inputs.forms.get((lemma.id, language_code), {}))
        if batch
        else {
            row.grammatical_form
            for row in session.query(DerivativeForm).filter(
                DerivativeForm.lemma_id == lemma.id,
                DerivativeForm.language_code == language_code,
            )
        }
    )

    added = 0
    for form_key, form_text in paradigm.items():
        grammatical_form = resolve_grammatical_form(language_code, pos_type, form_key)
        if grammatical_form is None or grammatical_form in existing:
            continue
        if not form_text or not form_text.strip():
            continue

        if not dry_run:
            if batch:
                batch.forms.append(
                    dict(
                        lemma_id=lemma.id,
                        derivative_form_text=form_text,
                        language_code=language_code,
                        grammatical_form=grammatical_form,
                        is_base_form=(form_key == BASE_FORM_KEY.get((language_code, pos_type))),
                        verified=False,
                    )
                )
            else:
                token = add_word_token(session, form_text, language_code)
                session.add(
                    DerivativeForm(
                        lemma_id=lemma.id,
                        derivative_form_text=form_text,
                        word_token_id=token.id,
                        language_code=language_code,
                        grammatical_form=grammatical_form,
                        is_base_form=(form_key == BASE_FORM_KEY.get((language_code, pos_type))),
                        verified=False,
                    )
                )
        added += 1

    if added:
        counts["lemmas_written"] += 1
        counts["forms_added"] += added
        if not dry_run:
            details = {
                "language_code": language_code,
                "pos_type": pos_type,
                "forms_added": added,
                "generator": f"langtools.{language_code} {pos_type}",
            }
            if batch:
                batch.add_log(lemma.id, details)
            else:
                log_operation(
                    session,
                    operation_type="mechanical_forms_generated",
                    source="generate_mechanical_forms",
                    entity_type="derivative_form",
                    lemma_id=lemma.id,
                    details=details,
                )
    return counts


def generate_for_session(
    session: Session,
    dry_run: bool = False,
    languages: Optional[List[str]] = None,
    pos_types: Optional[List[str]] = None,
    batch_size: Optional[int] = None,
) -> Dict[str, Dict[str, int]]:
    """Add missing mechanical forms to an already-open session.

    The session is committed (unless *dry_run*) but not closed: it belongs to
    the caller.

    *pos_types* narrows the run to those parts of speech (default: every one
    the language supports).  Variant forms are skipped when it is given: they
    are rebuilt per language, not per part of speech.

    When batch_size is provided, commit after that many lemmas/variants so
    hosted startup does not hold one write transaction for the full dictionary.
    Otherwise, plan/write in batches of 100 while committing only at the end.
    Existing forms and facts are never overwritten, so this is additive and
    safe to re-run against a database that has already been generated into.
    """
    if batch_size is not None and batch_size < 1:
        raise ValueError("batch_size must be positive")
    selected = languages or list(SUPPORTED)
    stats: Dict[str, Dict[str, int]] = {}

    for language_code in selected:
        language_pos_types = [
            pos for pos in SUPPORTED[language_code] if pos_types is None or pos in pos_types
        ]
        counts = {
            "lemmas_seen": 0,
            "lemmas_written": 0,
            "forms_added": 0,
            "rules_declined": 0,
            "facts_added": 0,
        }
        stats[language_code] = counts

        lemma_ids = [
            row.id
            for row in session.query(Lemma.id)
            .filter(Lemma.pos_type.in_(language_pos_types))
            .order_by(Lemma.id)
        ]
        chunk_size = batch_size or 100
        for start in range(0, len(lemma_ids), chunk_size):
            chunk_ids = lemma_ids[start : start + chunk_size]
            lemmas = session.query(Lemma).filter(Lemma.id.in_(chunk_ids)).order_by(Lemma.id).all()
            with MechanicalBatch(session, chunk_ids, language_code) as batch:
                for lemma in lemmas:
                    counts["lemmas_seen"] += 1
                    lemma_counts = generate_lemma_forms(
                        session, lemma, language_code, dry_run=dry_run
                    )
                    for count_key, count_value in lemma_counts.items():
                        counts[count_key] += count_value
                if not dry_run:
                    batch.flush()
            if batch_size and not dry_run:
                session.commit()

        # A variant inflects by the same rules as the lemma it belongs to,
        # so its derivable slots are rebuilt here too -- otherwise the
        # release would ship "greyer" beside a "grayer" it withholds.
        if pos_types is None:
            counts["variant_forms_added"] = generate_variant_forms(
                session, language_code, dry_run=dry_run, batch_size=batch_size
            )["forms_added"]

    if not dry_run:
        session.commit()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate mechanically-derivable English forms (no LLM calls)"
    )
    parser.add_argument("--db-path", required=True, help="Path to the SQLite database")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be added, write nothing"
    )
    parser.add_argument(
        "--language",
        dest="languages",
        action="append",
        choices=sorted(SUPPORTED),
        help="Limit to one language (repeatable; default: every supported language)",
    )
    parser.add_argument(
        "--pos",
        dest="pos_types",
        action="append",
        choices=sorted({pos for pos_types in SUPPORTED.values() for pos in pos_types}),
        help="Limit to one part of speech (repeatable; default: every supported one)",
    )
    args = parser.parse_args()

    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)
    stats = generate(
        config, dry_run=args.dry_run, languages=args.languages, pos_types=args.pos_types
    )

    prefix = "would add" if args.dry_run else "added"
    total = 0
    for language_code, counts in sorted(stats.items()):
        total += counts["forms_added"]
        print(
            f"  {language_code}: {counts['lemmas_seen']:5} lemmas examined, "
            f"{counts['rules_declined']:5} declined, "
            f"{prefix} {counts['forms_added']:6} forms "
            f"across {counts['lemmas_written']} lemmas"
            + (f", {counts['facts_added']} grammar facts" if counts["facts_added"] else "")
        )
    print(f"  total forms {prefix}: {total}")


if __name__ == "__main__":
    main()
