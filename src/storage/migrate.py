#!/usr/bin/env python3
"""Migrate data between SQLite and JSONL storage backends.

This script allows you to export data from SQLite to JSONL format,
or import data from JSONL to SQLite.
"""

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Collection, Dict, Iterator, List, Optional, Set, Tuple

from sqlalchemy.orm import selectinload

# Add src to path if running as script
if __name__ == "__main__":
    src_path = str(Path(__file__).parent.parent.parent)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

import constants
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.config.grammar_facts import RELEASE_GRAMMAR_FACT_TYPES

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

    # Get variant forms (alternate spellings), grouped per language and then
    # per variant so each variant keeps its own paradigm.
    variants_by_key: Dict[str, Dict[Tuple[str, str], List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for variant_form in lemma.variant_forms:
        variant_record: Dict[str, Any] = {
            "grammatical_form": variant_form.grammatical_form,
            "text": variant_form.variant_form_text,
            "is_base_form": variant_form.is_base_form,
        }
        if variant_form.ipa_pronunciation:
            variant_record["ipa"] = variant_form.ipa_pronunciation
        if variant_form.phonetic_pronunciation:
            variant_record["phonetic"] = variant_form.phonetic_pronunciation
        variants_by_key[variant_form.language_code][
            (variant_form.variant_kind, variant_form.variant_key)
        ].append(variant_record)

    variants: Dict[str, List[Dict[str, Any]]] = {
        lang_code: [
            {
                "kind": variant_kind,
                "key": variant_key,
                "forms": sorted(
                    variant_forms,
                    key=lambda current_form: current_form["grammatical_form"],
                ),
            }
            for (variant_kind, variant_key), variant_forms in sorted(variant_group.items())
        ]
        for lang_code, variant_group in variants_by_key.items()
    }

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


def _sentence_word_to_dict(word: Any) -> Dict[str, Any]:
    """Serialize one SentenceWord to its on-disk shape.

    Lemmas are referenced by GUID (the stable, on-disk identifier used
    throughout data/release); integer lemma_ids are ephemeral and would not
    survive a JSONL -> SQLite reload. The ``word_role`` key retains the
    database column name, which the JSONL read path maps back to
    ``part_of_speech``.

    ``name_guid`` is emitted for the same reason and only when set: a word that
    resolves to a proper name is not an unresolved gap, and without the key the
    two cases were indistinguishable on disk (both ``lemma_guid: null``).

    Shared by every sentence-word serialization path so a newly added column
    reaches all of them at once.
    """
    return {
        "lemma_guid": word.lemma.guid if word.lemma and word.lemma.guid else None,
        "name_guid": word.name.guid if word.name and word.name.guid else None,
        "language_code": word.language_code,
        "position": word.position,
        "word_role": word.word_role,
        "english_text": word.english_text,
        "target_language_text": word.target_language_text,
        "grammatical_form": word.grammatical_form,
        "grammatical_case": word.grammatical_case,
        "declined_form": word.declined_form,
        "ud_relation": word.ud_relation,
        "ud_head_position": word.ud_head_position,
    }


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

    words = [_sentence_word_to_dict(word) for word in sentence.words]

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
    """Export SQLite to data/release format.

    This creates per-category directories (e.g., nouns/animal/) containing:
    - base.jsonl: concept definitions with translations and difficulty_overrides
      (guid, pos_type, pos_subtype, concept_label, concept_definition,
       difficulty_level, translations: {lang_code: translation},
       difficulty_overrides: {lang_code: level})
    - {lang}.jsonl: per-language data keyed by guid, written only for languages
      that have derivative_forms (conjugations, inflections, etc.), synonyms
      (synonyms, abbreviations, expanded forms, and related lexical variants),
      or grammar_facts (gender, declension, number_type, etc.)

    Args:
        sqlite_path: Path to SQLite database
        release_dir: Directory to write release files (e.g., data/release/lemmas)
    """
    print(f"Exporting from SQLite ({sqlite_path}) to release format ({release_dir})...")

    from storage import translation_helpers
    from storage.database import create_database_session
    from storage.models.concept import ConceptLemmaLink
    from storage.models.guid_tombstone import GuidTombstone
    from storage.models.schema import Lemma, NON_INFLECTION_GRAMMATICAL_FORMS
    from storage.release.lemma import lemma_to_release_record

    session = create_database_session(sqlite_path)
    from storage.utils.session import ensure_tables_exist

    ensure_tables_exist(session)

    try:
        # Get all lemmas with GUIDs (curated words only)
        # Eager-load derivative_forms and grammar_facts to avoid N+1 queries
        lemmas = (
            session.query(Lemma)
            .filter(Lemma.guid.isnot(None))
            .options(
                selectinload(Lemma.translations),
                selectinload(Lemma.derivative_forms),
                selectinload(Lemma.variant_forms),
                selectinload(Lemma.grammar_facts),
                # Read by the base record builder.
                selectinload(Lemma.difficulty_overrides),
            )
            .order_by(Lemma.id)
            .all()
        )
        print(f"Found {len(lemmas)} curated lemmas to export")

        # Every lemma's Q-id in one query. Resolving these per lemma inside the
        # export loop would be one query per word on a whole-tree export.
        qid_by_lemma_id: Dict[int, str] = dict(
            session.query(ConceptLemmaLink.lemma_id, ConceptLemmaLink.qid).all()
        )

        # Group lemmas by POS type/subtype
        lemmas_by_category: Dict[tuple, list] = defaultdict(list)
        for lemma in lemmas:
            pos_type = lemma.pos_type.lower() if lemma.pos_type else "misc"
            pos_subtype = lemma.pos_subtype.lower() if lemma.pos_subtype else "other"
            category = (pos_type, pos_subtype)
            lemmas_by_category[category].append(lemma)

        print(f"Organized into {len(lemmas_by_category)} categories")

        # Map POS types to directory names (pluralized)
        type_to_dir = {
            "noun": "nouns",
            "verb": "verbs",
            "adjective": "adjectives",
            "adverb": "adverbs",
            "pronoun": "pronouns",
            "preposition": "prepositions",
            "conjunction": "conjunctions",
            "interjection": "interjections",
            "numeral": "numerals",
            "particle": "particles",
        }

        # Track languages encountered
        all_languages: Set[str] = set()

        # Process each category
        for (pos_type, pos_subtype), category_lemmas in lemmas_by_category.items():
            # Determine directory structure
            dir_name = type_to_dir.get(pos_type, "misc")
            category_dir = Path(release_dir) / dir_name / pos_subtype
            category_dir.mkdir(parents=True, exist_ok=True)

            print(f"Exporting {len(category_lemmas)} lemmas to {dir_name}/{pos_subtype}...")

            # Collect base records (now includes translations)
            base_records = []

            release_lang_set = set(translation_helpers.RELEASE_LANGUAGES)
            secondary_lang_set = set(translation_helpers.SECONDARY_RELEASE_LANGUAGES)
            extra_group_lang_sets = {
                group_name: set(group_languages)
                for group_name, group_languages in translation_helpers.EXTRA_RELEASE_LANGUAGE_GROUPS.items()
            }

            # Collect secondary translation records alongside base records
            secondary_records: List[Dict[str, Any]] = []
            extra_group_records: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

            for lemma in category_lemmas:
                # Get all translations
                all_translations = translation_helpers.get_all_translations(session, lemma)

                # Route each language to the file that carries it. RELEASE_LANGUAGES
                # ride in the base record, which lemma_to_release_record builds
                # below, so this loop only needs to note that the language is in
                # play; the secondary and grouped tiers are collected here.
                secondary_translations_dict: Dict[str, str] = {}
                secondary_translation_metadata_dict: Dict[str, Dict[str, str]] = {}
                extra_group_translations: Dict[str, Dict[str, str]] = defaultdict(dict)
                extra_group_metadata: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(dict)
                metadata_by_lang: Dict[str, Dict[str, str]] = {}
                for trans_obj in lemma.translations:
                    metadata: Dict[str, str] = {}
                    if trans_obj.translation_status:
                        metadata["translation_status"] = trans_obj.translation_status
                    if trans_obj.translation_status_note:
                        metadata["translation_status_note"] = trans_obj.translation_status_note
                    if metadata:
                        metadata_by_lang[trans_obj.language_code] = metadata

                for lang_code, translation in all_translations.items():
                    if translation and translation.strip():
                        if lang_code in release_lang_set:
                            all_languages.add(lang_code)
                        elif lang_code in secondary_lang_set:
                            all_languages.add(lang_code)
                            secondary_translations_dict[lang_code] = translation
                            if lang_code in metadata_by_lang:
                                secondary_translation_metadata_dict[lang_code] = metadata_by_lang[
                                    lang_code
                                ]
                        else:
                            for group_name, group_lang_set in extra_group_lang_sets.items():
                                if lang_code in group_lang_set:
                                    all_languages.add(lang_code)
                                    extra_group_translations[group_name][lang_code] = translation
                                    if lang_code in metadata_by_lang:
                                        extra_group_metadata[group_name][lang_code] = (
                                            metadata_by_lang[lang_code]
                                        )
                                    break

                # The base record is built by storage.release.lemma, the same
                # function the Barsukas sync uses, so the two exports cannot
                # disagree about it. (They used to: this path wrote
                # concept_label without the disambiguation and omitted qid and
                # translation_disambiguations, so a CLI export after UI work
                # stripped both from the tree.) Secondary and grouped-language
                # records are this function's own concern and stay below.
                base_records.append(
                    lemma_to_release_record(lemma, qid=qid_by_lemma_id.get(lemma.id))
                )

                # Secondary translations record (guid + translations only)
                if secondary_translations_dict:
                    secondary_data: Dict[str, Any] = {
                        "guid": lemma.guid,
                        "translations": secondary_translations_dict,
                    }
                    if secondary_translation_metadata_dict:
                        secondary_data["translation_metadata"] = secondary_translation_metadata_dict
                    secondary_records.append(secondary_data)

                for group_name, group_translations in extra_group_translations.items():
                    if group_translations:
                        group_data: Dict[str, Any] = {
                            "guid": lemma.guid,
                            "translations": group_translations,
                        }
                        group_metadata = extra_group_metadata.get(group_name, {})
                        if group_metadata:
                            group_data["translation_metadata"] = group_metadata
                        extra_group_records[group_name].append(group_data)

            # Write base.jsonl (now includes translations)
            base_file = category_dir / "base.jsonl"
            _write_jsonl_atomic(base_file, base_records)

            # Write secondary.jsonl (secondary language translations)
            secondary_file = category_dir / "secondary.jsonl"
            _write_jsonl_atomic(secondary_file, secondary_records)

            for group_name, group_records in extra_group_records.items():
                group_file = category_dir / f"{group_name}.jsonl"
                _write_jsonl_atomic(group_file, group_records)

            # Collect per-language data (derivative_forms, grammar_facts)
            # keyed by language code -> list of per-lemma records
            lang_records: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

            for lemma in category_lemmas:
                # Group derivative forms by language. True inflections are keyed by
                # grammatical_form; synonym-class forms are list-shaped because the
                # same relation label can repeat for a lemma/language.
                forms_by_lang: Dict[str, Dict[str, Dict[str, Any]]] = {}
                synonyms_by_lang: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                for form in lemma.derivative_forms:
                    lang = form.language_code
                    if form.grammatical_form in NON_INFLECTION_GRAMMATICAL_FORMS:
                        synonym_record: Dict[str, Any] = {
                            "grammatical_form": form.grammatical_form,
                            "text": form.derivative_form_text,
                        }
                        if form.ipa_pronunciation:
                            synonym_record["ipa"] = form.ipa_pronunciation
                        if form.phonetic_pronunciation:
                            synonym_record["phonetic"] = form.phonetic_pronunciation
                        synonyms_by_lang[lang].append(synonym_record)
                        continue
                    if lang not in forms_by_lang:
                        forms_by_lang[lang] = {}
                    forms_by_lang[lang][form.grammatical_form] = {
                        "form": form.derivative_form_text,
                        "is_base_form": form.is_base_form,
                        "ipa": form.ipa_pronunciation,
                        "phonetic": form.phonetic_pronunciation,
                    }

                # Group variant forms (alternate spellings) by language, then by
                # the variant they belong to, so each variant keeps its own
                # paradigm: {"en": {("spelling", "grey"): [grey, greyer, ...]}}
                variants_by_lang: Dict[str, Dict[Tuple[str, str], List[Dict[str, Any]]]] = (
                    defaultdict(lambda: defaultdict(list))
                )
                for variant_form in lemma.variant_forms:
                    variant_record: Dict[str, Any] = {
                        "grammatical_form": variant_form.grammatical_form,
                        "text": variant_form.variant_form_text,
                        "is_base_form": variant_form.is_base_form,
                    }
                    if variant_form.ipa_pronunciation:
                        variant_record["ipa"] = variant_form.ipa_pronunciation
                    if variant_form.phonetic_pronunciation:
                        variant_record["phonetic"] = variant_form.phonetic_pronunciation
                    variants_by_lang[variant_form.language_code][
                        (variant_form.variant_kind, variant_form.variant_key)
                    ].append(variant_record)

                # Group grammar facts by language (only whitelisted types)
                facts_by_lang: Dict[str, List[Dict[str, Any]]] = {}
                for fact in lemma.grammar_facts:
                    lang = fact.language_code
                    allowed_types = RELEASE_GRAMMAR_FACT_TYPES.get(lang)
                    if allowed_types and fact.fact_type in allowed_types:
                        if lang not in facts_by_lang:
                            facts_by_lang[lang] = []
                        facts_by_lang[lang].append(
                            {
                                "fact_type": fact.fact_type,
                                "fact_value": fact.fact_value,
                            }
                        )

                # Build per-language records for release languages that have data
                langs_with_data = (
                    set(forms_by_lang.keys())
                    | set(synonyms_by_lang.keys())
                    | set(variants_by_lang.keys())
                    | set(facts_by_lang.keys())
                ) & release_lang_set
                for lang in langs_with_data:
                    record: Dict[str, Any] = {"guid": lemma.guid}
                    if lang in forms_by_lang:
                        record["derivative_forms"] = forms_by_lang[lang]
                    if lang in synonyms_by_lang:
                        record["synonyms"] = sorted(
                            synonyms_by_lang[lang],
                            key=lambda current_synonym: (
                                current_synonym["grammatical_form"],
                                current_synonym["text"],
                            ),
                        )
                    if lang in variants_by_lang:
                        record["variants"] = [
                            {
                                "kind": variant_kind,
                                "key": variant_key,
                                "forms": sorted(
                                    variant_forms,
                                    key=lambda current_form: current_form["grammatical_form"],
                                ),
                            }
                            for (variant_kind, variant_key), variant_forms in sorted(
                                variants_by_lang[lang].items()
                            )
                        ]
                    if lang in facts_by_lang:
                        record["grammar_facts"] = facts_by_lang[lang]
                    lang_records[lang].append(record)

            # Write {lang}.jsonl files for each language that has data
            for lang, records in sorted(lang_records.items()):
                lang_file = category_dir / f"{lang}.jsonl"
                _write_jsonl_atomic(lang_file, records)

        print(f"\nExport complete!")
        print(f"Languages exported: {', '.join(sorted(all_languages))}")

        tombstone_records: List[Dict[str, Any]] = []
        for tombstone in session.query(GuidTombstone).order_by(GuidTombstone.guid).all():
            tombstone_record: Dict[str, Any] = {
                "guid": tombstone.guid,
                "original_lemma_text": tombstone.original_lemma_text,
                "original_pos_type": tombstone.original_pos_type,
                "reason": tombstone.reason,
            }
            if tombstone.original_pos_subtype:
                tombstone_record["original_pos_subtype"] = tombstone.original_pos_subtype
            if tombstone.replacement_guid:
                tombstone_record["replacement_guid"] = tombstone.replacement_guid
            if tombstone.lemma_id:
                tombstone_record["lemma_id"] = tombstone.lemma_id
            if tombstone.notes:
                tombstone_record["notes"] = tombstone.notes
            if tombstone.changed_by:
                tombstone_record["changed_by"] = tombstone.changed_by
            _add_tombstoned_at(tombstone_record, tombstone.tombstoned_at)
            tombstone_records.append(tombstone_record)

        _write_jsonl_atomic(
            Path(release_dir).parent / "tombstones" / "guid_tombstones.jsonl",
            tombstone_records,
        )
        print(f"Tombstones exported: {len(tombstone_records)}")

    finally:
        session.close()


def _add_tombstoned_at(record: Dict[str, Any], tombstoned_at: Any) -> None:
    """Add tombstoned_at to a release tombstone record if it is available."""
    if tombstoned_at is None:
        return
    if hasattr(tombstoned_at, "isoformat"):
        record["tombstoned_at"] = tombstoned_at.isoformat()
    else:
        record["tombstoned_at"] = str(tombstoned_at)


def export_sqlite_to_sentence_release(sqlite_path: str, release_dir: str) -> None:
    """Export sentences from SQLite to data/release/sentences format.

    Sentences are grouped first by their **collection** (sentence_collection field,
    defaulting to "general"), then by primary lemma pos_type/pos_subtype — the noun
    with the lowest GUID among word hints, falling back to misc/misc.

    Structure: {release_dir}/{collection}/{pos_dir}/{pos_subtype}/base.jsonl

    Conversation and rejected sentences are excluded.

    Args:
        sqlite_path: Path to SQLite database
        release_dir: Directory to write release files (e.g., data/release/sentences)
    """
    print(f"Exporting sentences from SQLite ({sqlite_path}) to release format ({release_dir})...")

    from sqlalchemy.orm import selectinload

    from storage.database import create_database_session
    from storage.models.schema import (
        ConversationSentence,
        Lemma,
        Sentence,
        SentenceWordHint,
        SentenceWord,
    )

    session = create_database_session(sqlite_path)

    # Map POS types to directory names (pluralized)
    type_to_dir: Dict[str, str] = {
        "noun": "nouns",
        "verb": "verbs",
        "adjective": "adjectives",
        "adverb": "adverbs",
        "pronoun": "pronouns",
        "preposition": "prepositions",
        "conjunction": "conjunctions",
        "interjection": "interjections",
        "numeral": "numerals",
        "particle": "particles",
    }

    try:
        # Exclude conversation sentences
        conversation_ids: Set[int] = set(
            row[0] for row in session.query(ConversationSentence.sentence_id).distinct().all()
        )

        # Get all sentences with GUIDs, eager-load relationships
        sentences = (
            session.query(Sentence)
            .filter(Sentence.guid.isnot(None))
            .filter(Sentence.rejected.is_(False))
            .options(
                selectinload(Sentence.translations),
                selectinload(Sentence.word_hints).selectinload(SentenceWordHint.lemma),
                selectinload(Sentence.words).selectinload(SentenceWord.lemma),
                selectinload(Sentence.audio_reviews),
            )
            .order_by(Sentence.guid)
            .all()
        )

        # Filter out conversation sentences
        sentences = [s for s in sentences if s.id not in conversation_ids]
        print(f"Found {len(sentences)} non-conversation, non-rejected sentences to export")

        # Group sentences by (collection, pos_type, pos_subtype)
        sentences_by_category: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)

        for sentence in sentences:
            record = _sentence_to_release_record(sentence)
            collection = sentence.sentence_collection or "general"
            pos_type, pos_subtype = _resolve_primary_lemma_category(sentence)
            sentences_by_category[(collection, pos_type, pos_subtype)].append(record)

        print(f"Organized into {len(sentences_by_category)} categories")

        for (collection, pos_type, pos_subtype), records in sentences_by_category.items():
            dir_name = type_to_dir.get(pos_type, pos_type)
            category_dir = Path(release_dir) / collection / dir_name / pos_subtype
            category_dir.mkdir(parents=True, exist_ok=True)

            # Sort by GUID within each file
            records.sort(key=lambda r: r["guid"])

            print(f"Exporting {len(records)} sentences to {collection}/{dir_name}/{pos_subtype}...")
            _write_jsonl_atomic(category_dir / "base.jsonl", records)

        print("Sentence export complete!")

    finally:
        session.close()


def phrase_to_release_records(phrase: Any) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Build the (base, secondary) release JSONL records for a phrase.

    The base record carries RELEASE_LANGUAGES translations (+ metadata), the
    concept label/definition, subtype, and difficulty. Secondary-language
    translations, when present, go to a separate record (written to
    ``secondary.jsonl``); ``None`` when the phrase has none. Translation keys
    are emitted in RELEASE_LANGUAGES / SECONDARY_RELEASE_LANGUAGES order so the
    output is stable and matches the lemma export.

    Shared by the CLI export (``export_sqlite_to_phrase_release``) and the
    Barsukas phrase sync so both write byte-identical files.
    """
    from storage import translation_helpers

    trans_by_lang: Dict[str, Any] = {
        t.language_code: t for t in phrase.translations if t.translation and t.translation.strip()
    }

    def _metadata_for(trans_obj: Any) -> Dict[str, str]:
        meta: Dict[str, str] = {}
        if trans_obj.translation_status:
            meta["translation_status"] = trans_obj.translation_status
        if trans_obj.translation_status_note:
            meta["translation_status_note"] = trans_obj.translation_status_note
        return meta

    translations_dict: Dict[str, str] = {}
    translation_metadata_dict: Dict[str, Dict[str, str]] = {}
    secondary_translations_dict: Dict[str, str] = {}
    secondary_metadata_dict: Dict[str, Dict[str, str]] = {}

    for lang_code in translation_helpers.RELEASE_LANGUAGES:
        trans_obj = trans_by_lang.get(lang_code)
        if trans_obj is None:
            continue
        translations_dict[lang_code] = trans_obj.translation
        metadata = _metadata_for(trans_obj)
        if metadata:
            translation_metadata_dict[lang_code] = metadata

    for lang_code in translation_helpers.SECONDARY_RELEASE_LANGUAGES:
        trans_obj = trans_by_lang.get(lang_code)
        if trans_obj is None:
            continue
        secondary_translations_dict[lang_code] = trans_obj.translation
        metadata = _metadata_for(trans_obj)
        if metadata:
            secondary_metadata_dict[lang_code] = metadata

    base_data: Dict[str, Any] = {
        "guid": phrase.guid,
        "phrase_subtype": phrase.phrase_subtype,
        "concept_label": phrase.label,
        "concept_definition": phrase.definition,
    }
    if translations_dict:
        base_data["translations"] = translations_dict
    if translation_metadata_dict:
        base_data["translation_metadata"] = translation_metadata_dict
    if phrase.difficulty_level is not None:
        base_data["difficulty_level"] = phrase.difficulty_level

    secondary_data: Optional[Dict[str, Any]] = None
    if secondary_translations_dict:
        secondary_data = {
            "guid": phrase.guid,
            "translations": secondary_translations_dict,
        }
        if secondary_metadata_dict:
            secondary_data["translation_metadata"] = secondary_metadata_dict

    return base_data, secondary_data


def export_sqlite_to_phrase_release(sqlite_path: str, release_dir: str) -> None:
    """Export phrases from SQLite to data/release/phrases format.

    Phrases (fixed traveler/greeting expressions) live in their own ``phrases``
    table (no longer in ``lemmas``), so they get their own release tree:

    Structure: {release_dir}/{phrase_subtype}/base.jsonl

    Each base record carries: guid, phrase_subtype, concept_label,
    concept_definition, translations (RELEASE_LANGUAGES), translation_metadata,
    and difficulty_level. Secondary-language translations, when present, go to a
    sibling secondary.jsonl.

    Args:
        sqlite_path: Path to SQLite database
        release_dir: Directory to write release files (e.g., data/release/phrases)
    """
    print(f"Exporting phrases from SQLite ({sqlite_path}) to release format ({release_dir})...")

    from sqlalchemy.orm import selectinload

    from storage.database import create_database_session
    from storage.models.schema import Phrase

    session = create_database_session(sqlite_path)
    from storage.utils.session import ensure_tables_exist

    ensure_tables_exist(session)

    try:
        phrases = (
            session.query(Phrase)
            .filter(Phrase.guid.isnot(None))
            .options(selectinload(Phrase.translations))
            .order_by(Phrase.guid)
            .all()
        )
        print(f"Found {len(phrases)} phrases to export")

        base_by_subtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        secondary_by_subtype: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for phrase in phrases:
            base_data, secondary_data = phrase_to_release_records(phrase)
            base_by_subtype[phrase.phrase_subtype].append(base_data)
            if secondary_data is not None:
                secondary_by_subtype[phrase.phrase_subtype].append(secondary_data)

        for phrase_subtype, records in base_by_subtype.items():
            category_dir = Path(release_dir) / phrase_subtype
            category_dir.mkdir(parents=True, exist_ok=True)
            records.sort(key=lambda r: r["guid"])
            print(f"Exporting {len(records)} phrases to {phrase_subtype}...")
            _write_jsonl_atomic(category_dir / "base.jsonl", records)

            secondary_records = secondary_by_subtype.get(phrase_subtype)
            if secondary_records:
                secondary_records.sort(key=lambda r: r["guid"])
                _write_jsonl_atomic(category_dir / "secondary.jsonl", secondary_records)

        print("Phrase export complete!")

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
    from storage.release.idiom import export_idioms_to_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        exported = export_idioms_to_release(session, Path(release_dir))
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
    from storage.release.idiom import import_idioms_from_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        imported, skipped = import_idioms_from_release(session, Path(release_dir))
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
    from storage.release.name import export_names_to_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        exported = export_names_to_release(session, Path(release_dir))
        print(f"Exported {exported} names")
        print("Name export complete!")
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
    from storage.release.name import import_names_from_release
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    try:
        imported, skipped = import_names_from_release(session, Path(release_dir))
        session.commit()
        print(f"Imported {imported} names ({skipped} already present)")
        print("Name import complete!")
    finally:
        session.close()


@dataclass
class LemmaAudioExportStats:
    """Summary of a lemma-audio export (SQLite/DB -> release files)."""

    audio_rows: int = 0
    guids: int = 0
    categories: int = 0


@dataclass
class LemmaAudioImportStats:
    """Summary of a lemma-audio import (release files -> SQLite/DB)."""

    added: int = 0
    updated: int = 0
    pruned: int = 0
    unchanged: int = 0


# Directory names for each part of speech, shared by lemma-audio export/import.
_LEMMA_AUDIO_TYPE_TO_DIR: Dict[str, str] = {
    "noun": "nouns",
    "verb": "verbs",
    "adjective": "adjectives",
    "adverb": "adverbs",
    "pronoun": "pronouns",
    "preposition": "prepositions",
    "conjunction": "conjunctions",
    "interjection": "interjections",
    "numeral": "numerals",
    "particle": "particles",
}

_LEMMA_AUDIO_DIR_TO_TYPE: Dict[str, str] = {
    dir_name: pos_type for pos_type, dir_name in _LEMMA_AUDIO_TYPE_TO_DIR.items()
}

# The audio.jsonl entry fields an export writes and an import reads back. Any
# difference in these between the database and the release file is a real change;
# every other AudioQualityReview column is local-only review metadata.
LEMMA_AUDIO_RELEASE_FIELDS: Tuple[str, ...] = (
    "filename",
    "status",
    "expected_text",
    "manifest_md5",
    "s3_prod_url",
    "s3_staging_url",
    "staging_agent",
)

# (guid, language_code, voice_name, grammatical_form) — the lemma-audio unique key.
LemmaAudioKey = Tuple[str, str, str, Any]
# (pos_type, pos_subtype) — one release directory's worth of lemma audio.
LemmaAudioCategory = Tuple[str, str]


def lemma_audio_category_slug(category: LemmaAudioCategory) -> str:
    """Render a category as the ``{pos_dir}/{pos_subtype}`` slug used in forms and URLs."""
    pos_type, pos_subtype = category
    return f"{_LEMMA_AUDIO_TYPE_TO_DIR.get(pos_type, pos_type)}/{pos_subtype}"


def parse_lemma_audio_category_slug(slug: str) -> Optional[LemmaAudioCategory]:
    """Parse a ``{pos_dir}/{pos_subtype}`` slug back into a (pos_type, pos_subtype).

    Returns None for anything that is not exactly two non-empty path segments, so
    caller-supplied slugs (form fields, CLI flags) cannot escape the release tree.
    """
    parts = [part for part in slug.strip().strip("/").split("/") if part]
    if len(parts) != 2:
        return None
    dir_name, pos_subtype = parts[0].lower(), parts[1].lower()
    if dir_name in {".", ".."} or pos_subtype in {".", ".."}:
        return None
    return (_LEMMA_AUDIO_DIR_TO_TYPE.get(dir_name, dir_name), pos_subtype)


def _lemma_audio_category_dir(release_dir: str, category: LemmaAudioCategory) -> Path:
    """Path of the directory holding one category's ``audio.jsonl``."""
    return Path(release_dir) / lemma_audio_category_slug(category)


def _lemma_audio_category_for_file(release_dir: str, audio_file: Path) -> LemmaAudioCategory:
    """Recover the (pos_type, pos_subtype) an ``audio.jsonl`` path belongs to."""
    relative = audio_file.parent.relative_to(Path(release_dir))
    category = parse_lemma_audio_category_slug(str(relative))
    if category is None:
        # A stray audio.jsonl at an unexpected depth: keep it addressable rather
        # than dropping it silently, using the raw path as the subtype.
        return ("misc", str(relative))
    return category


def _lemma_audio_guids_in_categories(
    session: Any, categories: Collection[LemmaAudioCategory]
) -> Set[str]:
    """GUIDs of the lemmas belonging to ``categories``.

    Used to scope a pruning import: a row may only be deleted if its lemma lives
    in one of the categories the import actually read.
    """
    from storage.models.schema import Lemma

    if not categories:
        return set()

    guids: Set[str] = set()
    wanted = set(categories)
    for guid, pos_type, pos_subtype in (
        session.query(Lemma.guid, Lemma.pos_type, Lemma.pos_subtype)
        .filter(Lemma.guid.isnot(None))
        .all()
    ):
        category = (
            pos_type.lower() if pos_type else "misc",
            pos_subtype.lower() if pos_subtype else "other",
        )
        if category in wanted:
            guids.add(guid)
    return guids


def _lemma_audio_entry_from_review(audio_review: Any) -> Dict[str, Any]:
    """Build the release ``audio[]`` entry for one AudioQualityReview row."""
    entry: Dict[str, Any] = {
        "language_code": audio_review.language_code,
        "voice_name": audio_review.voice_name,
    }
    for field in LEMMA_AUDIO_RELEASE_FIELDS:
        entry[field] = getattr(audio_review, field)
    entry["grammatical_form"] = audio_review.grammatical_form
    return entry


def _iter_release_lemma_audio_entries(
    release_dir: str, categories: Optional[Collection[LemmaAudioCategory]] = None
) -> Iterator[Tuple[LemmaAudioCategory, LemmaAudioKey, Dict[str, Any]]]:
    """Yield every well-formed lemma-audio entry in the release files.

    Shared by import and diff so both agree on which rows exist, how they are
    keyed, and which categories a scoped operation touches. Entries missing a
    language or voice cannot be keyed and are skipped.
    """
    wanted = set(categories) if categories is not None else None
    if wanted is not None:
        audio_files = [
            path
            for path in (
                _lemma_audio_category_dir(release_dir, category) / "audio.jsonl"
                for category in sorted(wanted)
            )
            if path.is_file()
        ]
    else:
        audio_files = sorted(Path(release_dir).rglob("audio.jsonl"))

    for audio_file in audio_files:
        category = _lemma_audio_category_for_file(release_dir, audio_file)
        with open(audio_file, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                guid = data.get("guid")
                if not guid:
                    continue
                for entry in data.get("audio", []):
                    language_code = entry.get("language_code")
                    voice_name = entry.get("voice_name")
                    if not language_code or not voice_name:
                        print(f"Warning: {audio_file} guid {guid} has audio without a voice")
                        continue
                    key = (guid, language_code, voice_name, entry.get("grammatical_form"))
                    yield category, key, entry


def export_lemma_audio_release_from_session(
    session: Any,
    release_dir: str,
    categories: Optional[Collection[LemmaAudioCategory]] = None,
) -> LemmaAudioExportStats:
    """Export approved lemma audio from an open session to release files.

    Session-based core of :func:`export_sqlite_to_lemma_audio_release`; works with
    any SQLAlchemy backend (SQLite or PostgreSQL) so the Barsukas sync route can
    reuse it against the live request session. Does not close ``session``.

    Args:
        session: Open SQLAlchemy session to read audio rows from.
        release_dir: Release lemmas directory (parent of the per-category files).
        categories: If given, only rewrite these ``(pos_type, pos_subtype)``
            categories; every other ``audio.jsonl`` is left untouched. A selected
            category with no approved audio in the database is truncated to an
            empty file rather than left stale, so export stays the inverse of
            a pruning import. If None, every category with audio is written.
    """
    from storage.models.schema import AudioQualityReview, Lemma

    wanted = set(categories) if categories is not None else None

    rows = (
        session.query(AudioQualityReview, Lemma)
        .join(Lemma, AudioQualityReview.guid == Lemma.guid)
        .filter(AudioQualityReview.guid.isnot(None))
        .filter(AudioQualityReview.sentence_id.is_(None))
        .filter(AudioQualityReview.status.in_(APPROVED_AUDIO_RELEASE_STATUSES))
        .order_by(
            Lemma.pos_type,
            Lemma.pos_subtype,
            AudioQualityReview.guid,
            AudioQualityReview.language_code,
            AudioQualityReview.voice_name,
        )
        .all()
    )

    records_by_category: Dict[LemmaAudioCategory, Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # The English word each GUID's audio relates to, so audio.jsonl records
    # are self-describing without a cross-reference into base.jsonl.
    english_by_category_guid: Dict[LemmaAudioCategory, Dict[str, str]] = defaultdict(dict)
    exported_rows = 0
    for audio_review, lemma in rows:
        pos_type = lemma.pos_type.lower() if lemma.pos_type else "misc"
        pos_subtype = lemma.pos_subtype.lower() if lemma.pos_subtype else "other"
        category = (pos_type, pos_subtype)
        if wanted is not None and category not in wanted:
            continue
        records_by_category[category][audio_review.guid].append(
            _lemma_audio_entry_from_review(audio_review)
        )
        english_by_category_guid[category][audio_review.guid] = lemma.lemma_text
        exported_rows += 1

    # Selected-but-empty categories still get written, so deselecting audio in the
    # database clears the corresponding file instead of leaving stale rows behind.
    written_categories = set(records_by_category)
    if wanted is not None:
        written_categories |= {
            category
            for category in wanted
            if (_lemma_audio_category_dir(release_dir, category) / "audio.jsonl").is_file()
        }

    guid_count = 0
    for category in sorted(written_categories):
        audio_by_guid = records_by_category.get(category, {})
        category_dir = _lemma_audio_category_dir(release_dir, category)
        category_dir.mkdir(parents=True, exist_ok=True)
        english_by_guid = english_by_category_guid[category]
        records = []
        for guid, audio in sorted(audio_by_guid.items(), key=lambda item: item[0]):
            record: Dict[str, Any] = {"guid": guid}
            english = english_by_guid.get(guid)
            if english:
                record["english"] = english
            record["audio"] = audio
            records.append(record)
        guid_count += len(records)
        slug = lemma_audio_category_slug(category)
        print(f"Exporting {len(records)} lemma audio records to {slug}...")
        _write_jsonl_atomic(category_dir / "audio.jsonl", records)

    print(f"Lemma audio export complete! Exported {exported_rows} approved audio rows.")
    return LemmaAudioExportStats(
        audio_rows=exported_rows,
        guids=guid_count,
        categories=len(written_categories),
    )


def export_sqlite_to_lemma_audio_release(
    sqlite_path: str,
    release_dir: str,
    categories: Optional[Collection[LemmaAudioCategory]] = None,
) -> None:
    """Export approved lemma audio from SQLite to data/release/lemmas format.

    Audio records are grouped beside lemma release records:
    {release_dir}/{pos_dir}/{pos_subtype}/audio.jsonl

    Only approved lemma audio is exported. Sentence audio is emitted by
    export_sqlite_to_sentence_release. Opens (and closes) its own session from
    ``sqlite_path``; :func:`export_lemma_audio_release_from_session` is the
    session-based core.

    Args:
        sqlite_path: Path to the SQLite database to export from.
        release_dir: Release lemmas directory to write into.
        categories: If given, only rewrite these ``(pos_type, pos_subtype)``
            categories; all other ``audio.jsonl`` files are left untouched.
    """
    print(f"Exporting lemma audio from SQLite ({sqlite_path}) to release format ({release_dir})...")

    from storage.database import create_database_session

    session = create_database_session(sqlite_path)
    try:
        export_lemma_audio_release_from_session(session, release_dir, categories=categories)
    finally:
        session.close()


def import_lemma_audio_release_into_session(
    session: Any,
    release_dir: str,
    prune: bool = False,
    categories: Optional[Collection[LemmaAudioCategory]] = None,
    keys: Optional[Collection[LemmaAudioKey]] = None,
) -> LemmaAudioImportStats:
    """Sync approved lemma audio from release files into an open session.

    Session-based core of :func:`import_lemma_audio_release_to_sqlite`; works with
    any SQLAlchemy backend so the Barsukas sync route can reuse it against the
    live request session. Commits on ``session`` but does not close it.

    Args:
        session: Open SQLAlchemy session to upsert audio rows into.
        release_dir: Release lemmas directory (parent of the per-category files).
        prune: If True, delete exportable lemma-audio rows that are no longer in
            the release files. Pruning respects ``categories``: a scoped import
            only ever deletes rows belonging to the categories it read, so
            syncing one directory cannot remove audio from another.
        categories: If given, only read these ``(pos_type, pos_subtype)``
            categories' files. If None, every ``audio.jsonl`` is read.
        keys: If given, only apply entries whose
            ``(guid, language_code, voice_name, grammatical_form)`` key is in this
            set — the selective-apply path used by the Barsukas diff page. Prune
            is likewise limited to these keys' categories.
    """
    from storage.models.schema import AudioQualityReview, Lemma

    added = 0
    updated = 0
    unchanged = 0
    pruned = 0

    # Map GUIDs to lemma ids so imported audio rows can be linked.
    lemma_id_by_guid: Dict[str, int] = {
        guid: lemma_id
        for guid, lemma_id in session.query(Lemma.guid, Lemma.id)
        .filter(Lemma.guid.isnot(None))
        .all()
    }

    selected_keys = set(keys) if keys is not None else None
    # Categories actually read, so a scoped prune knows what it is allowed to touch.
    visited_categories: Set[LemmaAudioCategory] = set()
    release_keys: Set[LemmaAudioKey] = set()

    for category, key, entry in _iter_release_lemma_audio_entries(release_dir, categories):
        visited_categories.add(category)
        release_keys.add(key)
        if selected_keys is not None and key not in selected_keys:
            continue

        guid, language_code, voice_name, grammatical_form = key
        existing = (
            session.query(AudioQualityReview)
            .filter(
                AudioQualityReview.guid == guid,
                AudioQualityReview.language_code == language_code,
                AudioQualityReview.voice_name == voice_name,
                (
                    AudioQualityReview.grammatical_form.is_(None)
                    if grammatical_form is None
                    else AudioQualityReview.grammatical_form == grammatical_form
                ),
            )
            .one_or_none()
        )

        if existing is None:
            session.add(
                AudioQualityReview(
                    guid=guid,
                    language_code=language_code,
                    voice_name=voice_name,
                    grammatical_form=grammatical_form,
                    filename=entry.get("filename", ""),
                    expected_text=entry.get("expected_text", ""),
                    manifest_md5=entry.get("manifest_md5", ""),
                    status=entry.get("status", "approved"),
                    s3_prod_url=entry.get("s3_prod_url"),
                    s3_staging_url=entry.get("s3_staging_url"),
                    staging_agent=entry.get("staging_agent"),
                    lemma_id=lemma_id_by_guid.get(guid),
                )
            )
            added += 1
            continue

        # Only count a row as updated when a release-bearing field really moved;
        # re-importing an unchanged file should report zero updates.
        changed = False
        for field in LEMMA_AUDIO_RELEASE_FIELDS:
            if field not in entry:
                continue
            new_value = entry[field]
            if getattr(existing, field) != new_value:
                setattr(existing, field, new_value)
                changed = True
        if existing.lemma_id is None:
            resolved_lemma_id = lemma_id_by_guid.get(guid)
            if resolved_lemma_id is not None:
                existing.lemma_id = resolved_lemma_id
                changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    if prune:
        prune_query = (
            session.query(AudioQualityReview)
            .filter(AudioQualityReview.guid.isnot(None))
            .filter(AudioQualityReview.sentence_id.is_(None))
            .filter(AudioQualityReview.status.in_(APPROVED_AUDIO_RELEASE_STATUSES))
        )
        # A scoped import must not delete rows outside the categories it read.
        prune_scope: Optional[Set[LemmaAudioCategory]] = None
        if categories is not None or selected_keys is not None:
            prune_scope = set(categories) if categories is not None else visited_categories
        prunable_guids = (
            _lemma_audio_guids_in_categories(session, prune_scope)
            if prune_scope is not None
            else None
        )
        for review in prune_query.all():
            if prunable_guids is not None and review.guid not in prunable_guids:
                continue
            key = (
                review.guid,
                review.language_code,
                review.voice_name,
                review.grammatical_form,
            )
            if key not in release_keys:
                session.delete(review)
                pruned += 1

    session.commit()
    summary = f"Lemma audio sync complete! Added {added}, updated {updated}, unchanged {unchanged}"
    if prune:
        summary += f", pruned {pruned}"
    print(summary + ".")
    return LemmaAudioImportStats(added=added, updated=updated, pruned=pruned, unchanged=unchanged)


# How one lemma-audio key differs between the release files and the database.
LEMMA_AUDIO_DIFF_STATES = ("only_in_release", "only_in_db", "changed", "identical")


@dataclass
class LemmaAudioDiffEntry:
    """One lemma-audio key's state in a release-vs-database comparison.

    ``state`` is one of :data:`LEMMA_AUDIO_DIFF_STATES`. ``changed_fields`` lists
    the release-bearing fields that differ (only meaningful when ``state`` is
    ``"changed"``), each mapped to its ``(release_value, db_value)`` pair so the
    UI can show what an import would overwrite.
    """

    guid: str
    language_code: str
    voice_name: str
    grammatical_form: Optional[str] = None
    state: str = "identical"
    english: Optional[str] = None
    changed_fields: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)

    @property
    def key(self) -> LemmaAudioKey:
        """The lemma-audio unique key this entry describes."""
        return (self.guid, self.language_code, self.voice_name, self.grammatical_form)

    @property
    def key_token(self) -> str:
        """Round-trippable form-field token for this key (see :func:`parse_lemma_audio_key_token`)."""
        return json.dumps(list(self.key), ensure_ascii=False, separators=(",", ":"))


@dataclass
class LemmaAudioCategoryDiff:
    """One category's worth of lemma-audio differences."""

    pos_type: str
    pos_subtype: str
    entries: List[LemmaAudioDiffEntry] = field(default_factory=list)

    @property
    def slug(self) -> str:
        """The ``{pos_dir}/{pos_subtype}`` slug identifying this category."""
        return lemma_audio_category_slug((self.pos_type, self.pos_subtype))

    @property
    def only_in_release(self) -> int:
        return sum(1 for entry in self.entries if entry.state == "only_in_release")

    @property
    def only_in_db(self) -> int:
        return sum(1 for entry in self.entries if entry.state == "only_in_db")

    @property
    def changed(self) -> int:
        return sum(1 for entry in self.entries if entry.state == "changed")

    @property
    def identical(self) -> int:
        return sum(1 for entry in self.entries if entry.state == "identical")

    @property
    def differing(self) -> int:
        """Entries an import or export would actually act on."""
        return self.only_in_release + self.only_in_db + self.changed

    @property
    def differing_entries(self) -> List["LemmaAudioDiffEntry"]:
        """Just the entries that differ, for listing in the UI."""
        return [entry for entry in self.entries if entry.state != "identical"]


@dataclass
class LemmaAudioReleaseDiff:
    """Read-only comparison of lemma-audio release files vs. the database.

    Keys are the lemma-audio unique tuple ``(guid, language_code, voice_name,
    grammatical_form)``. Database rows are counted only when exportable
    (GUID-bearing, non-sentence, in an approved status), matching what an export
    would write. Unlike a plain key-set comparison, a key present on both sides
    whose release-bearing fields differ is reported as ``changed`` rather than
    ``in_both`` — those are exactly the rows an import would silently overwrite.
    """

    categories: List[LemmaAudioCategoryDiff] = field(default_factory=list)

    @property
    def release_keys(self) -> int:
        return sum(
            category.only_in_release + category.changed + category.identical
            for category in self.categories
        )

    @property
    def db_keys(self) -> int:
        return sum(
            category.only_in_db + category.changed + category.identical
            for category in self.categories
        )

    @property
    def only_in_release(self) -> int:
        return sum(category.only_in_release for category in self.categories)

    @property
    def only_in_db(self) -> int:
        return sum(category.only_in_db for category in self.categories)

    @property
    def changed(self) -> int:
        return sum(category.changed for category in self.categories)

    @property
    def identical(self) -> int:
        return sum(category.identical for category in self.categories)

    @property
    def differing(self) -> int:
        return sum(category.differing for category in self.categories)

    @property
    def differing_categories(self) -> List[LemmaAudioCategoryDiff]:
        """Categories with at least one difference, for listing in the UI."""
        return [category for category in self.categories if category.differing]


def parse_lemma_audio_key_token(token: str) -> Optional[LemmaAudioKey]:
    """Parse a :attr:`LemmaAudioDiffEntry.key_token` back into a lemma-audio key.

    Returns None for malformed tokens so caller-supplied form values cannot
    produce a partially-formed key.
    """
    try:
        parsed = json.loads(token)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or len(parsed) != 4:
        return None
    guid, language_code, voice_name, grammatical_form = parsed
    if not isinstance(guid, str) or not isinstance(language_code, str):
        return None
    if not isinstance(voice_name, str):
        return None
    if grammatical_form is not None and not isinstance(grammatical_form, str):
        return None
    return (guid, language_code, voice_name, grammatical_form)


def summarize_lemma_audio_release_diff(
    session: Any,
    release_dir: str,
    categories: Optional[Collection[LemmaAudioCategory]] = None,
) -> LemmaAudioReleaseDiff:
    """Compare exportable lemma audio in ``session`` against the release files.

    Read-only: mutates nothing, used to preview a sync in the Barsukas UI.

    Args:
        session: Open SQLAlchemy session to read audio rows from.
        release_dir: Release lemmas directory (parent of the per-category files).
        categories: If given, restrict the comparison to these categories.
    """
    from storage.models.schema import AudioQualityReview, Lemma

    wanted = set(categories) if categories is not None else None

    release_entries: Dict[LemmaAudioKey, Dict[str, Any]] = {}
    release_category_by_key: Dict[LemmaAudioKey, LemmaAudioCategory] = {}
    for category, key, entry in _iter_release_lemma_audio_entries(release_dir, categories):
        release_entries[key] = entry
        release_category_by_key[key] = category

    db_entries: Dict[LemmaAudioKey, Dict[str, Any]] = {}
    db_category_by_key: Dict[LemmaAudioKey, LemmaAudioCategory] = {}
    english_by_guid: Dict[str, str] = {}
    exportable = (
        session.query(AudioQualityReview, Lemma)
        .join(Lemma, AudioQualityReview.guid == Lemma.guid)
        .filter(AudioQualityReview.guid.isnot(None))
        .filter(AudioQualityReview.sentence_id.is_(None))
        .filter(AudioQualityReview.status.in_(APPROVED_AUDIO_RELEASE_STATUSES))
        .all()
    )
    for audio_review, lemma in exportable:
        category = (
            lemma.pos_type.lower() if lemma.pos_type else "misc",
            lemma.pos_subtype.lower() if lemma.pos_subtype else "other",
        )
        if wanted is not None and category not in wanted:
            continue
        key = (
            audio_review.guid,
            audio_review.language_code,
            audio_review.voice_name,
            audio_review.grammatical_form,
        )
        db_entries[key] = _lemma_audio_entry_from_review(audio_review)
        db_category_by_key[key] = category
        english_by_guid[audio_review.guid] = lemma.lemma_text

    entries_by_category: Dict[LemmaAudioCategory, List[LemmaAudioDiffEntry]] = defaultdict(list)
    for key in set(release_entries) | set(db_entries):
        guid, language_code, voice_name, grammatical_form = key
        release_entry = release_entries.get(key)
        db_entry = db_entries.get(key)

        if release_entry is None:
            state = "only_in_db"
            changed_fields: Dict[str, Tuple[Any, Any]] = {}
        elif db_entry is None:
            state = "only_in_release"
            changed_fields = {}
        else:
            changed_fields = {
                release_field: (release_entry.get(release_field), db_entry.get(release_field))
                for release_field in LEMMA_AUDIO_RELEASE_FIELDS
                if release_field in release_entry
                and release_entry.get(release_field) != db_entry.get(release_field)
            }
            state = "changed" if changed_fields else "identical"

        # Prefer the database's category: it is what an export would write, and
        # for release-only rows the file's own location is the only signal.
        category = db_category_by_key.get(key) or release_category_by_key[key]
        entries_by_category[category].append(
            LemmaAudioDiffEntry(
                guid=guid,
                language_code=language_code,
                voice_name=voice_name,
                grammatical_form=grammatical_form,
                state=state,
                english=english_by_guid.get(guid),
                changed_fields=changed_fields,
            )
        )

    category_diffs = []
    for category in sorted(entries_by_category):
        entries = sorted(
            entries_by_category[category],
            key=lambda entry: (entry.guid, entry.language_code, entry.voice_name),
        )
        category_diffs.append(
            LemmaAudioCategoryDiff(pos_type=category[0], pos_subtype=category[1], entries=entries)
        )

    return LemmaAudioReleaseDiff(categories=category_diffs)


def import_lemma_audio_release_to_sqlite(
    sqlite_path: str,
    release_dir: str,
    prune: bool = False,
    categories: Optional[Collection[LemmaAudioCategory]] = None,
) -> None:
    """Sync approved lemma audio from data/release back into SQLite.

    This is the inverse of :func:`export_sqlite_to_lemma_audio_release`. It reads
    every ``audio.jsonl`` under ``release_dir`` and upserts the audio rows into an
    existing SQLite database's ``audio_quality_reviews`` table, matched on the
    lemma-audio unique key ``(guid, language_code, voice_name, grammatical_form)``.

    Only the release-bearing columns are written on update; locally-held review
    metadata (``reviewed_by``, ``quality_issues``, ``notes``, acceptance columns)
    on an existing row is left untouched. ``lemma_id`` is resolved from the GUID.
    Opens (and closes) its own session from ``sqlite_path``;
    :func:`import_lemma_audio_release_into_session` is the session-based core.

    Args:
        sqlite_path: Path to the SQLite database to sync into.
        release_dir: Release lemmas directory (e.g. ``data/release/lemmas``), the
            parent of the per-category ``audio.jsonl`` files.
        prune: If True, delete lemma-audio rows in an exportable status that are
            no longer present in the release files (the inverse of export). Rows
            without a GUID (sentence audio) and rows in non-exportable statuses
            are never pruned, and when ``categories`` is set only rows in those
            categories are eligible.
        categories: If given, only read these ``(pos_type, pos_subtype)``
            categories' files.
    """
    print(f"Syncing lemma audio from release ({release_dir}) into SQLite ({sqlite_path})...")

    from storage.database import create_database_session
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)
    try:
        import_lemma_audio_release_into_session(
            session, release_dir, prune=prune, categories=categories
        )
    finally:
        session.close()


def _resolve_primary_lemma_category(sentence: Any) -> Tuple[str, str]:
    """Resolve the primary lemma category for directory placement.

    Returns (pos_type, pos_subtype) based on the noun with the lowest GUID
    among the sentence's word hints.  Falls back to any lemma with the
    lowest GUID, or ("misc", "misc") if nothing resolves.
    """
    lemmas_with_guids = []
    for pw in sentence.word_hints:
        if pw.lemma and pw.lemma.guid:
            lemmas_with_guids.append(pw.lemma)

    if not lemmas_with_guids:
        return ("misc", "misc")

    # Prefer nouns
    nouns = [l for l in lemmas_with_guids if l.pos_type and l.pos_type.lower() == "noun"]
    if nouns:
        best = min(nouns, key=lambda l: l.guid)
    else:
        best = min(lemmas_with_guids, key=lambda l: l.guid)

    pos_type = best.pos_type.lower() if best.pos_type else "misc"
    pos_subtype = best.pos_subtype.lower() if best.pos_subtype else "other"
    return (pos_type, pos_subtype)


def _sentence_to_release_record(sentence: Any) -> Dict[str, Any]:
    """Convert a Sentence ORM object to a release JSONL record."""
    from storage.translation_helpers import RELEASE_LANGUAGES

    release_lang_set = set(RELEASE_LANGUAGES)
    translations: Dict[str, str] = {}
    for trans in sentence.translations:
        if trans.language_code not in release_lang_set:
            continue
        if trans.translation_text and trans.translation_text.strip():
            translations[trans.language_code] = trans.translation_text

    word_hints: List[Dict[str, Any]] = []
    for pw in sorted(sentence.word_hints, key=lambda p: p.position):
        lemma_guid = pw.lemma.guid if pw.lemma and pw.lemma.guid else None
        word_hints.append(
            {
                "position": pw.position,
                "slot_name": pw.slot_name,
                "lemma_guid": lemma_guid,
                # See _sentence_word_to_dict: a name-filled slot has to stay
                # distinguishable from an unresolved one.
                "name_guid": pw.name.guid if pw.name and pw.name.guid else None,
                "english_text": pw.english_text,
            }
        )

    record: Dict[str, Any] = {
        "guid": sentence.guid,
    }
    if sentence.sentence_collection:
        record["collection"] = sentence.sentence_collection
    if sentence.pattern_type:
        record["pattern_type"] = sentence.pattern_type
    if sentence.tense:
        record["tense"] = sentence.tense
    if sentence.minimum_level is not None:
        record["minimum_level"] = sentence.minimum_level
    if translations:
        record["translations"] = translations
    if word_hints:
        record["word_hints"] = word_hints
    if sentence.notes:
        record["notes"] = sentence.notes

    words: List[Dict[str, Any]] = [
        _sentence_word_to_dict(sentence_word)
        for sentence_word in sorted(
            sentence.words,
            key=lambda current_word: (current_word.language_code, current_word.position),
        )
    ]
    if words:
        record["words"] = words

    audio: List[Dict[str, Any]] = []
    for audio_review in sorted(
        sentence.audio_reviews,
        key=lambda current_audio: (current_audio.language_code, current_audio.voice_name),
    ):
        if audio_review.status not in APPROVED_AUDIO_RELEASE_STATUSES:
            continue
        audio.append(
            {
                "language_code": audio_review.language_code,
                "voice_name": audio_review.voice_name,
                "filename": audio_review.filename,
                "status": audio_review.status,
                "expected_text": audio_review.expected_text,
                "manifest_md5": audio_review.manifest_md5,
                "s3_prod_url": audio_review.s3_prod_url,
                "s3_staging_url": audio_review.s3_staging_url,
                "staging_agent": audio_review.staging_agent,
            }
        )
    if audio:
        record["audio"] = audio

    return record


def _write_jsonl_atomic(file_path: Path, records: List[Dict[str, Any]]) -> None:
    """Write JSONL file atomically.

    Args:
        file_path: Path to write to
        records: List of dictionaries to write as JSONL
    """
    # Write to temp file first
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=file_path.parent, delete=False, suffix=".tmp"
    ) as tmp_file:
        for record in records:
            tmp_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        tmp_file.flush()
        os.fsync(tmp_file.fileno())

    # Atomic rename
    os.replace(tmp_file.name, file_path)


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
        default="data/release/lemmas",
        help="Path to release directory (default: data/release/lemmas)",
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
        default="data/release/sentences",
        help="Path to sentence release directory (default: data/release/sentences)",
    )
    parser.add_argument(
        "--phrase-release-dir",
        default="data/release/phrases",
        help="Path to phrase release directory (default: data/release/phrases)",
    )
    parser.add_argument(
        "--idiom-release-dir",
        default="data/release/idioms",
        help="Path to idiom release directory (default: data/release/idioms)",
    )
    parser.add_argument(
        "--name-release-dir",
        default="data/release/names",
        help="Path to name release directory (default: data/release/names)",
    )

    args = parser.parse_args()

    lemma_audio_categories: Optional[List[LemmaAudioCategory]] = None
    if args.categories:
        lemma_audio_categories = []
        for slug in args.categories:
            parsed_category = parse_lemma_audio_category_slug(slug)
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
