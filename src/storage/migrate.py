#!/usr/bin/env python3
"""Migrate data between SQLite and JSONL storage backends.

This script allows you to export data from SQLite to JSONL format,
or import data from JSONL to SQLite.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Collection, Dict, List, Optional

from sqlalchemy.orm import selectinload

# Add src to path if running as script
if __name__ == "__main__":
    src_path = str(Path(__file__).parent.parent.parent)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

import constants
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.release import lemma_audio
from storage.release import phrase as phrase_release
from storage.release import sentence as sentence_release
from storage.release.io import write_jsonl_atomic
from storage.release.lemma import decode_db_emoji
from storage.release.variant import variants_by_language

APPROVED_AUDIO_RELEASE_STATUSES = {"approved", "approved_with_issues"}


def export_sqlalchemy_to_jsonl(source_config: DataSourceConfig, jsonl_dir: str) -> None:
    """Export all data from a SQLAlchemy backend (SQLite or PostgreSQL) to JSONL format.

    Args:
        source_config: DataSourceConfig for the source database (SQLite or PostgreSQL)
        jsonl_dir: Directory to write JSONL files
    """
    backend_name = source_config.backend_type.value.upper()
    if source_config.backend_type == BackendType.SQLITE:
        source_desc = source_config.sqlite_path
    elif source_config.backend_type == BackendType.POSTGRES:
        # Mask password in output
        url = source_config.postgres_url or ""
        if "@" in url:
            _, rest = url.split("@", 1)
            source_desc = f"postgresql://***@{rest}"
        else:
            source_desc = url
    else:
        raise ValueError(f"Unsupported source backend: {source_config.backend_type}")

    print(f"Exporting from {backend_name} ({source_desc}) to JSONL ({jsonl_dir})...")

    # Create source session
    source_session = create_session(source_config)

    # Create target session (JSONL)
    target_config = DataSourceConfig(backend_type=BackendType.JSONL, jsonl_data_dir=jsonl_dir)
    target_session = create_session(target_config)

    # Import models
    from storage.backend.jsonl import models as jsonl_models
    from storage.models.guid_tombstone import GuidTombstone as SQLiteGuidTombstone
    from storage.models.operation_log import OperationLog as SQLiteOperationLog
    from storage.models.schema import AudioQualityReview as SQLiteAudioQualityReview
    from storage.models.schema import Lemma as SQLiteLemma
    from storage.models.schema import Sentence as SQLiteSentence
    from storage.models.schema import SentenceWord as SQLiteSentenceWord

    try:
        # Export Lemmas with eager loading to avoid N+1 queries
        # This is critical for PostgreSQL performance - loads all relationships in batch queries
        print("Exporting lemmas...")
        lemmas = (
            source_session.query(SQLiteLemma)
            .options(
                selectinload(SQLiteLemma.translations),
                selectinload(SQLiteLemma.difficulty_overrides),
                selectinload(SQLiteLemma.derivative_forms),
                selectinload(SQLiteLemma.variant_forms),
                selectinload(SQLiteLemma.grammar_facts),
            )
            .all()
        )
        print(f"Found {len(lemmas)} lemmas")

        for lemma in lemmas:
            # Convert SQLAlchemy lemma to JSONL dataclass
            jsonl_lemma = convert_sqlalchemy_lemma_to_jsonl(lemma, source_session)
            target_session.add(jsonl_lemma)

        # Export Sentences with eager loading to avoid N+1 queries
        print("Exporting sentences...")
        sentences = (
            source_session.query(SQLiteSentence)
            .options(
                selectinload(SQLiteSentence.translations),
                selectinload(SQLiteSentence.words).selectinload(SQLiteSentenceWord.lemma),
            )
            .all()
        )
        print(f"Found {len(sentences)} sentences")

        for sentence in sentences:
            jsonl_sentence = convert_sqlalchemy_sentence_to_jsonl(sentence)
            target_session.add(jsonl_sentence)

        # Export Audio Reviews
        print("Exporting audio reviews...")
        reviews = source_session.query(SQLiteAudioQualityReview).all()
        print(f"Found {len(reviews)} audio reviews")

        for review in reviews:
            jsonl_review = convert_sqlalchemy_audio_review_to_jsonl(review)
            target_session.add(jsonl_review)

        # Export Operation Logs
        print("Exporting operation logs...")
        logs = source_session.query(SQLiteOperationLog).all()
        print(f"Found {len(logs)} operation logs")

        for log in logs:
            jsonl_log = convert_sqlalchemy_operation_log_to_jsonl(log)
            target_session.add(jsonl_log)

        # Export Tombstones
        print("Exporting GUID tombstones...")
        tombstones = source_session.query(SQLiteGuidTombstone).all()
        print(f"Found {len(tombstones)} tombstones")

        for tombstone in tombstones:
            jsonl_tombstone = convert_sqlalchemy_tombstone_to_jsonl(tombstone)
            target_session.add(jsonl_tombstone)

        # Commit all changes
        print("Committing changes...")
        target_session.commit()

        print("Export complete!")

    finally:
        source_session.close()
        target_session.close()


def export_sqlite_to_jsonl(sqlite_path: str, jsonl_dir: str) -> None:
    """Export all data from SQLite to JSONL format.

    This is a backwards-compatible wrapper around export_sqlalchemy_to_jsonl.

    Args:
        sqlite_path: Path to SQLite database
        jsonl_dir: Directory to write JSONL files
    """
    source_config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=sqlite_path)
    export_sqlalchemy_to_jsonl(source_config, jsonl_dir)


def export_postgres_to_jsonl(postgres_url: str, jsonl_dir: str) -> None:
    """Export all data from PostgreSQL to JSONL format.

    Args:
        postgres_url: PostgreSQL connection URL
        jsonl_dir: Directory to write JSONL files
    """
    source_config = DataSourceConfig(backend_type=BackendType.POSTGRES, postgres_url=postgres_url)
    export_sqlalchemy_to_jsonl(source_config, jsonl_dir)


def _sqlite_file_has_data(sqlite_path: str) -> bool:
    """Return True if a SQLite file exists and holds at least one lemma."""
    if not os.path.exists(sqlite_path) or os.path.getsize(sqlite_path) == 0:
        return False

    import sqlite3

    conn = sqlite3.connect(sqlite_path)
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lemmas'")
        if cursor.fetchone() is None:
            return False
        cursor = conn.execute("SELECT 1 FROM lemmas LIMIT 1")
        return cursor.fetchone() is not None
    finally:
        conn.close()


def import_jsonl_to_sqlite(release_dir: str, sqlite_path: str, force: bool = False) -> None:
    """Build a read-write SQLite database from a JSONL release directory.

    Reuses the JSONL backend's loader, which populates an in-memory SQLite
    database with full parity (lemmas, translations, derivative forms,
    synonyms, synthesized base forms, grammar facts, relation groups/members,
    sentences, sentence translations/words, tombstones). The populated
    in-memory database is then copied to the target file via SQLite's native
    backup API, so the on-disk result matches the in-memory load exactly.

    Args:
        release_dir: Path to the JSONL data directory (the parent of
            ``lemmas/``, ``sentences/``, etc. — e.g. ``data/release``).
        sqlite_path: Destination SQLite file path.
        force: If True, overwrite an existing non-empty SQLite file. Otherwise
            this raises when the target already holds data.
    """
    import sqlite3

    from storage.backend.jsonl.storage import JSONLStorage

    if _sqlite_file_has_data(sqlite_path) and not force:
        raise ValueError(
            f"Target SQLite database '{sqlite_path}' already contains data. "
            "Pass --force to overwrite it."
        )

    print(f"Loading JSONL release from '{release_dir}'...")
    storage = JSONLStorage(release_dir)
    storage.ensure_initialized()

    # Force the JSONL backend to populate its cached in-memory SQLite engine.
    # Any query is enough to trigger _get_or_create_cached_engine.
    from storage.backend.jsonl import models as jsonl_models

    warm_session = storage.create_session()
    try:
        warm_session.query(jsonl_models.Lemma).limit(1).all()
    finally:
        warm_session.close()

    source_engine = storage._cached_sqlite_engine
    if source_engine is None:
        raise RuntimeError("JSONL backend did not populate its in-memory SQLite engine")

    # Replace any existing database so the backup writes a clean file. Remove
    # the WAL/SHM sidecars too: a stale -shm/-wal left from a prior database
    # paired with a freshly written main file makes SQLite raise disk I/O
    # errors when it next tries to open the WAL.
    for suffix in ("", "-wal", "-shm", "-journal"):
        sidecar = sqlite_path + suffix
        if os.path.exists(sidecar):
            os.remove(sidecar)
    parent_dir = os.path.dirname(os.path.abspath(sqlite_path))
    os.makedirs(parent_dir, exist_ok=True)

    print(f"Writing SQLite database to '{sqlite_path}'...")
    raw_source = source_engine.raw_connection()
    try:
        source_conn = raw_source.driver_connection
        dest_conn = sqlite3.connect(sqlite_path)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        raw_source.close()

    print(f"Done. SQLite database written to '{sqlite_path}'.")


def convert_sqlalchemy_lemma_to_jsonl(lemma: Any, session: Any = None) -> Any:
    """Convert SQLAlchemy Lemma to JSONL dataclass.

    Args:
        lemma: SQLAlchemy Lemma object with relationships already loaded via selectinload
        session: Deprecated, kept for backward compatibility. Not used when relationships
                 are pre-loaded.
    """
    from storage.backend.jsonl import models as jsonl_models

    # Build translations and disambiguations from the pre-loaded translations relationship
    # This avoids the N+1 query problem when relationships are loaded with selectinload
    translations: Dict[str, str] = {"en": lemma.lemma_text}
    translation_disambiguations: Dict[str, str] = {}
    for trans in lemma.translations:
        if trans.translation:
            translations[trans.language_code] = trans.translation
        if trans.disambiguation:
            translation_disambiguations[trans.language_code] = trans.disambiguation

    # Get difficulty overrides
    difficulty_overrides = {}
    for override in lemma.difficulty_overrides:
        difficulty_overrides[override.language_code] = override.difficulty_level

    # Get derivative forms
    derivative_forms: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for form in lemma.derivative_forms:
        lang_code = form.language_code
        if lang_code not in derivative_forms:
            derivative_forms[lang_code] = {}

        derivative_forms[lang_code][form.grammatical_form] = {
            "form": form.derivative_form_text,
            "is_base_form": form.is_base_form,
            "ipa": form.ipa_pronunciation,
            "phonetic": form.phonetic_pronunciation,
        }

    # Variant forms (alternate spellings), grouped per language and then per
    # variant so each keeps its own paradigm. Built by storage.release.variant
    # so this and the release exporter below cannot disagree about the shape.
    variants: Dict[str, List[Dict[str, Any]]] = variants_by_language(lemma.variant_forms)

    # Get grammar facts
    grammar_facts = []
    for fact in lemma.grammar_facts:
        grammar_facts.append(
            {
                "language_code": fact.language_code,
                "fact_type": fact.fact_type,
                "fact_value": fact.fact_value,
                "notes": fact.notes,
                "verified": fact.verified,
            }
        )

    # Create JSONL lemma with new base concept fields
    return jsonl_models.Lemma(
        id=lemma.id,
        guid=lemma.guid,
        # New base concept fields
        concept_label=lemma.lemma_text,  # Use English lemma text as concept label
        concept_definition=lemma.definition_text,  # Use English definition as concept definition
        # Legacy fields for backward compatibility
        lemma_text=lemma.lemma_text,
        definition_text=lemma.definition_text,
        # Core fields
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
        difficulty_level=lemma.difficulty_level,
        frequency_rank=lemma.frequency_rank,
        tags=lemma.tags,
        # Translations are carried in the `translations` dict below, built from
        # LemmaTranslation; the JSONL model's per-language fields are left unset.
        # Metadata
        disambiguation=lemma.disambiguation,
        sense_prominence=lemma.sense_prominence,
        emoji=decode_db_emoji(lemma.emoji),
        confidence=lemma.confidence,
        verified=lemma.verified,
        notes=lemma.notes,
        lexical_gap_reason=lemma.lexical_gap_reason,
        added_at=lemma.added_at,
        updated_at=lemma.updated_at,
        # Language-specific data (translations now go in base.jsonl)
        translations=translations,
        translation_disambiguations=translation_disambiguations,
        difficulty_overrides=difficulty_overrides,
        derivative_forms=derivative_forms,
        variants=variants,
        base_forms={},  # Populated when no derivative has is_base_form=true
        grammar_facts=grammar_facts,
        audio_hashes={},
    )


def convert_sqlalchemy_sentence_to_jsonl(sentence: Any) -> Any:
    """Convert SQLAlchemy Sentence to JSONL dataclass.

    Sentences are split into different locations based on their source:
    - If source_filename starts with "pattern:": goes to sentences/pattern/{pattern_id}.jsonl (BUIVOLAS pattern sentences)
    - Elif source_filename is set: goes to sentences/group/{source_filename}.jsonl (ZVIRDLIS grouped sentences)
    - Else: goes to sentences/misc/misc.jsonl (miscellaneous sentences)
    """
    from storage.backend.jsonl import models as jsonl_models

    # Get translations
    translations = {}
    for trans in sentence.translations:
        translations[trans.language_code] = trans.translation_text

    words = [sentence_release.sentence_word_to_record(word) for word in sentence.words]

    return jsonl_models.Sentence(
        id=sentence.id,
        guid=f"S_{sentence.id:05d}",  # Generate GUID
        pattern_type=sentence.pattern_type,
        tense=sentence.tense,
        minimum_level=sentence.minimum_level,
        source_filename=sentence.source_filename,
        verified=sentence.verified,
        notes=sentence.notes,
        added_at=sentence.added_at,
        updated_at=sentence.updated_at,
        translations=translations,
        words=words,
    )


def convert_sqlalchemy_audio_review_to_jsonl(review: Any) -> Any:
    """Convert SQLAlchemy AudioQualityReview to JSONL dataclass."""
    from storage.backend.jsonl import models as jsonl_models

    # Parse quality_issues from JSON string to list
    quality_issues = []
    if review.quality_issues:
        try:
            quality_issues = json.loads(review.quality_issues)
        except (json.JSONDecodeError, TypeError):
            # If it's not valid JSON, treat it as a single issue
            quality_issues = [str(review.quality_issues)]

    return jsonl_models.AudioQualityReview(
        id=review.id,
        guid=review.guid,
        language_code=review.language_code,
        voice_name=review.voice_name,
        grammatical_form=review.grammatical_form,
        filename=review.filename,
        status=review.status,
        quality_issues=quality_issues,
        manifest_md5=review.manifest_md5,
        reviewed_at=review.reviewed_at,
        reviewed_by=review.reviewed_by,
        notes=review.notes,
        added_at=review.added_at,
    )


def convert_sqlalchemy_operation_log_to_jsonl(log: Any) -> Any:
    """Convert SQLAlchemy OperationLog to JSONL dataclass."""
    from storage.backend.jsonl import models as jsonl_models

    return jsonl_models.OperationLog(
        id=log.id,
        source=log.source,
        operation_type=log.operation_type,
        timestamp=log.timestamp,
        fact=log.fact,
        lemma_id=log.lemma_id,
        word_token_id=log.word_token_id,
        derivative_form_id=log.derivative_form_id,
        entity_guid=log.entity_guid,
    )


def convert_sqlalchemy_tombstone_to_jsonl(tombstone: Any) -> Any:
    """Convert SQLAlchemy GuidTombstone to JSONL dataclass."""
    from storage.backend.jsonl import models as jsonl_models

    return jsonl_models.GuidTombstone(
        id=tombstone.id,
        guid=tombstone.guid,
        original_lemma_text=tombstone.original_lemma_text,
        original_pos_type=tombstone.original_pos_type,
        original_pos_subtype=tombstone.original_pos_subtype,
        replacement_guid=tombstone.replacement_guid,
        lemma_id=tombstone.lemma_id,
        reason=tombstone.reason,
        notes=tombstone.notes,
        changed_by=tombstone.changed_by,
        tombstoned_at=tombstone.tombstoned_at,
    )


def export_sqlite_to_release(sqlite_path: str, release_dir: str) -> None:
    """Export lemmas (and the tombstones that ship beside them) from SQLite.

    Thin CLI wrapper; the serialization lives in :mod:`storage.release.lemma`
    and :mod:`storage.release.tombstone`.
    """
    from storage.database import create_database_session
    from storage.release import lemma as lemma_release
    from storage.release import tombstone as tombstone_release

    print(f"Exporting from SQLite ({sqlite_path}) to release format ({release_dir})...")
    session = create_database_session(sqlite_path)
    try:
        lemma_release.export_to_release(session, Path(release_dir))
        tombstone_count = tombstone_release.export_to_release(
            session, Path(release_dir).parent / tombstone_release.RELEASE_DIRNAME
        )
        print(f"Tombstones exported: {tombstone_count}")
    finally:
        session.close()


def export_sqlite_to_phrase_release(sqlite_path: str, release_dir: str) -> None:
    """Export phrases from SQLite to the release tree.

    Thin CLI wrapper; the serialization lives in :mod:`storage.release.phrase`.
    """
    from storage.database import create_database_session

    print(f"Exporting phrases from SQLite ({sqlite_path}) to release format ({release_dir})...")
    session = create_database_session(sqlite_path)
    try:
        phrase_release.export_to_release(session, Path(release_dir))
    finally:
        session.close()


def export_sqlite_to_idiom_release(sqlite_path: str, release_dir: str) -> None:
    """Export idioms from SQLite to data/release/idioms format.

    Structure: {release_dir}/base.jsonl - a single file, since idioms carry no
    subtype to partition on. The record shape lives in storage.release.idiom so
    the CLI and the Barsukas sync write identical files.
    """
    print(f"Exporting idioms from SQLite ({sqlite_path}) to release format ({release_dir})...")

    from storage.database import create_database_session
    from storage.release.idiom import export_to_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        exported = export_to_release(session, Path(release_dir))
        print(f"Exported {exported} idioms")
        print("Idiom export complete!")
    finally:
        session.close()


def import_idiom_release_to_sqlite(sqlite_path: str, release_dir: str) -> None:
    """Import data/release/idioms into SQLite.

    Records whose GUID is already present are skipped, so re-running is safe.
    Reconciling changes to an existing idiom is a sync-UI concern, not an
    import one.
    """
    print(f"Importing idioms from release format ({release_dir}) into SQLite ({sqlite_path})...")

    from storage.database import create_database_session
    from storage.release.idiom import import_from_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        imported, skipped = import_from_release(session, Path(release_dir))
        session.commit()
        print(f"Imported {imported} idioms ({skipped} already present)")
        print("Idiom import complete!")
    finally:
        session.close()


def export_sqlite_to_name_release(sqlite_path: str, release_dir: str) -> None:
    """Export names from SQLite to data/release/names format.

    Structure: {release_dir}/base.jsonl - a single file. The name's kind is
    already encoded in its GUID prefix, so partitioning by kind would add
    directories without adding information. The record shape lives in
    storage.release.name so the CLI and the Barsukas sync write identical files.
    """
    print(f"Exporting names from SQLite ({sqlite_path}) to release format ({release_dir})...")

    from storage.database import create_database_session
    from storage.release.name import export_to_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        exported = export_to_release(session, Path(release_dir))
        print(f"Exported {exported} names")
        print("Name export complete!")
    finally:
        session.close()


def import_tombstone_release_to_sqlite(sqlite_path: str, release_dir: str) -> None:
    """Import data/release/tombstones into SQLite.

    Unlike the name and idiom importers, this one *refreshes* records whose GUID
    is already present rather than skipping them: create_tombstone upserts on
    the GUID, so re-running is safe and a row whose replacement or notes changed
    is brought up to date. There is nothing to lose by overwriting - a tombstone
    has no local review state the way a lemma or an audio row does.

    Until this existed the file reached SQLite only through a full bootstrap, so
    a database built any other way had no idea which GUIDs were spent.
    """
    print(
        f"Importing GUID tombstones from release format ({release_dir}) "
        f"into SQLite ({sqlite_path})..."
    )

    from storage.database import create_database_session
    from storage.release.tombstone import import_from_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        imported = import_from_release(session, Path(release_dir))
        print(f"Imported {imported} tombstones")
        print("Tombstone import complete!")
    finally:
        session.close()


def import_name_release_to_sqlite(sqlite_path: str, release_dir: str) -> None:
    """Import data/release/names into SQLite.

    Records whose GUID is already present are skipped, so re-running is safe.
    Reconciling changes to an existing name is a sync-UI concern, not an import
    one.
    """
    print(f"Importing names from release format ({release_dir}) into SQLite ({sqlite_path})...")

    from storage.database import create_database_session
    from storage.release.name import import_from_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        imported, skipped = import_from_release(session, Path(release_dir))
        session.commit()
        print(f"Imported {imported} names ({skipped} already present)")
        print("Name import complete!")
    finally:
        session.close()


def export_sqlite_to_lemma_audio_release(
    sqlite_path: str,
    release_dir: str,
    categories: Optional[Collection[lemma_audio.Category]] = None,
) -> None:
    """Export approved lemma audio from SQLite to the release tree."""
    from storage.database import create_database_session

    print(f"Exporting lemma audio from SQLite ({sqlite_path}) to release ({release_dir})...")
    session = create_database_session(sqlite_path)
    try:
        lemma_audio.export_to_release(session, release_dir, categories=categories)
    finally:
        session.close()


def import_lemma_audio_release_to_sqlite(
    sqlite_path: str,
    release_dir: str,
    prune: bool = False,
    categories: Optional[Collection[lemma_audio.Category]] = None,
) -> None:
    """Sync approved lemma audio from the release tree back into SQLite."""
    from storage.database import create_database_session

    print(f"Syncing lemma audio from release ({release_dir}) into SQLite ({sqlite_path})...")
    session = create_database_session(sqlite_path)
    try:
        lemma_audio.import_from_release(session, release_dir, prune=prune, categories=categories)
    finally:
        session.close()


def export_sqlite_to_sentence_release(sqlite_path: str, release_dir: str) -> None:
    """Export sentences from SQLite to the release tree.

    Thin CLI wrapper: the serialization lives in
    :mod:`storage.release.sentence`, which the Barsukas sync calls directly
    with its own session.
    """
    from storage.database import create_database_session

    print(f"Exporting sentences from SQLite ({sqlite_path}) to release format ({release_dir})...")
    session = create_database_session(sqlite_path)
    try:
        sentence_release.export_to_release(session, Path(release_dir))
    finally:
        session.close()


def import_sentence_audio_release_to_sqlite(sqlite_path: str, release_dir: str) -> None:
    """Sync sentence audio from the release tree back into SQLite."""
    from storage.database import create_database_session

    print(f"Syncing sentence audio from release ({release_dir}) into SQLite ({sqlite_path})...")
    session = create_database_session(sqlite_path)
    try:
        sentence_release.import_audio_from_release(session, Path(release_dir))
    finally:
        session.close()


def _write_jsonl_atomic(file_path: Path, records: List[Dict[str, Any]]) -> None:
    """Write a JSONL file atomically, preserving the caller's record order.

    Thin wrapper over :func:`storage.release.io.write_jsonl_atomic`; the lemma
    and sentence exports sort each file's records themselves, so this must not
    re-sort them.
    """
    write_jsonl_atomic(file_path, records, sort_by_guid=False)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate data between storage backends")
    parser.add_argument(
        "direction",
        choices=[
            "sqlite-to-jsonl",
            "postgres-to-jsonl",
            "sqlite-to-release",
            "sqlite-to-sentence-release",
            "sqlite-to-phrase-release",
            "sqlite-to-idiom-release",
            "idiom-release-to-sqlite",
            "sqlite-to-name-release",
            "name-release-to-sqlite",
            "tombstone-release-to-sqlite",
            "sqlite-to-lemma-audio-release",
            "lemma-audio-release-to-sqlite",
        ],
        help="Migration direction",
    )
    parser.add_argument(
        "--sqlite-path",
        default=constants.WORDFREQ_DB_PATH,
        help=f"Path to SQLite database (default: {constants.WORDFREQ_DB_PATH})",
    )
    parser.add_argument(
        "--postgres-url",
        default=None,
        help="PostgreSQL connection URL (reads from env/key file if not provided)",
    )
    parser.add_argument(
        "--jsonl-dir",
        default="data/working",
        help="Path to JSONL data directory (default: data/working)",
    )
    parser.add_argument(
        "--release-dir",
        default=os.path.join(constants.RELEASE_DIR, "lemmas"),
        help="Path to release directory (default: <release root>/lemmas)",
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help=(
            "When syncing lemma audio release -> SQLite, delete exportable "
            "lemma-audio rows that are no longer present in the release files"
        ),
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        metavar="POS_DIR/SUBTYPE",
        help=(
            "Limit lemma-audio export/import to one category, e.g. nouns/food. "
            "Repeatable; omit to process every category"
        ),
    )
    parser.add_argument(
        "--sentence-release-dir",
        default=os.path.join(constants.RELEASE_DIR, "sentences"),
        help="Path to sentence release directory (default: <release root>/sentences)",
    )
    parser.add_argument(
        "--phrase-release-dir",
        default=os.path.join(constants.RELEASE_DIR, "phrases"),
        help="Path to phrase release directory (default: <release root>/phrases)",
    )
    parser.add_argument(
        "--idiom-release-dir",
        default=os.path.join(constants.RELEASE_DIR, "idioms"),
        help="Path to idiom release directory (default: <release root>/idioms)",
    )
    parser.add_argument(
        "--name-release-dir",
        default=os.path.join(constants.RELEASE_DIR, "names"),
        help="Path to name release directory (default: <release root>/names)",
    )
    parser.add_argument(
        "--tombstone-release-dir",
        default=os.path.join(constants.RELEASE_DIR, "tombstones"),
        help="Path to tombstone release directory (default: <release root>/tombstones)",
    )

    args = parser.parse_args()

    lemma_audio_categories: Optional[List[lemma_audio.Category]] = None
    if args.categories:
        lemma_audio_categories = []
        for slug in args.categories:
            parsed_category = lemma_audio.parse_category_slug(slug)
            if parsed_category is None:
                print(f"Invalid --category {slug!r}; expected POS_DIR/SUBTYPE, e.g. nouns/food")
                sys.exit(1)
            lemma_audio_categories.append(parsed_category)

    if args.direction == "sqlite-to-jsonl":
        export_sqlite_to_jsonl(args.sqlite_path, args.jsonl_dir)
    elif args.direction == "postgres-to-jsonl":
        postgres_url = args.postgres_url
        if not postgres_url:
            # Try to build from environment/key file
            postgres_url = DataSourceConfig.build_postgres_url()
        export_postgres_to_jsonl(postgres_url, args.jsonl_dir)
    elif args.direction == "sqlite-to-release":
        export_sqlite_to_release(args.sqlite_path, args.release_dir)
        export_sqlite_to_lemma_audio_release(args.sqlite_path, args.release_dir)
    elif args.direction == "sqlite-to-sentence-release":
        export_sqlite_to_sentence_release(args.sqlite_path, args.sentence_release_dir)
    elif args.direction == "sqlite-to-phrase-release":
        export_sqlite_to_phrase_release(args.sqlite_path, args.phrase_release_dir)
    elif args.direction == "sqlite-to-idiom-release":
        export_sqlite_to_idiom_release(args.sqlite_path, args.idiom_release_dir)
    elif args.direction == "idiom-release-to-sqlite":
        import_idiom_release_to_sqlite(args.sqlite_path, args.idiom_release_dir)
    elif args.direction == "sqlite-to-name-release":
        export_sqlite_to_name_release(args.sqlite_path, args.name_release_dir)
    elif args.direction == "name-release-to-sqlite":
        import_name_release_to_sqlite(args.sqlite_path, args.name_release_dir)
    elif args.direction == "tombstone-release-to-sqlite":
        import_tombstone_release_to_sqlite(args.sqlite_path, args.tombstone_release_dir)
    elif args.direction == "sqlite-to-lemma-audio-release":
        export_sqlite_to_lemma_audio_release(
            args.sqlite_path, args.release_dir, categories=lemma_audio_categories
        )
    elif args.direction == "lemma-audio-release-to-sqlite":
        import_lemma_audio_release_to_sqlite(
            args.sqlite_path,
            args.release_dir,
            prune=args.prune,
            categories=lemma_audio_categories,
        )
    else:
        print(f"Unknown migration direction: {args.direction}")
        sys.exit(1)


if __name__ == "__main__":
    main()
