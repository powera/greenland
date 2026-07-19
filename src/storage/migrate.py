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
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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
        # Legacy translation fields
        chinese_translation=lemma.chinese_translation,
        french_translation=lemma.french_translation,
        korean_translation=lemma.korean_translation,
        swahili_translation=lemma.swahili_translation,
        lithuanian_translation=lemma.lithuanian_translation,
        vietnamese_translation=lemma.vietnamese_translation,
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

    # Get words. Reference lemmas by GUID (the stable, on-disk identifier used
    # throughout data/release); integer lemma_ids are ephemeral and would not
    # survive a JSONL -> SQLite reload.
    words = []
    for word in sentence.words:
        words.append(
            {
                "lemma_guid": word.lemma.guid if word.lemma else None,
                "language_code": word.language_code,
                "position": word.position,
                "word_role": word.word_role,
                "english_text": word.english_text,
                "target_language_text": word.target_language_text,
                "grammatical_form": word.grammatical_form,
                "grammatical_case": word.grammatical_case,
                "declined_form": word.declined_form,
            }
        )

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
    from storage.models.guid_tombstone import GuidTombstone
    from storage.models.schema import Lemma, NON_INFLECTION_GRAMMATICAL_FORMS

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
                selectinload(Lemma.grammar_facts),
            )
            .order_by(Lemma.id)
            .all()
        )
        print(f"Found {len(lemmas)} curated lemmas to export")

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

                # Build translations dict (only non-empty values, filtered to RELEASE_LANGUAGES)
                translations_dict: Dict[str, str] = {}
                translation_metadata_dict: Dict[str, Dict[str, str]] = {}
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
                            translations_dict[lang_code] = translation
                            if lang_code in metadata_by_lang:
                                translation_metadata_dict[lang_code] = metadata_by_lang[lang_code]
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

                # Get difficulty overrides (filtered to RELEASE_LANGUAGES)
                difficulty_overrides_dict: Dict[str, int] = {}
                for override in lemma.difficulty_overrides:
                    if override.language_code in release_lang_set:
                        difficulty_overrides_dict[override.language_code] = (
                            override.difficulty_level
                        )

                # Base concept data with translations and difficulty_overrides
                base_data: Dict[str, Any] = {
                    "guid": lemma.guid,
                    "pos_type": lemma.pos_type,
                    "pos_subtype": lemma.pos_subtype,
                    "concept_label": lemma.lemma_text,
                    "concept_definition": lemma.definition_text,
                }

                if translations_dict:
                    base_data["translations"] = translations_dict
                if translation_metadata_dict:
                    base_data["translation_metadata"] = translation_metadata_dict

                if lemma.difficulty_level is not None:
                    base_data["difficulty_level"] = lemma.difficulty_level

                if difficulty_overrides_dict:
                    base_data["difficulty_overrides"] = difficulty_overrides_dict

                if lemma.lexical_gap_reason:
                    base_data["lexical_gap_reason"] = lemma.lexical_gap_reason

                base_records.append(base_data)

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
    with the lowest GUID among pattern words, falling back to misc/misc.

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
        SentencePatternWord,
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
                selectinload(Sentence.pattern_words).selectinload(SentencePatternWord.lemma),
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


def export_sqlite_to_lemma_audio_release(sqlite_path: str, release_dir: str) -> None:
    """Export approved lemma audio from SQLite to data/release/lemmas format.

    Audio records are grouped beside lemma release records:
    {release_dir}/{pos_dir}/{pos_subtype}/audio.jsonl

    Only approved lemma audio is exported. Sentence audio is emitted by
    export_sqlite_to_sentence_release.
    """
    print(f"Exporting lemma audio from SQLite ({sqlite_path}) to release format ({release_dir})...")

    from storage.database import create_database_session
    from storage.models.schema import AudioQualityReview, Lemma

    session = create_database_session(sqlite_path)

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

        records_by_category: Dict[Tuple[str, str], Dict[str, List[Dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        # The English word each GUID's audio relates to, so audio.jsonl records
        # are self-describing without a cross-reference into base.jsonl.
        english_by_category_guid: Dict[Tuple[str, str], Dict[str, str]] = defaultdict(dict)
        for audio_review, lemma in rows:
            pos_type = lemma.pos_type.lower() if lemma.pos_type else "misc"
            pos_subtype = lemma.pos_subtype.lower() if lemma.pos_subtype else "other"
            records_by_category[(pos_type, pos_subtype)][audio_review.guid].append(
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
                    "grammatical_form": audio_review.grammatical_form,
                }
            )
            english_by_category_guid[(pos_type, pos_subtype)][audio_review.guid] = lemma.lemma_text

        for (pos_type, pos_subtype), audio_by_guid in records_by_category.items():
            dir_name = type_to_dir.get(pos_type, pos_type)
            category_dir = Path(release_dir) / dir_name / pos_subtype
            category_dir.mkdir(parents=True, exist_ok=True)
            english_by_guid = english_by_category_guid[(pos_type, pos_subtype)]
            records = []
            for guid, audio in sorted(audio_by_guid.items(), key=lambda item: item[0]):
                record: Dict[str, Any] = {"guid": guid}
                english = english_by_guid.get(guid)
                if english:
                    record["english"] = english
                record["audio"] = audio
                records.append(record)
            print(f"Exporting {len(records)} lemma audio records to {dir_name}/{pos_subtype}...")
            _write_jsonl_atomic(category_dir / "audio.jsonl", records)

        print(f"Lemma audio export complete! Exported {len(rows)} approved audio rows.")

    finally:
        session.close()


def import_lemma_audio_release_to_sqlite(
    sqlite_path: str, release_dir: str, prune: bool = False
) -> None:
    """Sync approved lemma audio from data/release back into SQLite.

    This is the inverse of :func:`export_sqlite_to_lemma_audio_release`. It reads
    every ``audio.jsonl`` under ``release_dir`` and upserts the audio rows into an
    existing SQLite database's ``audio_quality_reviews`` table, matched on the
    lemma-audio unique key ``(guid, language_code, voice_name, grammatical_form)``.

    Only the release-bearing columns are written on update; locally-held review
    metadata (``reviewed_by``, ``quality_issues``, ``notes``, acceptance columns)
    on an existing row is left untouched. ``lemma_id`` is resolved from the GUID.

    Args:
        sqlite_path: Path to the SQLite database to sync into.
        release_dir: Release lemmas directory (e.g. ``data/release/lemmas``), the
            parent of the per-category ``audio.jsonl`` files.
        prune: If True, delete lemma-audio rows in an exportable status that are
            no longer present in the release files (the inverse of export). Rows
            without a GUID (sentence audio) and rows in non-exportable statuses
            are never pruned.
    """
    print(f"Syncing lemma audio from release ({release_dir}) into SQLite ({sqlite_path})...")

    from storage.database import create_database_session
    from storage.models.schema import AudioQualityReview, Lemma
    from storage.utils.session import ensure_tables_exist

    session = create_database_session(sqlite_path)
    ensure_tables_exist(session)

    added = 0
    updated = 0
    pruned = 0

    try:
        # Map GUIDs to lemma ids so imported audio rows can be linked.
        lemma_id_by_guid: Dict[str, int] = {
            guid: lemma_id
            for guid, lemma_id in session.query(Lemma.guid, Lemma.id)
            .filter(Lemma.guid.isnot(None))
            .all()
        }

        release_keys: Set[Tuple[str, str, str, Any]] = set()

        for audio_file in sorted(Path(release_dir).rglob("audio.jsonl")):
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
                        grammatical_form = entry.get("grammatical_form")
                        release_keys.add((guid, language_code, voice_name, grammatical_form))

                        existing = (
                            session.query(AudioQualityReview)
                            .filter(
                                AudioQualityReview.guid == guid,
                                AudioQualityReview.language_code == language_code,
                                AudioQualityReview.voice_name == voice_name,
                                (
                                    AudioQualityReview.grammatical_form.is_(grammatical_form)
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
                        else:
                            existing.filename = entry.get("filename", existing.filename)
                            existing.expected_text = entry.get(
                                "expected_text", existing.expected_text
                            )
                            existing.manifest_md5 = entry.get("manifest_md5", existing.manifest_md5)
                            existing.status = entry.get("status", existing.status)
                            existing.s3_prod_url = entry.get("s3_prod_url", existing.s3_prod_url)
                            existing.s3_staging_url = entry.get(
                                "s3_staging_url", existing.s3_staging_url
                            )
                            existing.staging_agent = entry.get(
                                "staging_agent", existing.staging_agent
                            )
                            if existing.lemma_id is None:
                                existing.lemma_id = lemma_id_by_guid.get(guid)
                            updated += 1

        if prune:
            exportable = (
                session.query(AudioQualityReview)
                .filter(AudioQualityReview.guid.isnot(None))
                .filter(AudioQualityReview.sentence_id.is_(None))
                .filter(AudioQualityReview.status.in_(APPROVED_AUDIO_RELEASE_STATUSES))
                .all()
            )
            for review in exportable:
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
        summary = f"Lemma audio sync complete! Added {added}, updated {updated}"
        if prune:
            summary += f", pruned {pruned}"
        print(summary + ".")

    finally:
        session.close()


def _resolve_primary_lemma_category(sentence: Any) -> Tuple[str, str]:
    """Resolve the primary lemma category for directory placement.

    Returns (pos_type, pos_subtype) based on the noun with the lowest GUID
    among the sentence's pattern words.  Falls back to any lemma with the
    lowest GUID, or ("misc", "misc") if nothing resolves.
    """
    lemmas_with_guids = []
    for pw in sentence.pattern_words:
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

    pattern_words: List[Dict[str, Any]] = []
    for pw in sorted(sentence.pattern_words, key=lambda p: p.position):
        lemma_guid = pw.lemma.guid if pw.lemma and pw.lemma.guid else None
        pattern_words.append(
            {
                "position": pw.position,
                "slot_name": pw.slot_name,
                "lemma_guid": lemma_guid,
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
    if pattern_words:
        record["pattern_words"] = pattern_words
    if sentence.notes:
        record["notes"] = sentence.notes

    words: List[Dict[str, Any]] = []
    for sentence_word in sorted(
        sentence.words, key=lambda current_word: (current_word.language_code, current_word.position)
    ):
        lemma_guid = (
            sentence_word.lemma.guid if sentence_word.lemma and sentence_word.lemma.guid else None
        )
        words.append(
            {
                "language_code": sentence_word.language_code,
                "position": sentence_word.position,
                "word_role": sentence_word.word_role,
                "lemma_guid": lemma_guid,
                "english_text": sentence_word.english_text,
                "target_language_text": sentence_word.target_language_text,
                "grammatical_form": sentence_word.grammatical_form,
                "grammatical_case": sentence_word.grammatical_case,
                "declined_form": sentence_word.declined_form,
            }
        )
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
            "jsonl-to-sqlite",
            "sqlite-to-release",
            "sqlite-to-sentence-release",
            "sqlite-to-phrase-release",
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
        "--jsonl-release-dir",
        default="data/release",
        help=(
            "Path to the JSONL release data directory for jsonl-to-sqlite "
            "(parent of lemmas/, sentences/, etc.; default: data/release)"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing non-empty target database (jsonl-to-sqlite)",
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
        "--sentence-release-dir",
        default="data/release/sentences",
        help="Path to sentence release directory (default: data/release/sentences)",
    )
    parser.add_argument(
        "--phrase-release-dir",
        default="data/release/phrases",
        help="Path to phrase release directory (default: data/release/phrases)",
    )

    args = parser.parse_args()

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
    elif args.direction == "sqlite-to-lemma-audio-release":
        export_sqlite_to_lemma_audio_release(args.sqlite_path, args.release_dir)
    elif args.direction == "lemma-audio-release-to-sqlite":
        import_lemma_audio_release_to_sqlite(args.sqlite_path, args.release_dir, prune=args.prune)
    elif args.direction == "jsonl-to-sqlite":
        import_jsonl_to_sqlite(args.jsonl_release_dir, args.sqlite_path, force=args.force)
    else:
        print(f"Unknown migration direction: {args.direction}")
        sys.exit(1)


if __name__ == "__main__":
    main()
