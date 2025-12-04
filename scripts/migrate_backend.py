#!/usr/bin/env python3
"""Migrate data between SQLite and JSONL storage backends.

This script allows you to export data from SQLite to JSONL format,
or import data from JSONL to SQLite.
"""

import argparse
import sys
import os
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import constants
from wordfreq.storage.backend.config import BackendConfig, BackendType
from wordfreq.storage.backend.factory import create_session


def export_sqlite_to_jsonl(sqlite_path: str, jsonl_dir: str):
    """Export all data from SQLite to JSONL format.

    Args:
        sqlite_path: Path to SQLite database
        jsonl_dir: Directory to write JSONL files
    """
    print(f"Exporting from SQLite ({sqlite_path}) to JSONL ({jsonl_dir})...")

    # Create source session (SQLite) - use wrapped session
    source_config = BackendConfig(backend_type=BackendType.SQLITE, sqlite_path=sqlite_path)
    source_session_wrapper = create_session(source_config)

    # Get the underlying SQLAlchemy session for compatibility
    source_session = source_session_wrapper._sqlalchemy_session

    # Create target session (JSONL)
    target_config = BackendConfig(backend_type=BackendType.JSONL, jsonl_data_dir=jsonl_dir)
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

        # Export Sentences (DISABLED FOR NOW)
        print("Skipping sentences (disabled)...")
        # sentences = source_session.query(SQLiteSentence).all()
        # print(f"Found {len(sentences)} sentences")
        #
        # for sentence in sentences:
        #     jsonl_sentence = convert_sqlalchemy_sentence_to_jsonl(sentence)
        #     target_session.add(jsonl_sentence)

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
    translations = {}
    for lang_code in ["lt", "zh", "ko", "fr", "sw", "vi"]:
        trans_text = translation_helpers.get_translation(session, lemma, lang_code)
        if trans_text:
            translations[lang_code] = trans_text

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

    # Create JSONL lemma
    return jsonl_models.Lemma(
        id=lemma.id,
        guid=lemma.guid,
        lemma_text=lemma.lemma_text,
        definition_text=lemma.definition_text,
        pos_type=lemma.pos_type,
        pos_subtype=lemma.pos_subtype,
        difficulty_level=lemma.difficulty_level,
        frequency_rank=lemma.frequency_rank,
        tags=lemma.tags,
        chinese_translation=lemma.chinese_translation,
        french_translation=lemma.french_translation,
        korean_translation=lemma.korean_translation,
        swahili_translation=lemma.swahili_translation,
        lithuanian_translation=lemma.lithuanian_translation,
        vietnamese_translation=lemma.vietnamese_translation,
        disambiguation=lemma.disambiguation,
        confidence=lemma.confidence,
        verified=lemma.verified,
        notes=lemma.notes,
        added_at=lemma.added_at,
        updated_at=lemma.updated_at,
        translations=translations,
        difficulty_overrides=difficulty_overrides,
        derivative_forms=derivative_forms,
        grammar_facts=grammar_facts,
        audio_hashes={},
    )


def convert_sqlalchemy_sentence_to_jsonl(sentence):
    """Convert SQLAlchemy Sentence to JSONL dataclass."""
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


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migrate data between storage backends")
    parser.add_argument(
        "direction",
        choices=["sqlite-to-jsonl", "jsonl-to-sqlite"],
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

    args = parser.parse_args()

    if args.direction == "sqlite-to-jsonl":
        export_sqlite_to_jsonl(args.sqlite_path, args.jsonl_dir)
    else:
        print("JSONL to SQLite migration not yet implemented")
        sys.exit(1)


if __name__ == "__main__":
    main()
