#!/usr/bin/env python3
"""Preview the narrow cousin/actor/German-person migration; --apply after review.

Preview opens SQLite with mode=ro, bypassing schema initialization. Applying
backs up through storage.backup (major by default; --backup-tier can override),
adds the nullable variant gender column, then runs all data edits transactionally.
No release files are edited. Export them through the ordinary release pipeline
only after reviewing the database changes.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import create_engine, delete, func, inspect, select, text, update
from sqlalchemy.orm import Session

from langtools.form_tasks import get_base_grammatical_form
from storage.backend.config import BackendType, DataSourceConfig
from storage.backup import create_backup, database_path
from storage.backend.sqlite_pragmas import apply_sqlite_pragmas
from storage.crud.guid_tombstone import create_tombstone
from storage.crud.operation_log import FieldChange, log_entity_operation, log_field_changes
from storage.crud.variant_form import add_variant_form
from storage.models.grammar_fact import GrammarFact
from storage.models.guid_tombstone import TOMBSTONE_REASON_GENDER_VARIANT_MERGE
from storage.models.lemma_fact import LemmaFact
from storage.models.lemma_relation import LemmaRelationGroup, LemmaRelationMember
from storage.models.schema import (
    AudioQualityReview,
    Base,
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
    NON_INFLECTION_GRAMMATICAL_FORMS,
)
from storage.models.variant_form import VariantForm
from storage.variant_audio import gender_audio_slot

SOURCE = "migration/gender-variants"
COUSIN_GUID = "N35_076"
COUSIN_MERGES: Tuple[Tuple[str, str], ...] = (("N35_047", "male"), ("N35_048", "female"))

# Initial additions are deliberately limited to reviewed counterpart vocabulary.
# (guid, language) -> male singular/plural, female singular/plural.
# Defaults are the existing translations, never synthesized from the male.
COUNTERPART_SEEDS: Dict[Tuple[str, str], Tuple[str, str, str, str]] = {
    ("N36_047", "en"): ("actor", "actors", "actress", "actresses"),
    ("N36_047", "es"): ("actor", "actores", "actriz", "actrices"),
    ("N36_047", "es-419"): ("actor", "actores", "actriz", "actrices"),
    # No English entry for German: one word with no grammatical gender serves
    # both, so English is gender_variant_status "none".
    ("N33_005", "es"): ("alemán", "alemanes", "alemana", "alemanas"),
    ("N33_005", "es-419"): ("alemán", "alemanes", "alemana", "alemanas"),
}


def _grammar_gender(session: Session, lemma_id: int, language: str) -> Optional[str]:
    fact = (
        session.query(GrammarFact)
        .filter_by(lemma_id=lemma_id, language_code=language, fact_type="grammatical_gender")
        .first()
    )
    return fact.fact_value if fact else None


def _archive_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep scalar/null types while making timestamps/vectors JSON-safe."""
    result: Dict[str, Any] = json.loads(json.dumps(dict(record), default=str))
    return result


def merge_cousin(session: Session, source_guid: str, gender: str) -> bool:
    """Move one allowlisted cousin into a variant; caller owns the transaction.

    Retain surface forms, pronunciation, audio, sentence references, and GUID
    history. Unexpected dependencies fail rather than discard records. An
    operation log archives the retired lemma's metadata before deletion.
    """
    if (source_guid, gender) not in COUSIN_MERGES:
        raise ValueError("Only the explicitly selected cousin lemmas may be merged")
    source_lemma = session.query(Lemma).filter_by(guid=source_guid).first()
    if source_lemma is None:
        return False
    target = session.query(Lemma).filter_by(guid=COUSIN_GUID).one()
    if source_lemma.pos_subtype != "family_relation" or target.pos_subtype != "family_relation":
        raise ValueError("Cousin migration requires family_relation lemmas")
    if session.query(VariantForm).filter_by(lemma_id=source_lemma.id).count():
        raise ValueError(f"Review existing variants on {source_guid} before merging")

    target_groups = {
        group.relation_type: group.id
        for group in session.query(LemmaRelationGroup)
        .join(LemmaRelationMember)
        .filter(LemmaRelationMember.lemma_id == target.id)
    }
    for group in (
        session.query(LemmaRelationGroup)
        .join(LemmaRelationMember)
        .filter(LemmaRelationMember.lemma_id == source_lemma.id)
    ):
        if group.relation_type in target_groups and target_groups[group.relation_type] != group.id:
            raise ValueError(f"Review competing {group.relation_type} groups on {source_guid}")

    # Only these reference shapes have an explicit migration policy. This
    # preflight also notices future tables instead of relying on cascade deletes.
    consumed = {
        "lemma_translations",
        "derivative_forms",
        "grammar_facts",
        "lemma_difficulty_overrides",
        "lemma_embeddings",
        "lemma_tiers",
        "lemma_facts",
    }
    repointed = {
        "sentence_words",
        "sentence_word_hints",
        "external_lexeme_annotation_lemmas",
        "pending_import_synonym_candidates",
        "lemma_relation_members",
    }
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if any(foreign.target_fullname == "lemmas.id" for foreign in column.foreign_keys):
                count = session.scalar(
                    select(func.count()).select_from(table).where(column == source_lemma.id)
                )
                if count and table.name not in consumed | repointed | {"audio_quality_reviews"}:
                    raise ValueError(f"Review {count} {table.name} references on {source_guid}")

    source_forms = session.query(DerivativeForm).filter_by(lemma_id=source_lemma.id).all()
    if any(form.grammatical_form in NON_INFLECTION_GRAMMATICAL_FORMS for form in source_forms):
        raise ValueError(f"Review legacy synonyms/abbreviations on {source_guid}")
    translations = session.query(LemmaTranslation).filter_by(lemma_id=source_lemma.id).all()
    for translation in translations:
        language = translation.language_code
        grammatical_gender = _grammar_gender(session, source_lemma.id, language)
        forms = [form for form in source_forms if form.language_code == language]
        for form in forms:
            add_variant_form(
                session,
                target,
                form.derivative_form_text,
                language,
                gender,
                form.grammatical_form,
                variant_kind="gender",
                is_base_form=form.is_base_form,
                grammatical_gender=grammatical_gender,
                ipa_pronunciation=form.ipa_pronunciation,
                phonetic_pronunciation=form.phonetic_pronunciation,
                verified=form.verified,
                source=SOURCE,
            )
        if not any(form.is_base_form for form in forms):
            # Unmodeled languages still have an invariant citation slot. Keep
            # their recorded word; do not invent a declension paradigm.
            base_slot = get_base_grammatical_form(language, "noun") or f"noun/{language}_base"
            add_variant_form(
                session,
                target,
                translation.translation,
                language,
                gender,
                base_slot,
                variant_kind="gender",
                is_base_form=True,
                grammatical_gender=grammatical_gender,
                source=SOURCE,
            )
    orphan_languages = {form.language_code for form in source_forms} - {
        translation.language_code for translation in translations
    }
    if orphan_languages:
        raise ValueError(f"Forms without translations on {source_guid}: {sorted(orphan_languages)}")

    archived: Dict[str, object] = {"referent_gender": gender, "replacement_guid": COUSIN_GUID}
    archived["lemma"] = _archive_record(
        {column.name: getattr(source_lemma, column.key) for column in Lemma.__table__.columns}
    )
    for table_name in consumed:
        table = Base.metadata.tables[table_name]
        archived[table_name] = [
            _archive_record(dict(row))
            for row in session.execute(
                select(table).where(table.c.lemma_id == source_lemma.id)
            ).mappings()
        ]

    for concept_fact in session.query(LemmaFact).filter_by(lemma_id=source_lemma.id).all():
        existing_fact = (
            session.query(LemmaFact)
            .filter_by(lemma_id=target.id, fact_type=concept_fact.fact_type)
            .first()
        )
        if existing_fact is not None and existing_fact.fact_value != concept_fact.fact_value:
            # The live male-cousin entry was misclassified as abstract. Keep
            # the surviving cousin's physical classification; the archived
            # source facts above retain the old value for review/audit.
            if not (
                concept_fact.fact_type == "concreteness"
                and concept_fact.fact_value == "abstract"
                and existing_fact.fact_value == "physical"
            ):
                raise ValueError(
                    f"Review conflicting concept fact {concept_fact.fact_type} on {source_guid}"
                )
        if existing_fact is None:
            session.add(
                LemmaFact(
                    lemma_id=target.id,
                    fact_type=concept_fact.fact_type,
                    fact_value=concept_fact.fact_value,
                    notes=concept_fact.notes,
                    verified=concept_fact.verified,
                )
            )

    # Audio preserves the existing asset hashes/URLs, with a variant namespace
    # in its grammatical slot. It cannot overwrite the unspecified base audio.
    for audio in (
        session.query(AudioQualityReview)
        .filter(
            (AudioQualityReview.guid == source_guid)
            | (AudioQualityReview.lemma_id == source_lemma.id)
        )
        .all()
    ):
        audio.guid = COUSIN_GUID
        audio.lemma_id = target.id
        audio.grammatical_form = gender_audio_slot(gender, audio.grammatical_form)
    session.flush()

    for table_name in repointed:
        table = Base.metadata.tables[table_name]
        # These link tables can already link the surviving lemma to the same
        # annotation/group. Remove only the redundant link, not its parent.
        identity = {
            "external_lexeme_annotation_lemmas": "annotation_id",
            "lemma_relation_members": "group_id",
        }.get(table_name)
        if identity:
            target_links = select(table.c[identity]).where(table.c.lemma_id == target.id)
            session.execute(
                delete(table).where(
                    table.c.lemma_id == source_lemma.id, table.c[identity].in_(target_links)
                )
            )
        session.execute(
            update(table).where(table.c.lemma_id == source_lemma.id).values(lemma_id=target.id)
        )
    for table_name in consumed:
        table = Base.metadata.tables[table_name]
        session.execute(delete(table).where(table.c.lemma_id == source_lemma.id))
    create_tombstone(
        session,
        source_guid,
        source_lemma.lemma_text,
        source_lemma.pos_type,
        source_lemma.pos_subtype,
        COUSIN_GUID,
        source_lemma.id,
        reason=TOMBSTONE_REASON_GENDER_VARIANT_MERGE,
        source=SOURCE,
        notes=f"Merged into the {gender} variant of cousin.",
    )
    log_entity_operation(
        session,
        source=SOURCE,
        operation_type="lemma_merge",
        entity_guid=source_guid,
        lemma_id=source_lemma.id,
        fact=archived,
    )
    session.execute(delete(Lemma).where(Lemma.id == source_lemma.id))
    session.expire_all()
    return True


def add_counterpart_seeds(session: Session) -> None:
    """Add only the selected actor and German-person paradigms, idempotently."""
    for (guid, language), words in COUNTERPART_SEEDS.items():
        lemma = session.query(Lemma).filter_by(guid=guid).one()
        if lemma.pos_type != "noun":
            raise ValueError(f"Gender counterparts require a noun: {guid}")
        for gender, singular, plural in (
            ("male", words[0], words[1]),
            ("female", words[2], words[3]),
        ):
            grammatical_gender = (
                None if language == "en" else ("masculine" if gender == "male" else "feminine")
            )
            for number, text in (("singular", singular), ("plural", plural)):
                add_variant_form(
                    session,
                    lemma,
                    text,
                    language,
                    gender,
                    f"noun/{language}_{number}",
                    variant_kind="gender",
                    is_base_form=number == "singular",
                    grammatical_gender=grammatical_gender,
                    source=SOURCE,
                )


def preview(config: DataSourceConfig) -> Dict[str, Any]:
    """Read the real database without initializing, altering, or writing it."""
    connection = sqlite3.connect(database_path(config).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        records: Dict[str, Any] = {}
        for guid in (COUSIN_GUID, *(guid for guid, _ in COUSIN_MERGES), "N36_047", "N33_005"):
            row = connection.execute(
                "SELECT id,guid,lemma_text,pos_type,pos_subtype,difficulty_level,disambiguation "
                "FROM lemmas WHERE guid=?",
                (guid,),
            ).fetchone()
            if row is None:
                records[guid] = None
                continue
            record = dict(row)
            record["translations"] = [
                dict(translation)
                for translation in connection.execute(
                    "SELECT language_code,translation FROM lemma_translations WHERE lemma_id=?",
                    (row["id"],),
                )
            ]
            record["grammar_facts"] = [
                dict(fact)
                for fact in connection.execute(
                    "SELECT language_code,fact_type,fact_value FROM grammar_facts WHERE lemma_id=?",
                    (row["id"],),
                )
            ]
            record["references"] = {}
            record["concept_facts"] = [
                dict(fact)
                for fact in connection.execute(
                    "SELECT fact_type,fact_value FROM lemma_facts WHERE lemma_id=?", (row["id"],)
                )
            ]
            for table_row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ):
                table_name = str(table_row["name"])
                # Identifiers are introspected, quoted, and never interpolated as values.
                quoted = '"' + table_name.replace('"', '""') + '"'
                columns = {
                    column["name"] for column in connection.execute(f"PRAGMA table_info({quoted})")
                }
                if "lemma_id" in columns:
                    count = connection.execute(
                        f"SELECT count(*) FROM {quoted} WHERE lemma_id=?", (row["id"],)
                    ).fetchone()[0]
                    if count:
                        record["references"][table_name] = count
            records[guid] = record
        return {
            "mode": "read-only preview",
            "schema": "ALTER TABLE variant_forms ADD COLUMN grammatical_gender VARCHAR (if absent)",
            "schema_column_present": any(
                column["name"] == "grammatical_gender"
                for column in connection.execute("PRAGMA table_info(variant_forms)")
            ),
            "default": "Ordinary lemma translation/forms and existing grammatical-gender fact; never inferred from male",
            "merge_into": COUSIN_GUID,
            "retire": [{"guid": guid, "gender_variant": gender} for guid, gender in COUSIN_MERGES],
            "seeds": [
                {"guid": guid, "language": language, "male": words[:2], "female": words[2:]}
                for (guid, language), words in COUNTERPART_SEEDS.items()
            ],
            "existing": records,
        }
    finally:
        connection.close()


def apply_changes(session: Session) -> None:
    """Apply the selected data edits to a prepared schema; caller commits."""
    for source_guid, gender in COUSIN_MERGES:
        merge_cousin(session, source_guid, gender)
    cousin = session.query(Lemma).filter_by(guid=COUSIN_GUID).one()
    definition = "A child of one's aunt or uncle; a relative who shares a common grandparent."
    changes = [
        FieldChange("disambiguation", cousin.disambiguation, None),
        FieldChange("definition_text", cousin.definition_text, definition),
    ]
    cousin.disambiguation = None
    cousin.definition_text = definition
    log_field_changes(
        session,
        source=SOURCE,
        operation_type="lemma_update",
        entity_guid=COUSIN_GUID,
        lemma_id=cousin.id,
        changes=changes,
    )
    # Exclusions existed because cousins were split by gender. The retained
    # default now exposes the counterparts, so it must remain in the curriculum.
    for override in (
        session.query(LemmaDifficultyOverride)
        .filter_by(lemma_id=cousin.id, difficulty_level=-1)
        .all()
    ):
        log_field_changes(
            session,
            source=SOURCE,
            operation_type="lemma_difficulty_override_delete",
            entity_guid=COUSIN_GUID,
            lemma_id=cousin.id,
            changes=[FieldChange("difficulty_level", -1, cousin.difficulty_level)],
            extra={"language_code": override.language_code},
        )
        session.delete(override)
    add_counterpart_seeds(session)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-tier", choices=("minor", "major"), default="major")
    args = parser.parse_args()
    config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=args.db_path)
    if not args.apply:
        print(json.dumps(preview(config), ensure_ascii=False, indent=2))
        return
    print(
        f"{args.backup_tier.title()} backup: {create_backup(config, 'gender-variants', args.backup_tier)}"
    )
    engine = create_engine(f"sqlite:///{database_path(config)}")
    apply_sqlite_pragmas(engine)
    try:
        with engine.begin() as connection:
            columns = {
                column["name"] for column in inspect(connection).get_columns("variant_forms")
            }
            if "grammatical_gender" not in columns:
                connection.execute(
                    text("ALTER TABLE variant_forms ADD COLUMN grammatical_gender VARCHAR")
                )
        with Session(engine) as session:
            with session.begin():
                apply_changes(session)
    finally:
        engine.dispose()
    print("Applied gender variants. Release files have not been exported.")


if __name__ == "__main__":
    main()
