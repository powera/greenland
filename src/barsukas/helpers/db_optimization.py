#!/usr/bin/python3

"""
Database optimization helpers for BARSUKAS.

This module provides optimized database query functions that reduce the number
of round-trips to the database, which is especially important when using
PostgreSQL over a network connection.
"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from storage.crud.guid_tombstone import get_tombstones_by_lemma_id
from storage.models.grammar_fact import GrammarFact
from storage.models.lemma_relation import LemmaRelationGroup, LemmaRelationMember
from storage.models.schema import (
    AudioQualityReview,
    DerivativeForm,
    Lemma,
    LemmaDifficultyOverride,
    LemmaTranslation,
    Sentence,
    SentenceWord,
)
from storage.models.variant_form import VariantForm
from storage.translation_helpers import LANGUAGE_FIELDS


def get_home_page_stats(session: Session) -> Dict[str, int]:
    """
    Get home page statistics in a single optimized query.

    Replaces 4 separate COUNT queries with 1 query using conditional aggregation.

    Returns:
        Dictionary with keys: total_lemmas, verified_lemmas, with_difficulty, total_sentences
    """
    # Combine lemma stats into a single query with conditional counts
    lemma_stats = session.query(
        func.count(Lemma.id).label("total"),
        func.count(case((Lemma.verified == True, 1))).label("verified"),
        func.count(case((Lemma.difficulty_level.isnot(None), 1))).label("with_difficulty"),
    ).first()

    # Sentence count as a separate query (different table)
    sentence_count = session.query(func.count(Sentence.id)).scalar()

    return {
        "total_lemmas": lemma_stats.total if lemma_stats else 0,
        "verified_lemmas": lemma_stats.verified if lemma_stats else 0,
        "with_difficulty": lemma_stats.with_difficulty if lemma_stats else 0,
        "total_sentences": sentence_count or 0,
    }


def get_audio_dashboard_stats(session: Session) -> Dict[str, Any]:
    """
    Get audio dashboard statistics in optimized queries.

    Combines 6 separate queries into 2 queries using conditional aggregation.

    Returns:
        Dictionary with keys: total_files, pending_review, approved, needs_replacement,
        language_counts, voice_counts, language_pending_lemma, language_pending_sentence
    """
    # Combine status counts into single query with conditional aggregation
    stats = session.query(
        func.count(AudioQualityReview.id).label("total"),
        func.count(case((AudioQualityReview.status == "pending_review", 1))).label(
            "pending_review"
        ),
        func.count(case((AudioQualityReview.status == "approved", 1))).label("approved"),
        func.count(case((AudioQualityReview.status == "needs_replacement", 1))).label(
            "needs_replacement"
        ),
    ).first()

    # Get grouped counts in one query (language + voice), including per-group
    # pending-review splits for lemma vs sentence audio.
    grouped_counts = (
        session.query(
            AudioQualityReview.language_code,
            AudioQualityReview.display_voice,
            func.count(AudioQualityReview.id).label("count"),
            func.count(
                case(
                    (
                        and_(
                            AudioQualityReview.status == "pending_review",
                            AudioQualityReview.sentence_id.is_(None),
                        ),
                        1,
                    )
                )
            ).label("pending_lemma"),
            func.count(
                case(
                    (
                        and_(
                            AudioQualityReview.status == "pending_review",
                            AudioQualityReview.sentence_id.isnot(None),
                        ),
                        1,
                    )
                )
            ).label("pending_sentence"),
        )
        .group_by(AudioQualityReview.language_code, AudioQualityReview.display_voice)
        .all()
    )

    # Process grouped counts into per-language and per-voice aggregates
    language_counts: Dict[str, int] = {}
    voice_counts: Dict[str, int] = {}
    language_pending_lemma: Dict[str, int] = {}
    language_pending_sentence: Dict[str, int] = {}

    for row in grouped_counts:
        # Aggregate language counts
        if row.language_code not in language_counts:
            language_counts[row.language_code] = 0
            language_pending_lemma[row.language_code] = 0
            language_pending_sentence[row.language_code] = 0
        language_counts[row.language_code] += row.count
        language_pending_lemma[row.language_code] += row.pending_lemma
        language_pending_sentence[row.language_code] += row.pending_sentence

        # Voice counts (already grouped by language/voice)
        if row.display_voice:
            voice_counts[row.display_voice] = row.count

    return {
        "total_files": stats.total if stats else 0,
        "pending_review": stats.pending_review if stats else 0,
        "approved": stats.approved if stats else 0,
        "needs_replacement": stats.needs_replacement if stats else 0,
        "language_counts": language_counts,
        "voice_counts": voice_counts,
        "language_pending_lemma": language_pending_lemma,
        "language_pending_sentence": language_pending_sentence,
    }


def get_rapid_review_filter_options(session: Session) -> Dict[str, List[Any]]:
    """
    Get all filter options for rapid review in optimized queries.

    Combines 4 separate DISTINCT queries into 2 queries.

    Returns:
        Dictionary with keys: languages, voices, subtypes, levels
    """
    # Query 1: Get distinct languages and voices from AudioQualityReview
    audio_distincts = (
        session.query(
            AudioQualityReview.language_code,
            AudioQualityReview.display_voice,
        )
        .distinct()
        .all()
    )

    languages = sorted(set(row.language_code for row in audio_distincts if row.language_code))
    voices = sorted(
        set(row.display_voice for row in audio_distincts if row.display_voice),
        key=lambda x: x or "",
    )

    # Query 2: Get distinct subtypes and levels from Lemmas that have audio
    lemma_distincts = (
        session.query(Lemma.pos_subtype, Lemma.difficulty_level)
        .join(AudioQualityReview, AudioQualityReview.lemma_id == Lemma.id)
        .distinct()
        .all()
    )

    subtypes = sorted(set(row.pos_subtype for row in lemma_distincts if row.pos_subtype))
    levels = sorted(
        set(row.difficulty_level for row in lemma_distincts if row.difficulty_level is not None)
    )

    return {
        "languages": languages,
        "voices": voices,
        "subtypes": subtypes,
        "levels": levels,
    }


def get_lemma_list_filter_options(
    session: Session, pos_type_filter: Optional[str] = None
) -> Dict[str, List[str]]:
    """
    Get filter options for lemma list in optimized queries.

    Combines 2 separate DISTINCT queries into 1 query when possible.

    Args:
        pos_type_filter: Optional POS type to filter subtypes

    Returns:
        Dictionary with keys: pos_types, pos_subtypes
    """
    # Single query to get both pos_types and pos_subtypes
    query = session.query(Lemma.pos_type, Lemma.pos_subtype).distinct()

    if pos_type_filter:
        # If filtering by pos_type, we still need all pos_types for the dropdown
        # but only subtypes for the filtered type
        all_types_query = session.query(Lemma.pos_type).distinct().order_by(Lemma.pos_type)
        pos_types = [p[0] for p in all_types_query.all() if p[0]]

        subtypes_query = (
            session.query(Lemma.pos_subtype)
            .filter(Lemma.pos_type == pos_type_filter, Lemma.pos_subtype.isnot(None))
            .distinct()
            .order_by(Lemma.pos_subtype)
        )
        pos_subtypes = [p[0] for p in subtypes_query.all() if p[0]]
    else:
        # No filter - get both in one query
        results = query.all()
        pos_types = sorted(set(r.pos_type for r in results if r.pos_type))
        pos_subtypes = sorted(set(r.pos_subtype for r in results if r.pos_subtype))

    return {
        "pos_types": pos_types,
        "pos_subtypes": pos_subtypes,
    }


def get_lemma_view_data(session: Session, lemma_id: int) -> Dict[str, Any]:
    """
    Get all data needed for lemma view page in minimal queries.

    This replaces 10+ queries with ~5 bulk queries:
    1. Lemma + translations + definitions (single query with join)
    2. Difficulty overrides (single query)
    3. Derivative forms (single query)
    4. Grammar facts (single query)
    5. Audio files (single query)
    6. Sentence count (single query)
    7. Duplicate count for disambiguation (single query)
    8. Related lemmas (single query)
    9. Variant forms (single query)
    10. Retired GUIDs for this lemma (single query)

    Args:
        session: Database session
        lemma_id: Lemma ID

    Returns:
        Dictionary with all data needed for lemma view
    """
    # Query 1: Get the lemma
    lemma = session.query(Lemma).get(lemma_id)
    if not lemma:
        return {"lemma": None}

    # Query 2: Get all LemmaTranslation rows in one query
    # This replaces both get_all_translations AND get_all_definitions
    translation_rows = (
        session.query(LemmaTranslation).filter(LemmaTranslation.lemma_id == lemma_id).all()
    )

    # Build translations, definitions, disambiguations, and translation-level pronunciation dicts
    translations: Dict[str, Optional[str]] = {"en": lemma.lemma_text}
    definitions: Dict[str, Optional[str]] = {"en": lemma.definition_text}
    translation_disambiguations: Dict[str, Optional[str]] = {"en": None}
    translation_pronunciations: Dict[str, Tuple[Optional[str], Optional[str]]] = {
        "en": (None, None)
    }

    for translation_row in translation_rows:
        translations[translation_row.language_code] = translation_row.translation
        definitions[translation_row.language_code] = translation_row.definition_text
        translation_disambiguations[translation_row.language_code] = translation_row.disambiguation
        translation_pronunciations[translation_row.language_code] = (
            translation_row.ipa_pronunciation,
            translation_row.phonetic_pronunciation,
        )

    # Fill in None for missing languages
    for lang_code in LANGUAGE_FIELDS.keys():
        if lang_code not in translations:
            translations[lang_code] = None
        if lang_code not in definitions:
            definitions[lang_code] = None
        if lang_code not in translation_disambiguations:
            translation_disambiguations[lang_code] = None
        if lang_code not in translation_pronunciations:
            translation_pronunciations[lang_code] = (None, None)

    # Query 3: Get all difficulty overrides in one query
    overrides = (
        session.query(LemmaDifficultyOverride)
        .filter(LemmaDifficultyOverride.lemma_id == lemma_id)
        .all()
    )
    override_by_lang = {o.language_code: o.difficulty_level for o in overrides}

    # Calculate effective levels without additional queries
    effective_levels: Dict[str, Optional[int]] = {}
    for lang_code in LANGUAGE_FIELDS.keys():
        if lang_code in override_by_lang:
            effective_levels[lang_code] = override_by_lang[lang_code]
        else:
            effective_levels[lang_code] = lemma.difficulty_level

    # Query 4: Get derivative forms
    derivative_forms = (
        session.query(DerivativeForm)
        .filter(DerivativeForm.lemma_id == lemma_id)
        .order_by(
            DerivativeForm.language_code,
            DerivativeForm.is_base_form.desc(),
            DerivativeForm.grammatical_form,
        )
        .all()
    )

    # Query 5: Get grammar facts
    grammar_facts = (
        session.query(GrammarFact)
        .filter(GrammarFact.lemma_id == lemma_id)
        .order_by(GrammarFact.language_code, GrammarFact.fact_type)
        .all()
    )

    # Query 6: Get audio files
    audio_files = (
        session.query(AudioQualityReview)
        .filter(AudioQualityReview.lemma_id == lemma_id)
        .order_by(AudioQualityReview.language_code, AudioQualityReview.voice_name)
        .all()
    )

    # Query 7: Sentence count (for nouns only)
    sentence_count = 0
    if lemma.pos_type == "noun":
        sentence_count = (
            session.query(func.count(SentenceWord.id))
            .filter(SentenceWord.lemma_id == lemma_id)
            .scalar()
            or 0
        )

    # Query 8: Duplicate count for disambiguation
    needs_disambiguation_check = False
    if lemma.lemma_text and "(" not in lemma.lemma_text:
        duplicate_count = (
            session.query(func.count(Lemma.id))
            .filter(
                Lemma.lemma_text == lemma.lemma_text,
                Lemma.guid.isnot(None),
                Lemma.id != lemma_id,
            )
            .scalar()
            or 0
        )
        needs_disambiguation_check = duplicate_count > 0

    # Query 9: Get related lemmas via relation groups
    # Find groups this lemma belongs to, then all other members
    related_lemmas: List[Tuple[str, Lemma]] = []
    member_rows = (
        session.query(LemmaRelationMember).filter(LemmaRelationMember.lemma_id == lemma_id).all()
    )
    if member_rows:
        group_ids = [m.group_id for m in member_rows]
        sibling_members = (
            session.query(LemmaRelationMember, LemmaRelationGroup.concept_label)
            .join(LemmaRelationGroup, LemmaRelationMember.group_id == LemmaRelationGroup.id)
            .filter(
                LemmaRelationMember.group_id.in_(group_ids),
                LemmaRelationMember.lemma_id != lemma_id,
            )
            .all()
        )
        sibling_lemma_ids = [m.lemma_id for m, _ in sibling_members]
        if sibling_lemma_ids:
            sibling_lemmas = {
                l.id: l for l in session.query(Lemma).filter(Lemma.id.in_(sibling_lemma_ids)).all()
            }
            for member, concept_label in sibling_members:
                sibling = sibling_lemmas.get(member.lemma_id)
                if sibling:
                    related_lemmas.append((concept_label, sibling))

    # Query 10: Variant forms (alternate spellings). Queried separately from
    # derivative_forms on purpose -- a variant is the same lexeme as the lemma
    # and must not appear among its inflections; see storage.models.variant_form.
    variant_forms = (
        session.query(VariantForm)
        .filter(VariantForm.lemma_id == lemma_id)
        .order_by(
            VariantForm.language_code,
            VariantForm.variant_key,
            VariantForm.is_base_form.desc(),
            VariantForm.grammatical_form,
        )
        .all()
    )

    # Query 11: GUIDs this lemma used to have. A lemma picks up a tombstone when
    # its part of speech is corrected or its GUID is reassigned by hand, and the
    # old number is retired for good, so the detail page can show where it has
    # been. The query plan above has claimed this since before it was written.
    tombstones = get_tombstones_by_lemma_id(session, lemma_id)

    return {
        "lemma": lemma,
        "translations": translations,
        "definitions": definitions,
        "translation_disambiguations": translation_disambiguations,
        "translation_pronunciations": translation_pronunciations,
        "overrides": overrides,
        "effective_levels": effective_levels,
        "derivative_forms": derivative_forms,
        "variant_forms": variant_forms,
        "grammar_facts": grammar_facts,
        "audio_files": audio_files,
        "sentence_count": sentence_count,
        "needs_disambiguation_check": needs_disambiguation_check,
        "related_lemmas": related_lemmas,
        "tombstones": tombstones,
    }


def bulk_get_translations_for_lemmas(
    session: Session, lemmas: List[Lemma]
) -> Dict[int, Dict[str, Optional[str]]]:
    """
    Get all translations for multiple lemmas in a single query.

    This is used by the API search endpoint to avoid N+1 queries.

    Args:
        session: Database session
        lemmas: List of Lemma objects

    Returns:
        Dictionary mapping lemma_id to dict of {lang_code: translation}
    """
    if not lemmas:
        return {}

    lemma_ids = [lemma.id for lemma in lemmas]

    # Single query for all translations
    translation_rows = (
        session.query(LemmaTranslation).filter(LemmaTranslation.lemma_id.in_(lemma_ids)).all()
    )

    # Build result dict
    result: Dict[int, Dict[str, Optional[str]]] = {}

    # Initialize with lemma_text (English) for each lemma
    for lemma in lemmas:
        result[lemma.id] = {"en": lemma.lemma_text}

    # Add translations from LemmaTranslation table
    for t in translation_rows:
        if t.lemma_id not in result:
            result[t.lemma_id] = {}
        result[t.lemma_id][t.language_code] = t.translation

    return result
