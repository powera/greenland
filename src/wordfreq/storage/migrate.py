#!/usr/bin/env python3
"""Migrate data between SQLite and JSONL storage backends.

This script allows you to export data from SQLite to JSONL format,
or import data from JSONL to SQLite.
"""

import argparse
import sys
import os
import json
import tempfile
from pathlib import Path
from collections import defaultdict
from typing import Dict, Set

# Add src to path if running as script
if __name__ == "__main__":
    src_path = str(Path(__file__).parent.parent.parent)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

import constants
from wordfreq.storage.backend.config import DataSourceConfig, BackendType
from wordfreq.storage.backend.factory import create_session


def export_sqlite_to_jsonl(sqlite_path: str, jsonl_dir: str):
    """Export all data from SQLite to JSONL format.

    Args:
        sqlite_path: Path to SQLite database
        jsonl_dir: Directory to write JSONL files
    """
    print(f"Exporting from SQLite ({sqlite_path}) to JSONL ({jsonl_dir})...")

    # Create source session (SQLite) - use wrapped session
    source_config = DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=sqlite_path)
    source_session_wrapper = create_session(source_config)

    # Get the underlying SQLAlchemy session for compatibility
    source_session = source_session_wrapper._sqlalchemy_session

    # Create target session (JSONL)
    target_config = DataSourceConfig(backend_type=BackendType.JSONL, jsonl_data_dir=jsonl_dir)
    target_session = create_session(target_config)

    # Import models
    from wordfreq.storage.models.schema import (
        Lemma as SQLiteLemma,
        Sentence as SQLiteSentence,
        AudioQualityReview as SQLiteAudioQualityReview,
    )
    from wordfreq.storage.models.operation_log import OperationLog as SQLiteOperationLog
    from wordfreq.storage.models.guid_tombstone import GuidTombstone as SQLiteGuidTombstone
    from wordfreq.storage.backend.jsonl import models as jsonl_models

    try:
        # Export Lemmas
        print("Exporting lemmas...")
        lemmas = source_session.query(SQLiteLemma).all()
        print(f"Found {len(lemmas)} lemmas")

        for lemma in lemmas:
            # Convert SQLAlchemy lemma to JSONL dataclass
            jsonl_lemma = convert_sqlalchemy_lemma_to_jsonl(lemma, source_session)
            target_session.add(jsonl_lemma)

        # Export Sentences
        print("Exporting sentences...")
        sentences = source_session.query(SQLiteSentence).all()
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
        source_session_wrapper.close()
        target_session.close()


def convert_sqlalchemy_lemma_to_jsonl(lemma, session):
    """Convert SQLAlchemy Lemma to JSONL dataclass."""
    from wordfreq.storage.backend.jsonl import models as jsonl_models
    from wordfreq.storage import translation_helpers

    # Get translations from the new translation table
    all_translations = translation_helpers.get_all_translations(session, lemma)
    # Remove None values
    all_translations = {k: v for k, v in all_translations.items() if v is not None}

    # Separate English from other translations
    # English now goes into translations dict like all other languages
    translations = all_translations.copy()

    # Get difficulty overrides
    difficulty_overrides = {}
    for override in lemma.difficulty_overrides:
        difficulty_overrides[override.language_code] = override.difficulty_level

    # Get derivative forms
    derivative_forms = {}
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
        grammar_facts.append({
            "language_code": fact.language_code,
            "fact_type": fact.fact_type,
            "fact_value": fact.fact_value,
            "notes": fact.notes,
            "verified": fact.verified,
        })

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
        added_at=lemma.added_at,
        updated_at=lemma.updated_at,
        # Language-specific data (now includes English in translations)
        translations=translations,
        difficulty_overrides=difficulty_overrides,
        derivative_forms=derivative_forms,
        grammar_facts=grammar_facts,
        audio_hashes={},
    )


def convert_sqlalchemy_sentence_to_jsonl(sentence):
    """Convert SQLAlchemy Sentence to JSONL dataclass.

    Sentences are split into different locations based on their source:
    - If source_filename starts with "pattern:": goes to sentences/pattern/{pattern_id}.jsonl (BUIVOLAS pattern sentences)
    - Elif source_filename is set: goes to sentences/group/{source_filename}.jsonl (ZVIRDLIS grouped sentences)
    - Else: goes to sentences/misc/misc.jsonl (miscellaneous sentences)
    """
    from wordfreq.storage.backend.jsonl import models as jsonl_models

    # Get translations
    translations = {}
    for trans in sentence.translations:
        translations[trans.language_code] = trans.translation_text

    # Get words
    words = []
    for word in sentence.words:
        words.append({
            "lemma_id": word.lemma_id,
            "language_code": word.language_code,
            "position": word.position,
            "word_role": word.word_role,
            "english_text": word.english_text,
            "target_language_text": word.target_language_text,
            "grammatical_form": word.grammatical_form,
            "grammatical_case": word.grammatical_case,
            "declined_form": word.declined_form,
        })

    return jsonl_models.Sentence(
        id=sentence.id,
        guid=f"S_{sentence.id:06d}",  # Generate GUID
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


def convert_sqlalchemy_audio_review_to_jsonl(review):
    """Convert SQLAlchemy AudioQualityReview to JSONL dataclass."""
    from wordfreq.storage.backend.jsonl import models as jsonl_models

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


def convert_sqlalchemy_operation_log_to_jsonl(log):
    """Convert SQLAlchemy OperationLog to JSONL dataclass."""
    from wordfreq.storage.backend.jsonl import models as jsonl_models

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


def convert_sqlalchemy_tombstone_to_jsonl(tombstone):
    """Convert SQLAlchemy GuidTombstone to JSONL dataclass."""
    from wordfreq.storage.backend.jsonl import models as jsonl_models

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


def export_sqlite_to_release(sqlite_path: str, release_dir: str):
    """Export SQLite to data/release format with separate language files.

    This creates:
    - base.jsonl: concept definitions (guid, pos_type, pos_subtype, concept_label, concept_definition, difficulty_level)
    - {lang}.jsonl: translations for each language (guid, translation)

    Args:
        sqlite_path: Path to SQLite database
        release_dir: Directory to write release files (e.g., data/release/lemmas)
    """
    print(f"Exporting from SQLite ({sqlite_path}) to release format ({release_dir})...")

    from wordfreq.storage.database import create_database_session
    from wordfreq.storage.models.schema import Lemma
    from wordfreq.storage import translation_helpers

    session = create_database_session(sqlite_path)

    try:
        # Get all lemmas with GUIDs (curated words only)
        lemmas = session.query(Lemma).filter(Lemma.guid.isnot(None)).order_by(Lemma.id).all()
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

            # Collect data by language
            base_records = []
            lang_records: Dict[str, list] = defaultdict(list)

            for lemma in category_lemmas:
                # Base concept data
                base_data = {
                    "guid": lemma.guid,
                    "pos_type": lemma.pos_type,
                    "pos_subtype": lemma.pos_subtype,
                    "concept_label": lemma.lemma_text,
                    "concept_definition": lemma.definition_text,
                }

                if lemma.difficulty_level is not None:
                    base_data["difficulty_level"] = lemma.difficulty_level

                base_records.append(base_data)

                # Get all translations
                all_translations = translation_helpers.get_all_translations(session, lemma)

                for lang_code, translation in all_translations.items():
                    if translation and translation.strip():
                        all_languages.add(lang_code)
                        lang_records[lang_code].append({
                            "guid": lemma.guid,
                            "translation": translation
                        })

            # Write base.jsonl
            base_file = category_dir / "base.jsonl"
            _write_jsonl_atomic(base_file, base_records)

            # Write language files
            for lang_code, records in lang_records.items():
                lang_file = category_dir / f"{lang_code}.jsonl"
                _write_jsonl_atomic(lang_file, records)

        print(f"\nExport complete!")
        print(f"Languages exported: {', '.join(sorted(all_languages))}")

    finally:
        session.close()


def _write_jsonl_atomic(file_path: Path, records: list):
    """Write JSONL file atomically.

    Args:
        file_path: Path to write to
        records: List of dictionaries to write as JSONL
    """
    # Write to temp file first
    with tempfile.NamedTemporaryFile(
        mode='w',
        encoding='utf-8',
        dir=file_path.parent,
        delete=False,
        suffix='.tmp'
    ) as tmp_file:
        for record in records:
            tmp_file.write(json.dumps(record, ensure_ascii=False) + '\n')
        tmp_file.flush()
        os.fsync(tmp_file.fileno())

    # Atomic rename
    os.replace(tmp_file.name, file_path)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate data between storage backends")
    parser.add_argument(
        "direction",
        choices=["sqlite-to-jsonl", "jsonl-to-sqlite", "sqlite-to-release"],
        help="Migration direction",
    )
    parser.add_argument(
        "--sqlite-path",
        default=constants.WORDFREQ_DB_PATH,
        help=f"Path to SQLite database (default: {constants.WORDFREQ_DB_PATH})",
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

    args = parser.parse_args()

    if args.direction == "sqlite-to-jsonl":
        export_sqlite_to_jsonl(args.sqlite_path, args.jsonl_dir)
    elif args.direction == "sqlite-to-release":
        export_sqlite_to_release(args.sqlite_path, args.release_dir)
    else:
        print("JSONL to SQLite migration not yet implemented")
        sys.exit(1)


if __name__ == "__main__":
    main()
