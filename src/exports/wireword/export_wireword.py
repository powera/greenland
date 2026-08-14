#!/usr/bin/env python3
"""
WireWord format exporter for trakaido data.

This module handles exporting trakaido data to the WireWord API format,
including nouns, verbs, and complete directory exports.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from storage.backend.config import BackendType, DataSourceConfig
from storage.backend.factory import create_session
from storage.crud.difficulty_override import bulk_get_effective_difficulty_levels
from storage.models.grammar_fact import GrammarFact
from storage.models.schema import (
    SYNONYM_GRAMMATICAL_FORMS,
    AudioQualityReview,
    DerivativeForm,
    Lemma,
    WordToken,
)
from storage.translation_helpers import (
    LANGUAGE_FIELDS,
    LANGUAGE_NAMES,
    bulk_get_translations,
    get_translation,
)
from langtools.zh.converter import to_simplified, to_traditional
from exports.wireword.data_models import ExportStats, create_export_stats
from exports.wireword.readings import (
    build_target_reading_fields,
    build_target_reading_list_fields,
)
from exports.wireword.text_rendering import resolve_group_label
from exports.wireword.helpers import (
    convert_to_wireword_grammatical_form_key,
    extract_conjugation_slot,
    extract_conjugation_tense,
    format_verb_entry,
    generate_simple_grammatical_form_label,
    normalize_pos_type,
)
from exports.wireword.generate_manifest import generate_manifest
from words.cognates import detect_cognate

# Configure logging
logger = logging.getLogger(__name__)

LANGUAGE_EXPORT_MAX_LEVELS: Dict[str, int] = {
    "lt": 30,
    "es": 30,
    "fr": 20,
    "zh": 20,
}
DEFAULT_EXPORT_MAX_LEVEL = 10

# Number of difficulty levels per split file (e.g. levels 1-5, 6-10, …)
LEVEL_RANGE_SIZE = 5


class WirewordExporter:
    """Exporter for WireWord API format."""

    def __init__(
        self,
        config: Optional[DataSourceConfig] = None,
        debug: bool = False,
        language: str = "lt",
        simplified_chinese: bool = True,
        include_unreviewed_audio: bool = False,
        source_language: str = "en",
    ):
        """
        Initialize the WirewordExporter.

        Args:
            config: DataSourceConfig with backend settings (uses default SQLite if None)
            debug: Enable debug logging
            language: Target language code ('lt' for Lithuanian, 'zh' for Chinese, etc.)
            simplified_chinese: If True and language is 'zh', convert to Simplified Chinese (default: True)
            include_unreviewed_audio: If True, include audio that exists in staging but hasn't been
                reviewed yet. The manifest's audio_prefix will be changed to point to staging.
            source_language: Source language code (default: 'en'). The language the learner already
                knows. When not 'en', base_english is replaced with base_source in the output.
        """
        # Use provided config or create default SQLite config
        if config is None:
            config = DataSourceConfig(backend_type=BackendType.SQLITE)
        self.config = config
        self.debug = debug
        self.language = language
        self.simplified_chinese = simplified_chinese
        self.include_unreviewed_audio = include_unreviewed_audio
        self.source_language = source_language

        if language not in LANGUAGE_FIELDS:
            raise ValueError(
                f"Unsupported language: {language}. Supported: {', '.join(LANGUAGE_FIELDS.keys())}"
            )

        if source_language not in LANGUAGE_FIELDS:
            raise ValueError(
                f"Unsupported source language: {source_language}. "
                f"Supported: {', '.join(LANGUAGE_FIELDS.keys())}"
            )

        # Get language name from translation_helpers
        from storage.translation_helpers import get_language_name

        self.language_name = get_language_name(language)
        self.source_language_name = get_language_name(source_language)

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self) -> Any:
        """Get database session."""
        return create_session(self.config)

    def _get_max_export_level(self) -> int:
        """Return the highest difficulty level allowed for this export language."""
        return LANGUAGE_EXPORT_MAX_LEVELS.get(self.language, DEFAULT_EXPORT_MAX_LEVEL)

    def _format_missing_verb_translation_warning(
        self, missing_forms: List[Tuple[int, str, str]]
    ) -> str:
        """Build an actionable warning for missing English verb form translations."""
        total_missing = len(missing_forms)
        preview_limit = 10
        preview_rows = missing_forms[:preview_limit]
        preview_lines = [
            (
                f"- lemma_id={lemma_id}, lemma_text='{lemma_text}', "
                f"grammatical_form='{grammatical_form}'"
            )
            for lemma_id, lemma_text, grammatical_form in preview_rows
        ]
        hidden_count = total_missing - len(preview_rows)
        if hidden_count > 0:
            preview_lines.append(f"- ... and {hidden_count} more missing forms")

        details = "\n".join(preview_lines)
        return (
            "Missing English translations in database for verb forms. "
            f"Found {total_missing} missing form(s).\n"
            f"{details}\n"
            "Falling back to generated English labels for the missing forms."
        )

    def get_source_word_from_lemma(self, session: Any, lemma: Lemma) -> Optional[str]:
        """
        Get the source language word for a lemma.

        When source_language is 'en', returns lemma_text (English).
        Otherwise, fetches the translation for the source language.

        Args:
            session: Database session
            lemma: Lemma object

        Returns:
            Source language word string or None if not found
        """
        if self.source_language == "en":
            text: Optional[str] = lemma.lemma_text
            return text
        return cast(Optional[str], get_translation(session, lemma, self.source_language))

    def query_trakaido_data_for_wireword(
        self,
        session: Any,
        difficulty_level: Optional[int] = None,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Query trakaido data from the database with flexible filtering.
        Filters by translation availability using translation_helpers.

        Uses language-specific difficulty level overrides when available.

        Optimized for remote databases: uses bulk queries to minimize round trips.
        """
        from sqlalchemy import func

        from storage.models.schema import LemmaDifficultyOverride

        logger.info(f"Querying database for trakaido data (language: {self.language_name})...")

        # Build the query without language filtering (we'll filter in Python)
        # Exclude verbs explicitly - they go in separate file (wireword_verbs.json)
        query = session.query(Lemma).filter(Lemma.pos_type != "verb")

        # Apply filters
        if not include_without_guid:
            query = query.filter(Lemma.guid != None)

        if not include_unverified:
            query = query.filter(Lemma.verified == True)

        # Handle difficulty level filtering with language-specific overrides
        if difficulty_level is not None:
            # Left join with overrides to get language-specific levels
            query = query.outerjoin(
                LemmaDifficultyOverride,
                (LemmaDifficultyOverride.lemma_id == Lemma.id)
                & (LemmaDifficultyOverride.language_code == self.language),
            )
            # Use override if exists, otherwise use default
            effective_level = func.coalesce(
                LemmaDifficultyOverride.difficulty_level, Lemma.difficulty_level
            )
            query = query.filter(effective_level == difficulty_level)

        if pos_type:
            query = query.filter(Lemma.pos_type == pos_type)

        if pos_subtype:
            query = query.filter(Lemma.pos_subtype == pos_subtype)

        # Order by GUID
        query = query.order_by(Lemma.guid.asc().nullslast())

        if limit:
            # Get extra since we'll filter by translation availability
            query = query.limit(limit * 2)

        all_lemmas = query.all()
        logger.info(f"Fetched {len(all_lemmas)} lemmas from database")

        # OPTIMIZATION: Bulk fetch translations and difficulty levels in two queries
        # instead of N queries per lemma
        translations_by_id = bulk_get_translations(session, all_lemmas, self.language)
        difficulty_levels_by_id = bulk_get_effective_difficulty_levels(
            session, all_lemmas, self.language
        )

        # For non-English source languages, bulk fetch source translations
        source_translations_by_id: Dict[int, Optional[str]] = {}
        if self.source_language != "en":
            source_translations_by_id = bulk_get_translations(
                session, all_lemmas, self.source_language
            )
            logger.info(
                f"Fetched {sum(1 for v in source_translations_by_id.values() if v)} "
                f"{self.source_language_name} source translations"
            )

        # For Traditional Chinese export, also fetch zh-tw translations
        zh_tw_translations_by_id: Dict[int, Optional[str]] = {}
        if self.language == "zh" and not self.simplified_chinese:
            zh_tw_translations_by_id = bulk_get_translations(session, all_lemmas, "zh-tw")
            logger.info(
                f"Fetched {sum(1 for v in zh_tw_translations_by_id.values() if v)} zh-tw translations"
            )

        # Filter by translation availability using pre-fetched data
        lemmas = []
        for lemma in all_lemmas:
            # For non-English source, also require source translation
            if self.source_language != "en":
                source_trans = source_translations_by_id.get(lemma.id)
                if not source_trans or not source_trans.strip():
                    continue

            # For Traditional Chinese, consider both zh and zh-tw translations
            if self.language == "zh" and not self.simplified_chinese:
                zh_tw_trans = zh_tw_translations_by_id.get(lemma.id)
                zh_trans = translations_by_id.get(lemma.id)
                if (zh_tw_trans and zh_tw_trans.strip()) or (zh_trans and zh_trans.strip()):
                    lemmas.append(lemma)
                    if limit and len(lemmas) >= limit:
                        break
            else:
                translation = translations_by_id.get(lemma.id)
                if translation and translation.strip():
                    lemmas.append(lemma)
                    if limit and len(lemmas) >= limit:
                        break

        logger.info(f"Found {len(lemmas)} lemmas with {self.language_name} translations")

        # Build export data using pre-fetched translations and difficulty levels
        export_data = []
        max_export_level = self._get_max_export_level()
        logger.info(
            "Applying max export level %s for language %s",
            max_export_level,
            self.language,
        )
        for lemma in lemmas:
            target_translation = translations_by_id.get(lemma.id)

            # For Chinese, handle simplified vs traditional
            if self.language == "zh":
                if self.simplified_chinese:
                    # Convert to Simplified Chinese
                    if target_translation:
                        target_translation = to_simplified(target_translation)
                else:
                    # Traditional Chinese: prefer zh-tw, fall back to converting zh
                    zh_tw_trans = zh_tw_translations_by_id.get(lemma.id)
                    if zh_tw_trans and zh_tw_trans.strip():
                        target_translation = zh_tw_trans
                    elif target_translation:
                        # Convert zh to traditional as fallback
                        target_translation = to_traditional(target_translation)

            # Get effective difficulty level from pre-fetched data
            raw_level = difficulty_levels_by_id.get(lemma.id)

            # Skip words with no difficulty level assigned
            if raw_level is None:
                continue

            lemma_effective_level: int = raw_level

            # Skip words at level -1 (excluded from all wireword exports)
            if lemma_effective_level == -1:
                continue

            # Skip words above the language-specific export cap
            if lemma_effective_level > max_export_level:
                continue

            # Get source word: English lemma_text for English source, or translation for other sources
            if self.source_language == "en":
                source_word: Optional[str] = lemma.lemma_text
            else:
                source_word = source_translations_by_id.get(lemma.id)

            entry = {
                "GUID": lemma.guid,
                "source_word": source_word,
                "target_language": target_translation,
                "definition": lemma.definition_text,
                "pos_type": lemma.pos_type,
                "pos_subtype": lemma.pos_subtype or "general",
                "subtype": lemma.pos_subtype or "general",
                "trakaido_level": lemma_effective_level,
                "verified": lemma.verified,
                "confidence": lemma.confidence,
                "_lemma_id": lemma.id,  # Keep for bulk lookups later
            }
            export_data.append(entry)

        return export_data

    def _calculate_corpus_assignments(
        self, export_data: List[Dict[str, Any]]
    ) -> Dict[Tuple[int, str], str]:
        """
        Calculate corpus assignments based on levels and group overflow logic.

        Args:
            export_data: List of export entries

        Returns:
            Dictionary mapping (level, subtype) tuples to corpus names
        """
        # Group data by subtype to track when groups appear across levels
        groups_by_level: Dict[int, set] = {}
        for entry in export_data:
            level = entry["trakaido_level"]
            subtype = entry["subtype"]

            if level not in groups_by_level:
                groups_by_level[level] = set()
            groups_by_level[level].add(subtype)

        # Track which groups have been assigned to which WORDS level
        group_assignments: Dict[str, str] = {}  # group_name -> WORDS level
        corpus_assignments = {}  # (level, subtype) -> corpus name

        # Define the level ranges for each WORDS corpus
        words_ranges = {
            "WORDS1": range(1, 4),  # Levels 1-3
            "WORDS2": range(4, 7),  # Levels 4-6
            "WORDS3": range(7, 11),  # Levels 7-10
            "WORDS4": range(11, 15),  # Levels 11-14
            "WORDS5": range(15, 21),  # Levels 15-20 (overflow)
        }

        # Process each level in order
        for level in sorted(groups_by_level.keys()):
            # Determine base WORDS level for this difficulty level
            base_words_level = None
            for words_name, level_range in words_ranges.items():
                if level in level_range:
                    base_words_level = words_name
                    break

            if base_words_level is None:
                # Level is outside normal ranges, assign to Trakaido
                for subtype in groups_by_level[level]:
                    corpus_assignments[(level, subtype)] = "Trakaido"
                continue

            # Process each subtype in this level
            for subtype in groups_by_level[level]:
                if subtype in group_assignments:
                    # Group has already been assigned, kick to next WORDS level
                    current_words_level = group_assignments[subtype]
                    words_levels = list(words_ranges.keys())
                    current_index = words_levels.index(current_words_level)

                    if current_index + 1 < len(words_levels):
                        # Assign to next WORDS level
                        next_words_level = words_levels[current_index + 1]
                        group_assignments[subtype] = next_words_level
                        corpus_assignments[(level, subtype)] = next_words_level
                        logger.debug(
                            f"Group '{subtype}' at level {level} kicked from {current_words_level} to {next_words_level}"
                        )
                    else:
                        # No more WORDS levels available, assign to Trakaido
                        corpus_assignments[(level, subtype)] = "Trakaido"
                        logger.debug(
                            f"Group '{subtype}' at level {level} assigned to Trakaido (overflow)"
                        )
                else:
                    # First time seeing this group, assign to base WORDS level
                    group_assignments[subtype] = base_words_level
                    corpus_assignments[(level, subtype)] = base_words_level
                    logger.debug(
                        f"Group '{subtype}' at level {level} assigned to {base_words_level}"
                    )

        return corpus_assignments

    def _get_audio_hashes(
        self, session: Any, guid: str, language: str, grammatical_form: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """
        Get MD5 hashes for all available audio voices for a given word.

        Args:
            session: Database session
            guid: Lemma GUID (e.g., "N01_001") or word text (e.g., "gyventi")
            language: Language code (e.g., "zh")
            grammatical_form: Optional grammatical form (e.g., "1s_present"), None for base form

        Returns:
            Dict mapping voice names to MD5 hashes, e.g.:
            {"ash": "ab4d3513...", "alloy": "cd567890..."}
            Returns None if no audio available.
        """
        # Query all audio records for this word and form
        query = session.query(AudioQualityReview).filter_by(guid=guid, language_code=language)

        # Filter by grammatical form (None matches NULL in database)
        if grammatical_form is None:
            query = query.filter(AudioQualityReview.grammatical_form.is_(None))
        else:
            query = query.filter_by(grammatical_form=grammatical_form)

        audio_records = query.all()

        if not audio_records:
            return None

        # Build dict of voice -> MD5 hash
        audio_hashes = {}
        for audio in audio_records:
            # Only include audio that is in production (has s3_prod_url)
            # and has not been rejected (status != needs_replacement)
            if audio.s3_prod_url and audio.status != "needs_replacement":
                audio_hashes[audio.voice_name] = audio.manifest_md5

        return audio_hashes if audio_hashes else None

    def export_to_wireword_format(
        self,
        output_path: str,
        difficulty_level: Optional[int] = None,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
        pretty_print: bool = True,
    ) -> Tuple[bool, Optional[ExportStats]]:
        """
        Export trakaido data to new WireWord API format.

        Optimized for remote databases: uses bulk queries to minimize round trips.

        Args:
            output_path: Path to write the JSON file
            difficulty_level: Filter by specific difficulty level (optional)
            pos_type: Filter by specific POS type (optional)
            pos_subtype: Filter by specific POS subtype (optional)
            limit: Limit number of results (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)
            pretty_print: Whether to format JSON with indentation (default: True)

        Returns:
            Tuple of (success flag, export statistics)
        """
        session = self.get_session()
        try:
            # Query the data using wireword-specific method
            export_data = self.query_trakaido_data_for_wireword(
                session=session,
                difficulty_level=difficulty_level,
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                limit=limit,
                include_without_guid=include_without_guid,
                include_unverified=include_unverified,
            )

            if not export_data:
                logger.warning("No data found matching the specified criteria")
                return False, None

            # Calculate corpus assignments based on levels and groups
            corpus_assignments = self._calculate_corpus_assignments(export_data)

            # OPTIMIZATION: Bulk fetch all related data in a few queries instead of N per entry
            lemma_ids = [entry["_lemma_id"] for entry in export_data]
            guids = [entry["GUID"] for entry in export_data if entry["GUID"]]

            # Bulk fetch lemmas (we need full Lemma objects for some operations)
            lemmas_list = session.query(Lemma).filter(Lemma.id.in_(lemma_ids)).all()
            lemmas_by_id = {lemma.id: lemma for lemma in lemmas_list}
            logger.info(f"Bulk fetched {len(lemmas_by_id)} lemmas")

            # Bulk fetch all derivative forms for all lemmas
            all_derivative_forms = (
                session.query(DerivativeForm).filter(DerivativeForm.lemma_id.in_(lemma_ids)).all()
            )
            derivative_forms_by_lemma: Dict[int, List[DerivativeForm]] = {}
            for form in all_derivative_forms:
                if form.lemma_id not in derivative_forms_by_lemma:
                    derivative_forms_by_lemma[form.lemma_id] = []
                derivative_forms_by_lemma[form.lemma_id].append(form)
            logger.info(f"Bulk fetched {len(all_derivative_forms)} derivative forms")

            # Bulk fetch all audio records for all GUIDs (base forms only)
            all_audio_records = (
                session.query(AudioQualityReview)
                .filter(
                    AudioQualityReview.guid.in_(guids),
                    AudioQualityReview.language_code == self.language,
                )
                .all()
            )
            # Index by (guid, grammatical_form) for quick lookup
            audio_by_guid_form: Dict[Tuple[str, Optional[str]], Dict[str, str]] = {}
            for audio in all_audio_records:
                # Always exclude rejected audio
                if audio.status == "needs_replacement":
                    continue

                # Include if in production OR (if flag is True and in staging)
                if audio.s3_prod_url or (self.include_unreviewed_audio and audio.s3_staging_url):
                    key = (audio.guid, audio.grammatical_form)
                    if key not in audio_by_guid_form:
                        audio_by_guid_form[key] = {}
                    audio_by_guid_form[key][audio.voice_name] = audio.manifest_md5
            logger.info(f"Bulk fetched {len(all_audio_records)} audio records")

            # Bulk fetch all grammar facts for all lemmas
            all_grammar_facts = (
                session.query(GrammarFact)
                .filter(
                    GrammarFact.lemma_id.in_(lemma_ids),
                    GrammarFact.language_code == self.language,
                )
                .all()
            )
            grammar_facts_by_lemma: Dict[int, List[GrammarFact]] = {}
            for fact in all_grammar_facts:
                if fact.lemma_id not in grammar_facts_by_lemma:
                    grammar_facts_by_lemma[fact.lemma_id] = []
                grammar_facts_by_lemma[fact.lemma_id].append(fact)
            logger.info(f"Bulk fetched {len(all_grammar_facts)} grammar facts")

            # Build English translation lookup for derivative forms
            # (used for _get_english_translation_from_db)
            english_forms_by_lemma: Dict[int, Dict[str, str]] = {}
            for form in all_derivative_forms:
                if form.language_code == "en":
                    if form.lemma_id not in english_forms_by_lemma:
                        english_forms_by_lemma[form.lemma_id] = {}
                    english_forms_by_lemma[form.lemma_id][
                        form.grammatical_form
                    ] = form.derivative_form_text

            # Transform to WireWord format using pre-fetched data
            wireword_data = []
            for entry in export_data:
                lemma_id = entry["_lemma_id"]
                lemma = lemmas_by_id.get(lemma_id)
                if not lemma:
                    continue

                derivative_forms = derivative_forms_by_lemma.get(lemma_id, [])

                # Build alternatives, synonyms, and grammatical forms
                english_alternatives = []
                target_alternatives = []
                english_synonyms = []
                target_synonyms = []
                grammatical_forms = {}

                for form in derivative_forms:
                    if form.is_base_form:
                        # Skip base forms as they're already in base_target/base_english
                        continue

                    # Determine if this form is an alternative form or synonym
                    # Alternative forms include: abbreviation, expanded_form, alternate_spelling, and legacy 'alternative_form'
                    is_alternative = form.grammatical_form in [
                        "abbreviation",
                        "expanded_form",
                        "alternate_spelling",
                        "alternative_form",
                    ]
                    is_synonym = form.grammatical_form in SYNONYM_GRAMMATICAL_FORMS

                    # Handle different types of derivative forms
                    if form.language_code == "en":
                        if is_alternative:
                            english_alternatives.append(form.derivative_form_text)
                        elif is_synonym:
                            english_synonyms.append(form.derivative_form_text)
                    elif form.language_code == self.language:
                        if is_alternative:
                            target_alternatives.append(form.derivative_form_text)
                        elif is_synonym:
                            target_synonyms.append(form.derivative_form_text)
                        elif form.grammatical_form == "plural_nominative":
                            # Add plural nominative form with appropriate level (minimum level 4)
                            form_level = max(entry["trakaido_level"], 4)
                            gram_form = {
                                "level": form_level,
                                "target": form.derivative_form_text,
                                "english": f"{entry['source_word']} (plural)",  # Simple plural source form
                            }
                            gram_form.update(
                                build_target_reading_fields(
                                    self.language,
                                    form.derivative_form_text,
                                )
                            )

                            # Add audio MD5 hashes for this grammatical form (from pre-fetched data)
                            form_audio = audio_by_guid_form.get(
                                (entry["GUID"], form.grammatical_form)
                            )
                            if form_audio:
                                gram_form["audio"] = form_audio

                            grammatical_forms[form.grammatical_form] = gram_form
                        elif form.grammatical_form in ["singular_accusative", "plural_accusative"]:
                            # Add accusative forms with appropriate level (minimum level 9)
                            form_level = max(entry["trakaido_level"], 9)
                            english_suffix = (
                                " (accusative singular)"
                                if form.grammatical_form == "singular_accusative"
                                else " (accusative plural)"
                            )
                            gram_form = {
                                "level": form_level,
                                "target": form.derivative_form_text,
                                "english": f"{entry['source_word']}{english_suffix}",
                            }
                            gram_form.update(
                                build_target_reading_fields(
                                    self.language,
                                    form.derivative_form_text,
                                )
                            )

                            # Add audio MD5 hashes for this grammatical form (from pre-fetched data)
                            form_audio = audio_by_guid_form.get(
                                (entry["GUID"], form.grammatical_form)
                            )
                            if form_audio:
                                gram_form["audio"] = form_audio

                            grammatical_forms[form.grammatical_form] = gram_form
                        else:
                            # Generic handler for other grammatical forms (French verbs, Korean forms, etc.)
                            # Skip alternative_form and synonym as they're handled separately above
                            if (
                                form.grammatical_form != "alternative_form"
                                and form.grammatical_form not in SYNONYM_GRAMMATICAL_FORMS
                            ):
                                form_level = max(entry["trakaido_level"], 4)

                                gram_form = {
                                    "level": form_level,
                                    "target": form.derivative_form_text,
                                }
                                # Noun declensions are identified by their form key and the
                                # lemma's base info, so no English label is exported for them.
                                if lemma.pos_type != "noun":
                                    english_label = self._get_english_translation_from_prefetched(
                                        english_forms_by_lemma, lemma.id, form.grammatical_form
                                    )
                                    if not english_label:
                                        english_label = generate_simple_grammatical_form_label(
                                            form.grammatical_form, entry["source_word"]
                                        )
                                    gram_form["english"] = english_label
                                gram_form.update(
                                    build_target_reading_fields(
                                        self.language,
                                        form.derivative_form_text,
                                    )
                                )

                                # Add audio MD5 hashes for this grammatical form (from pre-fetched data)
                                form_audio = audio_by_guid_form.get(
                                    (entry["GUID"], form.grammatical_form)
                                )
                                if form_audio:
                                    gram_form["audio"] = form_audio

                                grammatical_forms[form.grammatical_form] = gram_form

                # Get corpus assignment for this entry
                corpus_key = (entry["trakaido_level"], entry["subtype"])
                assigned_corpus = corpus_assignments.get(corpus_key, "Trakaido")

                # Create WireWord object
                wireword: Dict[str, Any] = {
                    "guid": entry["GUID"],
                    "base_target": entry["target_language"],
                }
                # Use base_english for English source, base_source for non-English source
                if self.source_language == "en":
                    source_word = entry["source_word"]
                    # Append disambiguation to English source word if present
                    # and the word doesn't already contain parentheses
                    if lemma.disambiguation and source_word and "(" not in source_word:
                        source_word = f"{source_word} ({lemma.disambiguation})"
                    wireword["base_english"] = source_word
                else:
                    wireword["base_source"] = entry["source_word"]

                noun_source_form: Optional[str]
                if self.source_language == "en":
                    noun_source_form = wireword.get("base_english")
                else:
                    noun_source_form = wireword.get("base_source")
                if noun_source_form:
                    noun_cognate_result = detect_cognate(
                        noun_source_form,
                        entry["target_language"],
                        self.source_language,
                        self.language,
                    )
                    wireword["cognate"] = noun_cognate_result.is_cognate
                    if self.debug:
                        wireword["cognate_score"] = noun_cognate_result.score
                        wireword["cognate_reason_codes"] = list(noun_cognate_result.reasons)
                wireword.update(
                    {
                        "corpus": assigned_corpus,
                        "group": resolve_group_label(
                            entry["subtype"], self.source_language, session
                        ),
                        "level": entry["trakaido_level"],
                        "word_type": normalize_pos_type(entry["pos_type"]),
                    }
                )

                # Add audio MD5 hashes for all available voices (from pre-fetched data)
                if entry["GUID"]:
                    audio_hashes = audio_by_guid_form.get((entry["GUID"], None))
                    if audio_hashes:
                        wireword["audio"] = audio_hashes

                wireword.update(
                    build_target_reading_fields(
                        self.language,
                        entry["target_language"],
                    )
                )

                # Add optional fields
                # Use source_alternatives/source_synonyms for non-English source languages
                source_alt_key = (
                    "english_alternatives"
                    if self.source_language == "en"
                    else "source_alternatives"
                )
                source_syn_key = (
                    "english_synonyms" if self.source_language == "en" else "source_synonyms"
                )
                if english_alternatives:
                    wireword[source_alt_key] = english_alternatives
                if target_alternatives:
                    wireword["target_alternatives"] = target_alternatives
                    wireword.update(
                        build_target_reading_list_fields(
                            self.language,
                            target_alternatives,
                            "target_alternatives",
                        )
                    )
                if english_synonyms:
                    wireword[source_syn_key] = english_synonyms
                if target_synonyms:
                    wireword["target_synonyms"] = target_synonyms
                    wireword.update(
                        build_target_reading_list_fields(
                            self.language,
                            target_synonyms,
                            "target_synonyms",
                        )
                    )

                # Add grammatical forms (for both verbs and nouns with declensions)
                if grammatical_forms:
                    wireword["grammatical_forms"] = grammatical_forms

                # Add grammar facts (gender, declension, etc.) as metadata (from pre-fetched data)
                grammar_facts = grammar_facts_by_lemma.get(lemma_id, [])

                if grammar_facts:
                    grammar_metadata = {}
                    for fact in grammar_facts:
                        # Store grammar facts as key-value pairs
                        grammar_metadata[fact.fact_type] = fact.fact_value
                    wireword["grammar_metadata"] = grammar_metadata

                if lemma.frequency_rank:
                    wireword["frequency_rank"] = lemma.frequency_rank
                if lemma.notes:
                    wireword["notes"] = lemma.notes

                # Add tags based on subtype and level
                tags = [entry["subtype"], f"level_{entry['trakaido_level']}"]
                if lemma.verified:
                    tags.append("verified")
                wireword["tags"] = tags

                wireword_data.append(wireword)

            # Calculate stats from the original export_data (before transformation)
            stats = create_export_stats(export_data)

            # Write to JSON file (without recalculating stats)
            try:
                # Ensure the directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                with open(output_path, "w", encoding="utf-8") as f:
                    if pretty_print:
                        # Write with nice formatting, one entry per line
                        f.write("[\n")
                        for i, entry in enumerate(wireword_data):
                            line = json.dumps(entry, ensure_ascii=False, separators=(", ", ": "))
                            if i < len(wireword_data) - 1:
                                f.write(f"  {line},\n")
                            else:
                                f.write(f"  {line}\n")
                        f.write("]\n")
                    else:
                        # Compact format
                        json.dump(wireword_data, f, ensure_ascii=False, separators=(",", ":"))

                logger.info(f"✅ Successfully wrote {len(wireword_data)} entries to {output_path}")
                logger.info(f"Entries with GUIDs: {stats.entries_with_guids}/{stats.total_entries}")
                logger.info(f"POS distribution: {stats.pos_distribution}")
                logger.info(f"Level distribution: {stats.level_distribution}")

            except Exception as e:
                logger.error(f"❌ Failed to write JSON file: {e}")
                raise

            logger.info(f"✅ Successfully exported {len(wireword_data)} words in WireWord format")

            return True, stats

        except Exception as e:
            logger.error(f"Export to WireWord format failed: {e}")
            return False, None
        finally:
            session.close()

    def _get_english_translation_from_prefetched(
        self,
        english_forms_by_lemma: Dict[int, Dict[str, str]],
        lemma_id: int,
        grammatical_form: str,
    ) -> Optional[str]:
        """
        Look up the English translation for a grammatical form from pre-fetched data.

        Currently only supports Lithuanian verb forms. Other languages will need
        their English translations stored directly in the database.

        Args:
            english_forms_by_lemma: Pre-fetched dict mapping lemma_id -> grammatical_form -> text
            lemma_id: The lemma ID
            grammatical_form: The grammatical form (e.g., "verb/lt_1s_present")

        Returns:
            English translation string, or None if not found
        """
        # For Lithuanian forms, convert verb/lt_* to verb/en_*
        if grammatical_form.startswith("verb/lt_"):
            english_form_key = grammatical_form.replace("verb/lt_", "verb/en_")
        else:
            # Other languages not yet supported - return None
            return None

        # Look up from pre-fetched data
        lemma_forms = english_forms_by_lemma.get(lemma_id, {})
        return lemma_forms.get(english_form_key)

    def _generate_derivative_noun_phrases(
        self, lemma: Lemma, base_english: str, base_target: str, entry_level: int
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate derivative noun phrases like "where is X" and "this is my X" for nouns.
        These are constructed phrases, not stored in the database.
        Only generates for noun subtypes where these phrases make sense.

        Args:
            lemma: The Lemma object
            base_english: Base English form
            base_target: Base target language form (nominative)
            entry_level: The base level of the word

        Returns:
            Dictionary of derivative phrases to add to grammatical_forms
        """
        derivative_phrases: Dict[str, Any] = {}

        # Only generate for nouns
        if lemma.pos_type != "noun":
            return derivative_phrases

        # "where_is" derivative phrase generation is intentionally disabled.
        # It creates synthetic sentence-like content in word exports, which is
        # no longer desired in Wireword noun entries.

        # Generate "this is my X" phrase for possessable items
        # Uses nominative case (dictionary form) - "Tai mano X"
        # TODO: Disabled until we can handle plural-only nouns (pants, scissors, etc.)
        # Requires adding grammatical_number field to database to properly generate
        # "These are my pants" vs "This is my shirt"
        if False:  # Temporarily disabled
            this_is_my_subtypes = {
                "clothing_accessory",  # this is my shirt, hat
                "small_movable_object",  # this is my book, phone
                "body_part",  # this is my hand, foot
            }

            if lemma.pos_subtype in this_is_my_subtypes:
                this_is_my_level = max(entry_level, 19)
                derivative_phrases["this_is_my"] = {
                    "level": this_is_my_level,
                    "target": f"Tai mano {base_target}",
                    "english": f"This is my {base_english}",
                }

        return derivative_phrases

    def _get_level_ranges(self) -> List[Tuple[int, int]]:
        """Return level ranges for splitting word files (e.g. [(1,5), (6,10), …])."""
        max_level = self._get_max_export_level()
        ranges: List[Tuple[int, int]] = []
        for start in range(1, max_level + 1, LEVEL_RANGE_SIZE):
            end = min(start + LEVEL_RANGE_SIZE - 1, max_level)
            ranges.append((start, end))
        return ranges

    def _write_combined_wireword_file(
        self,
        filepath: str,
        wireword_data: List[Dict[str, Any]],
        pretty_print: bool = True,
    ) -> None:
        """Write wireword data (mixed nouns and verbs) to a JSON file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            if pretty_print:
                f.write("[\n")
                for i, entry in enumerate(wireword_data):
                    is_last = i == len(wireword_data) - 1
                    if entry.get("word_type") == "verb" and entry.get("grammatical_forms"):
                        f.write(format_verb_entry(entry, is_last=is_last))
                    else:
                        line = json.dumps(entry, ensure_ascii=False, separators=(", ", ": "))
                        if not is_last:
                            f.write(f"  {line},\n")
                        else:
                            f.write(f"  {line}\n")
                f.write("]\n")
            else:
                json.dump(wireword_data, f, ensure_ascii=False, separators=(",", ":"))

    def export_wireword_directory(
        self, output_dir: str, cdn_base: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Export WireWord format files to directory structure.
        Creates one file per level range (e.g. wireword_levels_1_5.json)
        containing both nouns and verbs for those levels.

        Args:
            output_dir: Base output directory (e.g., lang_lt/generated)
            cdn_base: Optional CDN base URL (e.g. "https://wireword.trakaido.com").
                When set, the manifest uses MD5-hash filenames for CDN caching.

        Returns:
            Tuple of (success flag, export results dictionary)
        """
        import tempfile

        # Create wireword subdirectory
        wireword_dir = os.path.join(output_dir, "wireword")
        os.makedirs(wireword_dir, exist_ok=True)

        results: Dict[str, Any] = {
            "files_created": [],
            "levels_exported": set(),
            "subtypes_exported": set(),
        }

        # Use unique temp files so concurrent exports don't collide
        verbs_tmp_fd, verbs_tmp_path = tempfile.mkstemp(suffix=".json", prefix="wireword_verbs_")
        os.close(verbs_tmp_fd)
        nouns_tmp_fd, nouns_tmp_path = tempfile.mkstemp(suffix=".json", prefix="wireword_nouns_")
        os.close(nouns_tmp_fd)

        try:
            # Export verbs to a temporary file.
            # (False, None) means no matching data — acceptable for some
            # languages.  A real failure raises an exception.
            logger.info("Exporting verbs to temporary file...")
            verbs_data: List[Dict[str, Any]] = []
            try:
                verbs_success, verbs_stats = self.export_verbs_to_wireword_format(
                    output_path=verbs_tmp_path,
                    include_without_guid=False,
                    include_unverified=True,
                    pretty_print=False,
                )
                if verbs_success:
                    with open(verbs_tmp_path, "r", encoding="utf-8") as f:
                        verbs_data = json.load(f)
                    if verbs_stats:
                        for level in verbs_stats.level_distribution.keys():
                            results["levels_exported"].add(int(level))
                    logger.info(f"✅ Loaded {len(verbs_data)} verb entries")
                else:
                    logger.info("No verbs found (may be expected for some languages)")
            except Exception:
                logger.error("❌ Verb export failed with an error")
                return False, results

            # Export non-verbs to a temporary file.
            logger.info("Exporting non-verbs to temporary file...")
            nouns_data: List[Dict[str, Any]] = []
            try:
                nouns_success, nouns_stats = self.export_to_wireword_format(
                    output_path=nouns_tmp_path,
                    include_without_guid=False,
                    include_unverified=True,
                    pretty_print=False,
                )
                if nouns_success:
                    with open(nouns_tmp_path, "r", encoding="utf-8") as f:
                        nouns_data = json.load(f)
                    if nouns_stats:
                        for level in nouns_stats.level_distribution.keys():
                            results["levels_exported"].add(int(level))
                        for pos_type in nouns_stats.pos_distribution.keys():
                            results["subtypes_exported"].add(pos_type)
                    logger.info(f"✅ Loaded {len(nouns_data)} non-verb entries")
                else:
                    logger.info("No non-verb entries found")
            except Exception:
                logger.error("❌ Non-verb export failed with an error")
                return False, results

        finally:
            # Clean up temporary files
            for tmp_path in (verbs_tmp_path, nouns_tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if not verbs_data and not nouns_data:
            logger.error("❌ No data to export")
            return False, results

        # Combine all words and sort by level then GUID
        all_words = nouns_data + verbs_data
        all_words.sort(key=lambda w: (w.get("level", 0), w.get("guid", "")))

        # Split into level-range files
        level_ranges = self._get_level_ranges()
        for start, end in level_ranges:
            range_words = [w for w in all_words if start <= w.get("level", 0) <= end]
            if not range_words:
                continue
            filename = f"wireword_levels_{start}_{end}.json"
            filepath = os.path.join(wireword_dir, filename)
            self._write_combined_wireword_file(filepath, range_words)
            results["files_created"].append(filepath)
            logger.info(
                f"✅ Wrote {len(range_words)} entries to {filename} " f"(levels {start}-{end})"
            )

        # Convert sets to sorted lists for JSON serialization
        results["levels_exported"] = sorted(list(results["levels_exported"]))
        results["subtypes_exported"] = sorted(list(results["subtypes_exported"]))

        # Generate manifest file
        manifest_success, manifest_path = generate_manifest(
            wireword_dir,
            self.language,
            self.simplified_chinese,
            include_unreviewed_audio=self.include_unreviewed_audio,
            source_language=self.source_language,
            cdn_base=cdn_base,
        )
        if manifest_success:
            results["files_created"].append(manifest_path)
            results["manifest_path"] = manifest_path

        logger.info(
            f"✅ WireWord directory export completed: "
            f"{len(results['files_created'])} files created"
        )
        return True, results

    def export_verbs_to_wireword_format(
        self,
        output_path: str,
        difficulty_level: Optional[int] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
        pretty_print: bool = True,
    ) -> Tuple[bool, Optional[ExportStats]]:
        """
        Export verbs from database to WireWord API format.

        Uses language-specific difficulty level overrides when available.
        Optimized for remote databases: uses bulk queries to minimize round trips.

        Args:
            output_path: Path to write the JSON file
            difficulty_level: Filter by specific difficulty level (optional)
            pos_subtype: Filter by specific verb subtype (optional)
            limit: Limit number of results (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)
            pretty_print: Whether to format JSON with indentation (default: True)

        Returns:
            Tuple of (success flag, export statistics)
        """
        from sqlalchemy import func

        from storage.models.schema import LemmaDifficultyOverride

        session = self.get_session()
        try:
            # Build the query for verbs
            query = session.query(Lemma).filter(Lemma.pos_type == "verb")

            # Apply filters
            if not include_without_guid:
                query = query.filter(Lemma.guid != None)

            if not include_unverified:
                query = query.filter(Lemma.verified == True)

            # Handle difficulty level filtering with language-specific overrides
            if difficulty_level is not None:
                # Left join with overrides to get language-specific levels
                query = query.outerjoin(
                    LemmaDifficultyOverride,
                    (LemmaDifficultyOverride.lemma_id == Lemma.id)
                    & (LemmaDifficultyOverride.language_code == self.language),
                )
                # Use override if exists, otherwise use default
                effective_level = func.coalesce(
                    LemmaDifficultyOverride.difficulty_level, Lemma.difficulty_level
                )
                query = query.filter(effective_level == difficulty_level)
                logger.info(
                    f"Filtering by effective difficulty level: {difficulty_level} for language: {self.language}"
                )

            if pos_subtype:
                query = query.filter(Lemma.pos_subtype == pos_subtype)
                logger.info(f"Filtering by verb subtype: {pos_subtype}")

            # Order by GUID for consistent output
            query = query.order_by(Lemma.guid.asc().nullslast())

            if limit:
                query = query.limit(limit)
                logger.info(f"Limiting results to: {limit}")

            lemmas = query.all()
            logger.info(f"Found {len(lemmas)} verbs matching criteria")

            if not lemmas:
                logger.warning("No verbs found matching the specified criteria")
                return False, None

            # OPTIMIZATION: Bulk fetch all related data in a few queries instead of N per lemma
            lemma_ids = [lemma.id for lemma in lemmas]
            guids = [lemma.guid for lemma in lemmas if lemma.guid]

            # Bulk fetch translations and difficulty levels
            translations_by_id = bulk_get_translations(session, lemmas, self.language)
            difficulty_levels_by_id = bulk_get_effective_difficulty_levels(
                session, lemmas, self.language
            )
            logger.info("Bulk fetched translations and difficulty levels")

            # For non-English source languages, bulk fetch source translations
            verb_source_translations_by_id: Dict[int, Optional[str]] = {}
            if self.source_language != "en":
                verb_source_translations_by_id = bulk_get_translations(
                    session, lemmas, self.source_language
                )
                logger.info(
                    f"Fetched {sum(1 for v in verb_source_translations_by_id.values() if v)} "
                    f"{self.source_language_name} source translations for verbs"
                )

            # For Traditional Chinese export, also fetch zh-tw translations
            zh_tw_translations_by_id: Dict[int, Optional[str]] = {}
            if self.language == "zh" and not self.simplified_chinese:
                zh_tw_translations_by_id = bulk_get_translations(session, lemmas, "zh-tw")
                logger.info(
                    f"Fetched {sum(1 for v in zh_tw_translations_by_id.values() if v)} zh-tw translations for verbs"
                )

            # Bulk fetch all derivative forms for all verbs
            all_derivative_forms = (
                session.query(DerivativeForm).filter(DerivativeForm.lemma_id.in_(lemma_ids)).all()
            )
            derivative_forms_by_lemma: Dict[int, List[DerivativeForm]] = {}
            for form in all_derivative_forms:
                if form.lemma_id not in derivative_forms_by_lemma:
                    derivative_forms_by_lemma[form.lemma_id] = []
                derivative_forms_by_lemma[form.lemma_id].append(form)
            logger.info(f"Bulk fetched {len(all_derivative_forms)} derivative forms")

            # Build English translation lookup for derivative forms
            english_forms_by_lemma: Dict[int, Dict[str, str]] = {}
            source_forms_by_lemma: Dict[int, Dict[str, str]] = {}
            for form in all_derivative_forms:
                if form.language_code == "en":
                    if form.lemma_id not in english_forms_by_lemma:
                        english_forms_by_lemma[form.lemma_id] = {}
                    english_forms_by_lemma[form.lemma_id][
                        form.grammatical_form
                    ] = form.derivative_form_text
                if form.language_code == self.source_language:
                    if form.lemma_id not in source_forms_by_lemma:
                        source_forms_by_lemma[form.lemma_id] = {}
                    source_forms_by_lemma[form.lemma_id][
                        form.grammatical_form
                    ] = form.derivative_form_text

            # Bulk fetch all audio records for all GUIDs
            all_audio_records = (
                session.query(AudioQualityReview)
                .filter(
                    AudioQualityReview.guid.in_(guids),
                    AudioQualityReview.language_code == self.language,
                )
                .all()
            )
            # Index by (guid, grammatical_form) for quick lookup
            audio_by_guid_form: Dict[Tuple[str, Optional[str]], Dict[str, str]] = {}
            for audio in all_audio_records:
                # Always exclude rejected audio
                if audio.status == "needs_replacement":
                    continue

                # Include if in production OR (if flag is True and in staging)
                if audio.s3_prod_url or (self.include_unreviewed_audio and audio.s3_staging_url):
                    key = (audio.guid, audio.grammatical_form)
                    if key not in audio_by_guid_form:
                        audio_by_guid_form[key] = {}
                    audio_by_guid_form[key][audio.voice_name] = audio.manifest_md5
            logger.info(f"Bulk fetched {len(all_audio_records)} audio records")

            # Transform to WireWord format using pre-fetched data
            wireword_data = []
            max_export_level = self._get_max_export_level()
            logger.info(
                "Applying max export level %s for language %s",
                max_export_level,
                self.language,
            )
            missing_english_forms: List[Tuple[int, str, str]] = []
            for lemma in lemmas:
                # Get effective difficulty level from pre-fetched data
                effective_lemma_level = difficulty_levels_by_id.get(lemma.id)

                # Skip words with no difficulty level assigned
                if effective_lemma_level is None:
                    continue

                # Skip words at level -1 (excluded from all wireword exports)
                if effective_lemma_level == -1:
                    continue

                # Skip words above the language-specific export cap
                if effective_lemma_level > max_export_level:
                    continue

                # Get derivative forms from pre-fetched data
                derivative_forms = derivative_forms_by_lemma.get(lemma.id, [])

                # Get base source and target language forms from pre-fetched data
                if self.source_language == "en":
                    base_source: Optional[str] = lemma.lemma_text
                else:
                    base_source = verb_source_translations_by_id.get(lemma.id)
                base_target = translations_by_id.get(lemma.id)

                # For Chinese, handle simplified vs traditional
                if self.language == "zh":
                    if self.simplified_chinese:
                        # Convert to Simplified Chinese
                        if base_target:
                            base_target = to_simplified(base_target)
                    else:
                        # Traditional Chinese: prefer zh-tw, fall back to converting zh
                        zh_tw_trans = zh_tw_translations_by_id.get(lemma.id)
                        if zh_tw_trans and zh_tw_trans.strip():
                            base_target = zh_tw_trans
                        elif base_target:
                            # Convert zh to traditional as fallback
                            base_target = to_traditional(base_target)

                # Skip verbs without target language translation
                if not base_target or not base_target.strip():
                    continue

                # Skip verbs without source language translation (for non-English source)
                if self.source_language != "en" and (not base_source or not base_source.strip()):
                    continue

                # Build grammatical forms (conjugations)
                grammatical_forms = {}
                conjugation_mode_tables: Dict[str, Dict[str, Dict[str, str]]] = {}
                target_alternatives: List[str] = []
                english_synonyms = []
                target_synonyms = []

                for form in derivative_forms:
                    if form.is_base_form:
                        # Skip base forms as they're already in base_target/base_english
                        continue

                    # Handle different types of derivative forms
                    if form.language_code == "en":
                        if form.grammatical_form in SYNONYM_GRAMMATICAL_FORMS:
                            english_synonyms.append(form.derivative_form_text)
                    elif form.language_code == self.language:
                        if form.grammatical_form in SYNONYM_GRAMMATICAL_FORMS:
                            target_synonyms.append(form.derivative_form_text)
                        elif form.grammatical_form != "infinitive":
                            # This is a conjugated form
                            form_level = max(effective_lemma_level, 1)

                            # For French, only export present, passé composé (past), and future
                            if self.language == "fr":
                                # Extract tense from grammatical_form (format: "verb/fr_1s_present", "verb/fr_1p_pc", etc.)
                                if "_" in form.grammatical_form:
                                    tense_suffix = form.grammatical_form.split("_")[-1]
                                    # Only allow present, pc (passé composé), and future
                                    if tense_suffix not in ["present", "pc", "future"]:
                                        continue  # Skip imperfect, conditional, subjunctive

                                    # Apply tense-specific minimum levels
                                    if tense_suffix == "pc":
                                        # Passé composé (past) minimum level is 7
                                        form_level = max(form_level, 7)
                                    elif tense_suffix == "future":
                                        # Future tense minimum level is 12
                                        form_level = max(form_level, 12)

                            # Apply tense-specific minimum levels for Lithuanian
                            elif self.language == "lt":
                                # Extract tense from grammatical_form (format: "1s_past", "3p_future", etc.)
                                if "_" in form.grammatical_form:
                                    tense_suffix = form.grammatical_form.split("_")[-1]
                                    if tense_suffix == "past":
                                        # Past tense minimum level is 7
                                        form_level = max(form_level, 7)
                                    elif tense_suffix == "future":
                                        # Future tense minimum level is 12
                                        form_level = max(form_level, 12)

                            source_label: str
                            if self.source_language == "en":
                                # Try to look up English translation from pre-fetched data
                                source_label = (
                                    self._get_english_translation_from_prefetched(
                                        english_forms_by_lemma,
                                        lemma.id,
                                        form.grammatical_form,
                                    )
                                    or ""
                                )
                                # If not found in database, use simple generated fallback label.
                                if not source_label:
                                    missing_english_forms.append(
                                        (lemma.id, lemma.lemma_text, form.grammatical_form)
                                    )
                                    source_label = generate_simple_grammatical_form_label(
                                        form.grammatical_form, base_source or ""
                                    )
                            else:
                                source_label = (
                                    source_forms_by_lemma.get(lemma.id, {}).get(
                                        form.grammatical_form
                                    )
                                    or ""
                                )
                                if not source_label:
                                    source_label = generate_simple_grammatical_form_label(
                                        form.grammatical_form, base_source or ""
                                    )

                            gram_form = {
                                "level": form_level,
                                "target": form.derivative_form_text,
                                "source": source_label,
                            }
                            gram_form.update(
                                build_target_reading_fields(
                                    self.language,
                                    form.derivative_form_text,
                                )
                            )

                            # Convert grammatical form key to WireWord format
                            # e.g., "verb/lt_3s_present" -> "3s_present"
                            wireword_key = convert_to_wireword_grammatical_form_key(
                                form.grammatical_form
                            )

                            # Add audio MD5 hashes for this grammatical form (from pre-fetched data)
                            form_audio = audio_by_guid_form.get((lemma.guid, wireword_key))
                            if form_audio:
                                gram_form["audio"] = form_audio

                            grammatical_forms[wireword_key] = gram_form

                            slot = extract_conjugation_slot(wireword_key)
                            tense = extract_conjugation_tense(wireword_key)
                            if slot and tense:
                                tense_table = conjugation_mode_tables.setdefault(tense, {})
                                tense_table[slot] = {
                                    "source": source_label.strip(),
                                    "target": form.derivative_form_text.strip(),
                                }

                # Create WireWord object
                wireword: Dict[str, Any] = {
                    "guid": lemma.guid,
                    "base_target": base_target,
                }
                # Use base_english for English source, base_source for non-English source
                if self.source_language == "en":
                    verb_source = base_source
                    # Append disambiguation to English source word if present
                    # and the word doesn't already contain parentheses
                    if lemma.disambiguation and verb_source and "(" not in verb_source:
                        verb_source = f"{verb_source} ({lemma.disambiguation})"
                    wireword["base_english"] = verb_source
                else:
                    wireword["base_source"] = base_source

                verb_source_form: Optional[str]
                if self.source_language == "en":
                    verb_source_form = wireword.get("base_english")
                else:
                    verb_source_form = wireword.get("base_source")
                if verb_source_form:
                    verb_cognate_result = detect_cognate(
                        verb_source_form,
                        base_target,
                        self.source_language,
                        self.language,
                    )
                    wireword["cognate"] = verb_cognate_result.is_cognate
                    if self.debug:
                        wireword["cognate_score"] = verb_cognate_result.score
                        wireword["cognate_reason_codes"] = list(verb_cognate_result.reasons)
                wireword.update(
                    {
                        "corpus": "VERBS",
                        "group": resolve_group_label(
                            lemma.pos_subtype or "action", self.source_language, session
                        ),
                        "level": effective_lemma_level,
                        "word_type": "verb",
                    }
                )

                # Add audio MD5 hashes for all available voices (from pre-fetched data)
                if lemma.guid:
                    audio_hashes = audio_by_guid_form.get((lemma.guid, None))
                    if audio_hashes:
                        wireword["audio"] = audio_hashes

                wireword.update(build_target_reading_fields(self.language, base_target))

                # Add optional fields
                verb_source_syn_key = (
                    "english_synonyms" if self.source_language == "en" else "source_synonyms"
                )
                if english_synonyms:
                    wireword[verb_source_syn_key] = english_synonyms
                if target_synonyms:
                    wireword["target_synonyms"] = target_synonyms
                    wireword.update(
                        build_target_reading_list_fields(
                            self.language,
                            target_synonyms,
                            "target_synonyms",
                        )
                    )

                # Add grammatical forms (conjugations)
                if grammatical_forms:
                    wireword["grammatical_forms"] = grammatical_forms

                # Add conjugation tables for Trakaido Conjugations mode.
                # Preserve only explicit tense+slot pairs present in grammatical_forms.
                # Tense keys keep compatible aliases (pres/past/fut) and allow
                # language-specific variants (e.g., imparfait, future_i).
                if conjugation_mode_tables:
                    wireword["conjugation_mode"] = {
                        "format": "raw_forms_v2",
                        "tables": conjugation_mode_tables,
                    }

                if lemma.notes:
                    wireword["notes"] = lemma.notes

                # Add tags
                tags = [lemma.pos_subtype or "action", f"level_{effective_lemma_level}"]
                if lemma.verified:
                    tags.append("verified")
                wireword["tags"] = tags

                wireword_data.append(wireword)

            if missing_english_forms:
                logger.warning(self._format_missing_verb_translation_warning(missing_english_forms))

            # Calculate basic stats
            # ExportStats is already imported at module level

            # Calculate level distribution
            level_dist: Dict[str, int] = {}
            for w in wireword_data:
                level = str(w.get("level", 0))
                level_dist[level] = level_dist.get(level, 0) + 1

            stats = ExportStats(
                total_entries=len(wireword_data),
                entries_with_guids=sum(1 for w in wireword_data if w.get("guid")),
                pos_distribution={"verb": len(wireword_data)},
                level_distribution=level_dist,
            )

            # Write to JSON file
            try:
                # Ensure the directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                with open(output_path, "w", encoding="utf-8") as f:
                    if pretty_print:
                        # Write with custom formatting for verbs
                        # Each verb entry gets more vertical space, but grammatical forms are condensed to one line each
                        f.write("[\n")
                        for i, entry in enumerate(wireword_data):
                            f.write(format_verb_entry(entry, is_last=(i == len(wireword_data) - 1)))
                        f.write("]\n")
                    else:
                        # Compact format
                        json.dump(wireword_data, f, ensure_ascii=False, separators=(",", ":"))

                logger.info(
                    f"✅ Successfully wrote {len(wireword_data)} verb entries to {output_path}"
                )
                logger.info(f"Entries with GUIDs: {stats.entries_with_guids}/{stats.total_entries}")

            except Exception as e:
                logger.error(f"❌ Failed to write JSON file: {e}")
                raise

            logger.info(f"✅ Successfully exported {len(wireword_data)} verbs in WireWord format")

            return True, stats

        except Exception as e:
            logger.error(f"Export verbs to WireWord format failed: {e}")
            return False, None
        finally:
            session.close()


# Convenience functions for backward compatibility
