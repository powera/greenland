#!/usr/bin/env python3
"""
WireWord format exporter for trakaido data.

This module handles exporting trakaido data to the WireWord API format,
including nouns, verbs, and complete directory exports.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import sys

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import WordToken, Lemma, DerivativeForm
from wordfreq.storage.models.grammar_fact import GrammarFact
from wordfreq.storage.translation_helpers import get_translation, LANGUAGE_FIELDS
from wordfreq.tools.chinese_converter import to_simplified

# Import pypinyin for Chinese pinyin generation
try:
    from pypinyin import lazy_pinyin, Style
    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False

from .data_models import ExportStats, create_export_stats
from .text_rendering import format_subtype_display_name

# Configure logging
logger = logging.getLogger(__name__)


class WirewordExporter:
    """Exporter for WireWord API format."""

    def __init__(self, db_path: str = None, debug: bool = False, language: str = 'lt', simplified_chinese: bool = True):
        """
        Initialize the WirewordExporter.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            language: Target language code ('lt' for Lithuanian, 'zh' for Chinese, etc.)
            simplified_chinese: If True and language is 'zh', convert to Simplified Chinese (default: True)
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.language = language
        self.simplified_chinese = simplified_chinese

        if language not in LANGUAGE_FIELDS:
            raise ValueError(f"Unsupported language: {language}. Supported: {', '.join(LANGUAGE_FIELDS.keys())}")

        # Get language name from translation_helpers
        from wordfreq.storage.translation_helpers import get_language_name
        self.language_name = get_language_name(language)

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def get_english_word_from_lemma(self, session, lemma: Lemma) -> Optional[str]:
        """
        Get the primary English word for a lemma.

        Args:
            session: Database session
            lemma: Lemma object

        Returns:
            English word string or None if not found
        """
        return lemma.lemma_text


    def query_trakaido_data_for_wireword(
        self,
        session,
        difficulty_level: Optional[int] = None,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Query trakaido data from the database with flexible filtering.
        Filters by translation availability using translation_helpers.

        Uses language-specific difficulty level overrides when available.

        Note: This queries all lemmas then filters in Python, which is less efficient
        than SQL filtering but works correctly with the LemmaTranslation table.
        """
        from sqlalchemy import func
        from wordfreq.storage.models.schema import LemmaDifficultyOverride
        from wordfreq.storage.crud.difficulty_override import get_effective_difficulty_level

        logger.info(f"Querying database for trakaido data (language: {self.language_name})...")

        # Build the query without language filtering (we'll filter in Python)
        query = session.query(Lemma)\
            .filter(Lemma.pos_type != 'verb')  # Exclude verbs - they go in separate file

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
                (LemmaDifficultyOverride.lemma_id == Lemma.id) &
                (LemmaDifficultyOverride.language_code == self.language)
            )
            # Use override if exists, otherwise use default
            effective_level = func.coalesce(
                LemmaDifficultyOverride.difficulty_level,
                Lemma.difficulty_level
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
        
        # Filter by translation availability using translation_helpers
        lemmas = []
        for lemma in all_lemmas:
            translation = get_translation(session, lemma, self.language)
            if translation and translation.strip():
                lemmas.append(lemma)
                if limit and len(lemmas) >= limit:
                    break
        
        logger.info(f"Found {len(lemmas)} lemmas with {self.language_name} translations")
        
        # Build export data
        export_data = []
        for lemma in lemmas:
            target_translation = get_translation(session, lemma, self.language)

            # For Chinese, optionally convert to simplified
            if self.language == 'zh' and self.simplified_chinese and target_translation:
                target_translation = to_simplified(target_translation)

            # Get effective difficulty level for this language
            effective_level = get_effective_difficulty_level(session, lemma, self.language)
            if effective_level is None:
                effective_level = 0

            # Skip words at level -1 (excluded from all wireword exports)
            if effective_level == -1:
                continue

            entry = {
                'GUID': lemma.guid,
                'english': self.get_english_word_from_lemma(session, lemma),
                'target_language': target_translation,
                'definition': lemma.definition_text,
                'pos_type': lemma.pos_type,
                'pos_subtype': lemma.pos_subtype or 'general',
                'subtype': lemma.pos_subtype or 'general',
                'trakaido_level': effective_level,
                'verified': lemma.verified,
                'confidence': lemma.confidence
            }
            export_data.append(entry)
        
        return export_data

    def _calculate_corpus_assignments(self, export_data: List[Dict[str, Any]]) -> Dict[Tuple[int, str], str]:
        """
        Calculate corpus assignments based on levels and group overflow logic.
        
        Args:
            export_data: List of export entries
            
        Returns:
            Dictionary mapping (level, subtype) tuples to corpus names
        """
        # Group data by subtype to track when groups appear across levels
        groups_by_level = {}
        for entry in export_data:
            level = entry['trakaido_level']
            subtype = entry['subtype']
            
            if level not in groups_by_level:
                groups_by_level[level] = set()
            groups_by_level[level].add(subtype)
        
        # Track which groups have been assigned to which WORDS level
        group_assignments = {}  # group_name -> WORDS level
        corpus_assignments = {}  # (level, subtype) -> corpus name
        
        # Define the level ranges for each WORDS corpus
        words_ranges = {
            'WORDS1': range(1, 4),   # Levels 1-3
            'WORDS2': range(4, 7),   # Levels 4-6
            'WORDS3': range(7, 11),  # Levels 7-10
            'WORDS4': range(11, 15), # Levels 11-14
            'WORDS5': range(15, 21)  # Levels 15-20 (overflow)
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
                    corpus_assignments[(level, subtype)] = 'Trakaido'
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
                        logger.debug(f"Group '{subtype}' at level {level} kicked from {current_words_level} to {next_words_level}")
                    else:
                        # No more WORDS levels available, assign to Trakaido
                        corpus_assignments[(level, subtype)] = 'Trakaido'
                        logger.debug(f"Group '{subtype}' at level {level} assigned to Trakaido (overflow)")
                else:
                    # First time seeing this group, assign to base WORDS level
                    group_assignments[subtype] = base_words_level
                    corpus_assignments[(level, subtype)] = base_words_level
                    logger.debug(f"Group '{subtype}' at level {level} assigned to {base_words_level}")
        
        return corpus_assignments
    
    def _normalize_pos_type(self, pos_type: str) -> str:
        """
        Normalize POS type to match WireWord PartOfSpeech enum.

        Args:
            pos_type: Original POS type

        Returns:
            Normalized POS type
        """
        pos_mappings = {
            'noun': 'noun',
            'verb': 'verb',
            'adjective': 'adjective',
            'adverb': 'adverb',
            'pronoun': 'pronoun',
            'preposition': 'preposition',
            'conjunction': 'conjunction',
            'interjection': 'interjection',
            'numeral': 'numeral',
            'particle': 'particle'
        }

        return pos_mappings.get(pos_type.lower(), pos_type)

    def _generate_pinyin(self, chinese_text: str) -> Optional[str]:
        """
        Generate pinyin for Chinese text.

        Args:
            chinese_text: Chinese text to convert to pinyin

        Returns:
            Pinyin string with tone marks, or None if pypinyin is not available
        """
        if not PYPINYIN_AVAILABLE or not chinese_text:
            return None

        try:
            # Use Style.TONE to get pinyin with tone marks (e.g., "nǐ hǎo")
            pinyin_list = lazy_pinyin(chinese_text, style=Style.TONE)
            return ' '.join(pinyin_list)
        except Exception as e:
            logger.warning(f"Failed to generate pinyin for '{chinese_text}': {e}")
            return None
    def export_to_wireword_format(
        self,
        output_path: str,
        difficulty_level: Optional[int] = None,
        pos_type: Optional[str] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
        pretty_print: bool = True
    ) -> Tuple[bool, Optional[ExportStats]]:
        """
        Export trakaido data to new WireWord API format.
        
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
                include_unverified=include_unverified
            )
            
            if not export_data:
                logger.warning("No data found matching the specified criteria")
                return False, None
            
            # Calculate corpus assignments based on levels and groups
            corpus_assignments = self._calculate_corpus_assignments(export_data)
            
            # Transform to WireWord format
            wireword_data = []
            for entry in export_data:
                # Get all derivative forms for this lemma
                lemma = session.query(Lemma).filter(Lemma.guid == entry['GUID']).first()
                if not lemma:
                    continue
                
                derivative_forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id
                ).all()
                
                # Build alternatives, synonyms, and grammatical forms
                english_alternatives = []
                target_alternatives = []
                target_alternatives_pinyin = []  # For Chinese pinyin
                english_synonyms = []
                target_synonyms = []
                target_synonyms_pinyin = []  # For Chinese pinyin
                grammatical_forms = {}

                for form in derivative_forms:
                    if form.is_base_form:
                        # Skip base forms as they're already in base_target/base_english
                        continue

                    # Determine if this form is an alternative form or synonym
                    # Alternative forms include: abbreviation, expanded_form, alternate_spelling, and legacy 'alternative_form'
                    is_alternative = form.grammatical_form in ['abbreviation', 'expanded_form', 'alternate_spelling', 'alternative_form']
                    is_synonym = form.grammatical_form == 'synonym'

                    # Handle different types of derivative forms
                    if form.language_code == 'en':
                        if is_alternative:
                            english_alternatives.append(form.derivative_form_text)
                        elif is_synonym:
                            english_synonyms.append(form.derivative_form_text)
                    elif form.language_code == self.language:
                        if is_alternative:
                            target_alternatives.append(form.derivative_form_text)
                            # Generate pinyin for Chinese alternatives (keep arrays parallel)
                            if self.language == 'zh':
                                pinyin = self._generate_pinyin(form.derivative_form_text)
                                target_alternatives_pinyin.append(pinyin if pinyin else '')
                        elif is_synonym:
                            target_synonyms.append(form.derivative_form_text)
                            # Generate pinyin for Chinese synonyms (keep arrays parallel)
                            if self.language == 'zh':
                                pinyin = self._generate_pinyin(form.derivative_form_text)
                                target_synonyms_pinyin.append(pinyin if pinyin else '')
                        elif form.grammatical_form == 'plural_nominative':
                            # Skip derivative forms for Lithuanian nouns (they're handled by special cases like "where is X")
                            if self.language == 'lt' and lemma.pos_type == 'noun':
                                continue
                            # Add plural nominative form with appropriate level (minimum level 4)
                            form_level = max(entry['trakaido_level'], 4)
                            gram_form = {
                                "level": form_level,
                                "target": form.derivative_form_text,
                                "english": f"{entry['english']} (plural)"  # Simple plural English form
                            }
                            # Add pinyin for Chinese grammatical forms
                            if self.language == 'zh':
                                pinyin = self._generate_pinyin(form.derivative_form_text)
                                if pinyin:
                                    gram_form['target_pinyin'] = pinyin
                            grammatical_forms[form.grammatical_form] = gram_form
                        elif form.grammatical_form in ['singular_accusative', 'plural_accusative']:
                            # Skip derivative forms for Lithuanian nouns (they're handled by special cases like "where is X")
                            if self.language == 'lt' and lemma.pos_type == 'noun':
                                continue
                            # Add accusative forms with appropriate level (minimum level 9)
                            form_level = max(entry['trakaido_level'], 9)
                            english_suffix = " (accusative singular)" if form.grammatical_form == 'singular_accusative' else " (accusative plural)"
                            gram_form = {
                                "level": form_level,
                                "target": form.derivative_form_text,
                                "english": f"{entry['english']}{english_suffix}"
                            }
                            # Add pinyin for Chinese grammatical forms
                            if self.language == 'zh':
                                pinyin = self._generate_pinyin(form.derivative_form_text)
                                if pinyin:
                                    gram_form['target_pinyin'] = pinyin
                            grammatical_forms[form.grammatical_form] = gram_form
                        else:
                            # Skip derivative forms for Lithuanian nouns (they're handled by special cases like "where is X")
                            if self.language == 'lt' and lemma.pos_type == 'noun':
                                continue
                            # Generic handler for other grammatical forms (French verbs, Korean forms, etc.)
                            # Skip alternative_form and synonym as they're handled separately above
                            if form.grammatical_form not in ['alternative_form', 'synonym']:
                                form_level = max(entry['trakaido_level'], 4)

                                # Try to look up English translation from database first
                                english_label = self._get_english_translation_from_db(
                                    session,
                                    lemma.id,
                                    form.grammatical_form
                                )

                                # If not found in database, generate it
                                if not english_label:
                                    english_label = self._generate_grammatical_form_label(
                                        form.grammatical_form,
                                        entry['english'],
                                        lemma.pos_type
                                    )

                                gram_form = {
                                    "level": form_level,
                                    "target": form.derivative_form_text,
                                    "english": english_label
                                }
                                # Add pinyin for Chinese grammatical forms
                                if self.language == 'zh':
                                    pinyin = self._generate_pinyin(form.derivative_form_text)
                                    if pinyin:
                                        gram_form['target_pinyin'] = pinyin
                                grammatical_forms[form.grammatical_form] = gram_form

                # Generate derivative noun phrases (e.g., "where is X") for appropriate nouns
                derivative_phrases = self._generate_derivative_noun_phrases(
                    lemma,
                    entry['english'],
                    entry['target_language'],
                    entry['trakaido_level']
                )
                grammatical_forms.update(derivative_phrases)

                # Get corpus assignment for this entry
                corpus_key = (entry['trakaido_level'], entry['subtype'])
                assigned_corpus = corpus_assignments.get(corpus_key, 'Trakaido')

                # Create WireWord object
                wireword = {
                    'guid': entry['GUID'],
                    'base_target': entry['target_language'],
                    'base_english': entry['english'],
                    'corpus': assigned_corpus,
                    'group': format_subtype_display_name(entry['subtype']),
                    'level': entry['trakaido_level'],
                    'word_type': self._normalize_pos_type(entry['pos_type'])
                }

                # Add filename field for Chinese to use GUID in URL instead of Chinese characters
                if self.language == 'zh' and entry['GUID']:
                    wireword['filename'] = entry['GUID']

                # Add pinyin for Chinese language exports
                if self.language == 'zh' and entry['target_language']:
                    pinyin = self._generate_pinyin(entry['target_language'])
                    if pinyin:
                        wireword['target_pinyin'] = pinyin

                # Add optional fields
                if english_alternatives:
                    wireword['english_alternatives'] = english_alternatives
                if target_alternatives:
                    wireword['target_alternatives'] = target_alternatives
                    # Add pinyin for Chinese alternatives
                    if self.language == 'zh' and target_alternatives_pinyin:
                        wireword['target_alternatives_pinyin'] = target_alternatives_pinyin
                if english_synonyms:
                    wireword['english_synonyms'] = english_synonyms
                if target_synonyms:
                    wireword['target_synonyms'] = target_synonyms
                    # Add pinyin for Chinese synonyms
                    if self.language == 'zh' and target_synonyms_pinyin:
                        wireword['target_synonyms_pinyin'] = target_synonyms_pinyin
                
                # Add grammatical forms (for both verbs and nouns with declensions)
                if grammatical_forms:
                    wireword['grammatical_forms'] = grammatical_forms

                # Add grammar facts (gender, declension, etc.) as metadata
                grammar_facts = session.query(GrammarFact).filter(
                    GrammarFact.lemma_id == lemma.id,
                    GrammarFact.language_code == self.language
                ).all()

                if grammar_facts:
                    grammar_metadata = {}
                    for fact in grammar_facts:
                        # Store grammar facts as key-value pairs
                        grammar_metadata[fact.fact_type] = fact.fact_value
                    wireword['grammar_metadata'] = grammar_metadata

                if lemma.frequency_rank:
                    wireword['frequency_rank'] = lemma.frequency_rank
                if lemma.notes:
                    wireword['notes'] = lemma.notes
                
                # Add tags based on subtype and level
                tags = [entry['subtype'], f"level_{entry['trakaido_level']}"]
                if lemma.verified:
                    tags.append('verified')
                wireword['tags'] = tags
                
                wireword_data.append(wireword)

            # Calculate stats from the original export_data (before transformation)
            stats = create_export_stats(export_data)

            # Write to JSON file (without recalculating stats)
            try:
                # Ensure the directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                with open(output_path, 'w', encoding='utf-8') as f:
                    if pretty_print:
                        # Write with nice formatting, one entry per line
                        f.write('[\n')
                        for i, entry in enumerate(wireword_data):
                            line = json.dumps(entry, ensure_ascii=False, separators=(', ', ': '))
                            if i < len(wireword_data) - 1:
                                f.write(f'  {line},\n')
                            else:
                                f.write(f'  {line}\n')
                        f.write(']\n')
                    else:
                        # Compact format
                        json.dump(wireword_data, f, ensure_ascii=False, separators=(',', ':'))

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

    def _calculate_corpus_assignments(self, export_data: List[Dict[str, Any]]) -> Dict[Tuple[int, str], str]:
        """
        Calculate corpus assignments based on levels and group overflow logic.
        
        Args:
            export_data: List of export entries
            
        Returns:
            Dictionary mapping (level, subtype) tuples to corpus names
        """
        # Group data by subtype to track when groups appear across levels
        groups_by_level = {}
        for entry in export_data:
            level = entry['trakaido_level']
            subtype = entry['subtype']
            
            if level not in groups_by_level:
                groups_by_level[level] = set()
            groups_by_level[level].add(subtype)
        
        # Track which groups have been assigned to which WORDS level
        group_assignments = {}  # group_name -> WORDS level
        corpus_assignments = {}  # (level, subtype) -> corpus name
        
        # Define the level ranges for each WORDS corpus
        words_ranges = {
            'WORDS1': range(1, 4),   # Levels 1-3
            'WORDS2': range(4, 7),   # Levels 4-6
            'WORDS3': range(7, 11),  # Levels 7-10
            'WORDS4': range(11, 15), # Levels 11-14
            'WORDS5': range(15, 21)  # Levels 15-20 (overflow)
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
                    corpus_assignments[(level, subtype)] = 'Trakaido'
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
                        logger.debug(f"Group '{subtype}' at level {level} kicked from {current_words_level} to {next_words_level}")
                    else:
                        # No more WORDS levels available, assign to Trakaido
                        corpus_assignments[(level, subtype)] = 'Trakaido'
                        logger.debug(f"Group '{subtype}' at level {level} assigned to Trakaido (overflow)")
                else:
                    # First time seeing this group, assign to base WORDS level
                    group_assignments[subtype] = base_words_level
                    corpus_assignments[(level, subtype)] = base_words_level
                    logger.debug(f"Group '{subtype}' at level {level} assigned to {base_words_level}")
        
        return corpus_assignments
    
    def _normalize_pos_type(self, pos_type: str) -> str:
        """
        Normalize POS type to match WireWord PartOfSpeech enum.

        Args:
            pos_type: Original POS type

        Returns:
            Normalized POS type
        """
        pos_mappings = {
            'noun': 'noun',
            'verb': 'verb',
            'adjective': 'adjective',
            'adverb': 'adverb',
            'pronoun': 'pronoun',
            'preposition': 'preposition',
            'conjunction': 'conjunction',
            'interjection': 'interjection',
            'numeral': 'numeral',
            'particle': 'particle'
        }

        return pos_mappings.get(pos_type.lower(), pos_type)

    def _convert_to_legacy_grammatical_form_key(self, grammatical_form: str) -> str:
        """
        Convert new grammatical form key format to legacy format.

        Converts from database format like "verb/lt_3s_m_pres" or "verb/fr_1s_pres"
        to legacy wireword format like "3s-m_pres" or "1s_pres".

        The key transformations:
        - Remove "verb/{lang}_" prefix
        - Replace underscores between person/number components with hyphens (3s_m -> 3s-m)

        Args:
            grammatical_form: Database grammatical form key (e.g., "verb/lt_3s_m_pres")

        Returns:
            Legacy format key (e.g., "3s-m_pres")
        """
        # If already in legacy format (no prefix), return as-is
        if not grammatical_form.startswith('verb/'):
            return grammatical_form

        # Remove "verb/{lang}_" prefix
        # Format: "verb/lt_1s_pres" or "verb/fr_3p_fut"
        parts = grammatical_form.split('_', 1)  # Split on first underscore only
        if len(parts) < 2:
            return grammatical_form  # Return original if format unexpected

        # parts[0] is "verb/lt" or "verb/fr"
        # parts[1] is "1s_pres" or "3s_m_pres" or similar
        key_without_prefix = parts[1]

        # Now convert underscores to hyphens in person/number part
        # e.g., "3s_m_pres" -> "3s-m_pres"
        # The pattern is: {person}{number}_{gender}_{tense}
        # We want hyphens between person/number/gender, but underscore before tense

        # Split by underscore to find components
        components = key_without_prefix.split('_')
        if len(components) == 2:
            # Simple case: "1s_pres" or "1p_past"
            return key_without_prefix
        elif len(components) == 3:
            # Has gender: "3s_m_pres" -> "3s-m_pres"
            person_num = components[0]
            gender = components[1]
            tense = components[2]
            return f"{person_num}-{gender}_{tense}"
        else:
            # Unexpected format, return as-is
            return key_without_prefix

    def _format_verb_entry(self, entry: Dict[str, Any], is_last: bool = False) -> str:
        """
        Format a single verb entry with custom JSON formatting.

        Creates a format where:
        - Top-level verb fields are on separate lines with proper indentation
        - Each grammatical form entry is condensed to a single line
        - More vertical spacing between verb entries (like the old format)

        Args:
            entry: Verb entry dictionary
            is_last: Whether this is the last entry in the array

        Returns:
            Formatted string for this verb entry
        """
        lines = []
        lines.append('  {')

        # Determine the keys order - put grammatical_forms last
        keys_order = []
        for key in ['guid', 'base_target', 'base_english', 'corpus', 'group', 'level', 'word_type']:
            if key in entry:
                keys_order.append(key)

        # Add any other keys except grammatical_forms
        for key in entry:
            if key not in keys_order and key != 'grammatical_forms':
                keys_order.append(key)

        # Write the non-grammatical-forms fields
        for key in keys_order:
            value_json = json.dumps(entry[key], ensure_ascii=False)
            lines.append(f'    "{key}": {value_json},')

        # Write grammatical_forms with each form on one line
        if 'grammatical_forms' in entry:
            lines.append('    "grammatical_forms": {')

            forms = entry['grammatical_forms']
            form_keys = list(forms.keys())
            for j, form_key in enumerate(form_keys):
                form_value_json = json.dumps(forms[form_key], ensure_ascii=False, separators=(', ', ': '))
                comma = '' if j == len(form_keys) - 1 else ','
                lines.append(f'      "{form_key}": {form_value_json}{comma}')

            lines.append('    }')

        # Close the verb entry object
        comma = '' if is_last else ','
        lines.append(f'  }}{comma}')

        return '\n'.join(lines) + '\n'

    def _generate_pinyin(self, chinese_text: str) -> Optional[str]:
        """
        Generate pinyin for Chinese text.

        Args:
            chinese_text: Chinese text to convert to pinyin

        Returns:
            Pinyin string with tone marks, or None if pypinyin is not available
        """
        if not PYPINYIN_AVAILABLE or not chinese_text:
            return None

        try:
            # Use Style.TONE to get pinyin with tone marks (e.g., "nǐ hǎo")
            pinyin_list = lazy_pinyin(chinese_text, style=Style.TONE)
            return ' '.join(pinyin_list)
        except Exception as e:
            logger.warning(f"Failed to generate pinyin for '{chinese_text}': {e}")
            return None

    def _get_english_translation_from_db(self, session, lemma_id: int, grammatical_form: str) -> Optional[str]:
        """
        Look up the English translation for a grammatical form from the database.
        Maps French/other language grammatical forms to their Lithuanian equivalents
        since English translations are stored with Lithuanian form labels.

        Args:
            session: Database session
            lemma_id: The lemma ID
            grammatical_form: The grammatical form (e.g., "verb/fr_1p_impf")

        Returns:
            English translation string, or None if not found
        """
        # Map French verb forms to Lithuanian verb forms (which have English translations)
        fr_to_lt_mapping = {
            # Present tense
            'verb/fr_1s_pres': 'verb/lt_1s_pres',
            'verb/fr_2s_pres': 'verb/lt_2s_pres',
            'verb/fr_3s_pres': 'verb/lt_3s_m_pres',  # Use masculine for he/she
            'verb/fr_1p_pres': 'verb/lt_1p_pres',
            'verb/fr_2p_pres': 'verb/lt_2p_pres',
            'verb/fr_3p_pres': 'verb/lt_3p_m_pres',  # Use masculine for they
            # Imperfect → Past tense (closest equivalent)
            'verb/fr_1s_impf': 'verb/lt_1s_past',
            'verb/fr_2s_impf': 'verb/lt_2s_past',
            'verb/fr_3s_impf': 'verb/lt_3s_m_past',
            'verb/fr_1p_impf': 'verb/lt_1p_past',
            'verb/fr_2p_impf': 'verb/lt_2p_past',
            'verb/fr_3p_impf': 'verb/lt_3p_m_past',
            # Future tense
            'verb/fr_1s_fut': 'verb/lt_1s_fut',
            'verb/fr_2s_fut': 'verb/lt_2s_fut',
            'verb/fr_3s_fut': 'verb/lt_3s_m_fut',
            'verb/fr_1p_fut': 'verb/lt_1p_fut',
            'verb/fr_2p_fut': 'verb/lt_2p_fut',
            'verb/fr_3p_fut': 'verb/lt_3p_m_fut',
            # Passé composé → Past tense
            'verb/fr_1s_pc': 'verb/lt_1s_past',
            'verb/fr_2s_pc': 'verb/lt_2s_past',
            'verb/fr_3s_pc': 'verb/lt_3s_m_past',
            'verb/fr_1p_pc': 'verb/lt_1p_past',
            'verb/fr_2p_pc': 'verb/lt_2p_past',
            'verb/fr_3p_pc': 'verb/lt_3p_m_past',
            # Conditional and subjunctive don't have direct Lithuanian equivalents
            # Leave those to fall through to generation
        }

        # Check if we have a mapping for this form
        mapped_form = fr_to_lt_mapping.get(grammatical_form)
        if not mapped_form:
            return None

        # Look up the English derivative form with the mapped grammatical form
        english_form = session.query(DerivativeForm).filter(
            DerivativeForm.lemma_id == lemma_id,
            DerivativeForm.language_code == 'en',
            DerivativeForm.grammatical_form == mapped_form
        ).first()

        if english_form:
            return english_form.derivative_form_text

        return None

    def _generate_grammatical_form_label(self, grammatical_form: str, base_english: str, pos_type: str) -> str:
        """
        Generate a readable English label for a grammatical form.

        Args:
            grammatical_form: The grammatical form identifier (e.g., "verb/fr_1s_pres", "noun/fr_plural")
            base_english: The base English word
            pos_type: Part of speech type

        Returns:
            Readable English label for the grammatical form
        """
        # Lithuanian verb forms - proper conjugations with tense
        lithuanian_verb_forms = {
            # Present tense
            'verb/lt_1s_pres': f'I {base_english}',
            'verb/lt_2s_pres': f'you(s.) {base_english}',
            'verb/lt_3s_m_pres': f'he {base_english}s',
            'verb/lt_3s_f_pres': f'she {base_english}s',
            'verb/lt_1p_pres': f'we {base_english}',
            'verb/lt_2p_pres': f'you(pl.) {base_english}',
            'verb/lt_3p_m_pres': f'they(m.) {base_english}',
            'verb/lt_3p_f_pres': f'they(f.) {base_english}',
            # Past tense - handle irregular verbs
            'verb/lt_1s_past': f'I {base_english}' if base_english.endswith('e') else f'I {base_english}ed',
            'verb/lt_2s_past': f'you(s.) {base_english}' if base_english.endswith('e') else f'you(s.) {base_english}ed',
            'verb/lt_3s_m_past': f'he {base_english}' if base_english.endswith('e') else f'he {base_english}ed',
            'verb/lt_3s_f_past': f'she {base_english}' if base_english.endswith('e') else f'she {base_english}ed',
            'verb/lt_1p_past': f'we {base_english}' if base_english.endswith('e') else f'we {base_english}ed',
            'verb/lt_2p_past': f'you(pl.) {base_english}' if base_english.endswith('e') else f'you(pl.) {base_english}ed',
            'verb/lt_3p_m_past': f'they(m.) {base_english}' if base_english.endswith('e') else f'they(m.) {base_english}ed',
            'verb/lt_3p_f_past': f'they(f.) {base_english}' if base_english.endswith('e') else f'they(f.) {base_english}ed',
            # Future tense
            'verb/lt_1s_fut': f'I will {base_english}',
            'verb/lt_2s_fut': f'you(s.) will {base_english}',
            'verb/lt_3s_m_fut': f'he will {base_english}',
            'verb/lt_3s_f_fut': f'she will {base_english}',
            'verb/lt_1p_fut': f'we will {base_english}',
            'verb/lt_2p_fut': f'you(pl.) will {base_english}',
            'verb/lt_3p_m_fut': f'they(m.) will {base_english}',
            'verb/lt_3p_f_fut': f'they(f.) will {base_english}',
        }

        # French verb tenses
        french_verb_forms = {
            'verb/fr_1s_pres': f'{base_english} (I, present)',
            'verb/fr_2s_pres': f'{base_english} (you, present)',
            'verb/fr_3s_pres': f'{base_english} (he/she, present)',
            'verb/fr_1p_pres': f'{base_english} (we, present)',
            'verb/fr_2p_pres': f'{base_english} (you all, present)',
            'verb/fr_3p_pres': f'{base_english} (they, present)',
            'verb/fr_1s_impf': f'{base_english} (I, imperfect)',
            'verb/fr_2s_impf': f'{base_english} (you, imperfect)',
            'verb/fr_3s_impf': f'{base_english} (he/she, imperfect)',
            'verb/fr_1p_impf': f'{base_english} (we, imperfect)',
            'verb/fr_2p_impf': f'{base_english} (you all, imperfect)',
            'verb/fr_3p_impf': f'{base_english} (they, imperfect)',
            'verb/fr_1s_fut': f'{base_english} (I, future)',
            'verb/fr_2s_fut': f'{base_english} (you, future)',
            'verb/fr_3s_fut': f'{base_english} (he/she, future)',
            'verb/fr_1p_fut': f'{base_english} (we, future)',
            'verb/fr_2p_fut': f'{base_english} (you all, future)',
            'verb/fr_3p_fut': f'{base_english} (they, future)',
            'verb/fr_1s_cond': f'{base_english} (I, conditional)',
            'verb/fr_2s_cond': f'{base_english} (you, conditional)',
            'verb/fr_3s_cond': f'{base_english} (he/she, conditional)',
            'verb/fr_1p_cond': f'{base_english} (we, conditional)',
            'verb/fr_2p_cond': f'{base_english} (you all, conditional)',
            'verb/fr_3p_cond': f'{base_english} (they, conditional)',
            'verb/fr_1s_subj': f'{base_english} (I, subjunctive)',
            'verb/fr_2s_subj': f'{base_english} (you, subjunctive)',
            'verb/fr_3s_subj': f'{base_english} (he/she, subjunctive)',
            'verb/fr_1p_subj': f'{base_english} (we, subjunctive)',
            'verb/fr_2p_subj': f'{base_english} (you all, subjunctive)',
            'verb/fr_3p_subj': f'{base_english} (they, subjunctive)',
            'verb/fr_1s_pc': f'{base_english} (I, perfect)',
            'verb/fr_2s_pc': f'{base_english} (you, perfect)',
            'verb/fr_3s_pc': f'{base_english} (he/she, perfect)',
            'verb/fr_1p_pc': f'{base_english} (we, perfect)',
            'verb/fr_2p_pc': f'{base_english} (you all, perfect)',
            'verb/fr_3p_pc': f'{base_english} (they, perfect)',
            'verb/fr_inf': f'{base_english} (infinitive)',
            'verb/fr_pres_part': f'{base_english} (present participle)',
            'verb/fr_past_part': f'{base_english} (past participle)',
        }

        # French noun forms (with gender from grammar_facts)
        french_noun_forms = {
            'noun/fr_singular': f'{base_english} (singular)',
            'noun/fr_plural': f'{base_english} (plural)',
        }

        # French adjective forms (with gender)
        french_adj_forms = {
            'adjective/fr_singular_m': f'{base_english} (masculine singular)',
            'adjective/fr_plural_m': f'{base_english} (masculine plural)',
            'adjective/fr_singular_f': f'{base_english} (feminine singular)',
            'adjective/fr_plural_f': f'{base_english} (feminine plural)',
        }

        # Check for exact matches
        if grammatical_form in lithuanian_verb_forms:
            return lithuanian_verb_forms[grammatical_form]
        elif grammatical_form in french_verb_forms:
            return french_verb_forms[grammatical_form]
        elif grammatical_form in french_noun_forms:
            return french_noun_forms[grammatical_form]
        elif grammatical_form in french_adj_forms:
            return french_adj_forms[grammatical_form]

        # Generic fallback: convert underscores to spaces and add base word
        readable_form = grammatical_form.replace('_', ' ').replace('/', ' ')
        return f'{base_english} ({readable_form})'

    def _generate_derivative_noun_phrases(self, lemma: Lemma, base_english: str, base_target: str, entry_level: int) -> Dict[str, Dict[str, any]]:
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
        derivative_phrases = {}

        # Only generate for nouns
        if lemma.pos_type != 'noun':
            return derivative_phrases

        # Generate "where is X?" phrase for location-related nouns (Lithuanian only for now)
        # Uses nominative case (dictionary form)
        # Note: This is Lithuanian-specific and disabled for other languages
        if self.language == 'lt':
            where_is_subtypes = {
                'building_structure',  # where is the bank, hospital, school
                'location',            # where is the park, city
                'place_name'          # where is Paris, etc.
            }

            if lemma.pos_subtype in where_is_subtypes:
                where_is_level = max(entry_level, 19)
                derivative_phrases['where_is'] = {
                    "level": where_is_level,
                    "target": f"Kur yra {base_target}?",
                    "english": f"Where is the {base_english}?"
                }

        # Generate "this is my X" phrase for possessable items
        # Uses nominative case (dictionary form) - "Tai mano X"
        # TODO: Disabled until we can handle plural-only nouns (pants, scissors, etc.)
        # Requires adding grammatical_number field to database to properly generate
        # "These are my pants" vs "This is my shirt"
        if False:  # Temporarily disabled
            this_is_my_subtypes = {
                'clothing_accessory',     # this is my shirt, hat
                'small_movable_object',   # this is my book, phone
                'body_part'              # this is my hand, foot
            }

            if lemma.pos_subtype in this_is_my_subtypes:
                this_is_my_level = max(entry_level, 19)
                derivative_phrases['this_is_my'] = {
                    "level": this_is_my_level,
                    "lithuanian": f"Tai mano {base_lithuanian}",
                    "english": f"This is my {base_english}"
                }

        return derivative_phrases

    def export_wireword_directory(self, output_dir: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Export WireWord format files to directory structure.
        Creates two files: wireword_verbs.json and wireword_nouns.json

        Args:
            output_dir: Base output directory (e.g., lang_lt/generated)

        Returns:
            Tuple of (success flag, export results dictionary)
        """
        # Create wireword subdirectory
        wireword_dir = os.path.join(output_dir, 'wireword')
        os.makedirs(wireword_dir, exist_ok=True)

        results = {
            'files_created': [],
            'levels_exported': set(),
            'subtypes_exported': set()
        }

        # Export verbs to wireword_verbs.json
        verbs_path = os.path.join(wireword_dir, 'wireword_verbs.json')
        logger.info(f"Exporting verbs to {verbs_path}...")
        verbs_success, verbs_stats = self.export_verbs_to_wireword_format(
            output_path=verbs_path,
            include_without_guid=False,
            include_unverified=True,
            pretty_print=True
        )

        if verbs_success:
            results['files_created'].append(verbs_path)
            if verbs_stats:
                for level in verbs_stats.level_distribution.keys():
                    results['levels_exported'].add(int(level))
            logger.info(f"✅ Exported verbs to {verbs_path}")
        else:
            logger.error(f"❌ Failed to export verbs")
            return False, results

        # Export non-verbs to wireword_nouns.json
        nouns_path = os.path.join(wireword_dir, 'wireword_nouns.json')
        logger.info(f"Exporting non-verbs to {nouns_path}...")
        nouns_success, nouns_stats = self.export_to_wireword_format(
            output_path=nouns_path,
            include_without_guid=False,
            include_unverified=True,
            pretty_print=True
        )

        if nouns_success:
            results['files_created'].append(nouns_path)
            if nouns_stats:
                for level in nouns_stats.level_distribution.keys():
                    results['levels_exported'].add(int(level))
                for pos_type in nouns_stats.pos_distribution.keys():
                    results['subtypes_exported'].add(pos_type)
            logger.info(f"✅ Exported non-verbs to {nouns_path}")
        else:
            logger.error(f"❌ Failed to export non-verbs")
            return False, results

        # Convert sets to sorted lists for JSON serialization
        results['levels_exported'] = sorted(list(results['levels_exported']))
        results['subtypes_exported'] = sorted(list(results['subtypes_exported']))

        logger.info(f"✅ WireWord directory export completed: {len(results['files_created'])} files created")
        return True, results

    def export_verbs_to_wireword_format(
        self,
        output_path: str,
        difficulty_level: Optional[int] = None,
        pos_subtype: Optional[str] = None,
        limit: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True,
        pretty_print: bool = True
    ) -> Tuple[bool, Optional[ExportStats]]:
        """
        Export verbs from database to WireWord API format.

        Uses language-specific difficulty level overrides when available.

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
        from wordfreq.storage.models.schema import LemmaDifficultyOverride
        from wordfreq.storage.crud.difficulty_override import get_effective_difficulty_level

        session = self.get_session()
        try:
            # NOTE: For languages in LemmaTranslation table (es, de, pt), we need special handling
            # TODO: Add proper join for LemmaTranslation table or filter in Python

            # Build the query for verbs
            query = session.query(Lemma)\
                .filter(Lemma.pos_type == 'verb')

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
                    (LemmaDifficultyOverride.lemma_id == Lemma.id) &
                    (LemmaDifficultyOverride.language_code == self.language)
                )
                # Use override if exists, otherwise use default
                effective_level = func.coalesce(
                    LemmaDifficultyOverride.difficulty_level,
                    Lemma.difficulty_level
                )
                query = query.filter(effective_level == difficulty_level)
                logger.info(f"Filtering by effective difficulty level: {difficulty_level} for language: {self.language}")

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

            # Transform to WireWord format
            wireword_data = []
            for lemma in lemmas:
                # Get effective difficulty level for this language
                effective_lemma_level = get_effective_difficulty_level(session, lemma, self.language)
                if effective_lemma_level is None:
                    effective_lemma_level = 1  # Default to level 1 if not set

                # Skip words at level -1 (excluded from all wireword exports)
                if effective_lemma_level == -1:
                    continue

                # Get all derivative forms for this verb
                derivative_forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id
                ).all()

                # Get base English and target language forms
                base_english = self.get_english_word_from_lemma(session, lemma)
                base_target = get_translation(session, lemma, self.language)

                # For Chinese, optionally convert to simplified
                if self.language == 'zh' and self.simplified_chinese and base_target:
                    base_target = to_simplified(base_target)

                # Build grammatical forms (conjugations)
                grammatical_forms = {}
                target_alternatives = []
                target_alternatives_pinyin = []
                english_synonyms = []
                target_synonyms = []
                target_synonyms_pinyin = []

                for form in derivative_forms:
                    if form.is_base_form:
                        # Skip base forms as they're already in base_target/base_english
                        continue

                    # Handle different types of derivative forms
                    if form.language_code == 'en':
                        if form.grammatical_form == 'synonym':
                            english_synonyms.append(form.derivative_form_text)
                    elif form.language_code == self.language:
                        if form.grammatical_form == 'synonym':
                            target_synonyms.append(form.derivative_form_text)
                            # Generate pinyin for Chinese synonyms
                            if self.language == 'zh':
                                pinyin = self._generate_pinyin(form.derivative_form_text)
                                target_synonyms_pinyin.append(pinyin if pinyin else '')
                        elif form.grammatical_form != 'infinitive':
                            # This is a conjugated form
                            form_level = max(effective_lemma_level, 1)

                            # For French, only export present, passé composé (past), and future
                            if self.language == 'fr':
                                # Extract tense from grammatical_form (format: "verb/fr_1s_pres", "verb/fr_1p_pc", etc.)
                                if '_' in form.grammatical_form:
                                    tense_suffix = form.grammatical_form.split('_')[-1]
                                    # Only allow pres (present), pc (passé composé), and fut (future)
                                    if tense_suffix not in ['pres', 'pc', 'fut']:
                                        continue  # Skip imperfect, conditional, subjunctive

                                    # Apply tense-specific minimum levels
                                    if tense_suffix == 'pc':
                                        # Passé composé (past) minimum level is 7
                                        form_level = max(form_level, 7)
                                    elif tense_suffix == 'fut':
                                        # Future tense minimum level is 12
                                        form_level = max(form_level, 12)

                            # Apply tense-specific minimum levels for Lithuanian
                            elif self.language == 'lt':
                                # Extract tense from grammatical_form (format: "1s_past", "3p-m_fut", etc.)
                                if '_' in form.grammatical_form:
                                    tense_suffix = form.grammatical_form.split('_')[-1]
                                    if tense_suffix == 'past':
                                        # Past tense minimum level is 7
                                        form_level = max(form_level, 7)
                                    elif tense_suffix == 'fut':
                                        # Future tense minimum level is 12
                                        form_level = max(form_level, 12)

                            # Try to look up English translation from database first
                            english_label = self._get_english_translation_from_db(
                                session,
                                lemma.id,
                                form.grammatical_form
                            )

                            # If not found in database, generate it
                            if not english_label:
                                english_label = self._generate_grammatical_form_label(
                                    form.grammatical_form,
                                    base_english,
                                    'verb'
                                )

                            gram_form = {
                                "level": form_level,
                                "target": form.derivative_form_text,
                                "english": english_label
                            }

                            # Add pinyin for Chinese grammatical forms
                            if self.language == 'zh':
                                pinyin = self._generate_pinyin(form.derivative_form_text)
                                if pinyin:
                                    gram_form['target_pinyin'] = pinyin

                            # Convert grammatical form key to legacy format
                            # e.g., "verb/lt_3s_m_pres" -> "3s-m_pres"
                            legacy_key = self._convert_to_legacy_grammatical_form_key(form.grammatical_form)
                            grammatical_forms[legacy_key] = gram_form

                # Create WireWord object
                wireword = {
                    'guid': lemma.guid,
                    'base_target': base_target,
                    'base_english': base_english,
                    'corpus': 'VERBS',
                    'group': format_subtype_display_name(lemma.pos_subtype or 'action'),
                    'level': effective_lemma_level,
                    'word_type': 'verb'
                }

                # Add filename field for Chinese to use GUID in URL instead of Chinese characters
                if self.language == 'zh' and lemma.guid:
                    wireword['filename'] = lemma.guid

                # Add pinyin for Chinese language exports
                if self.language == 'zh' and base_target:
                    pinyin = self._generate_pinyin(base_target)
                    if pinyin:
                        wireword['target_pinyin'] = pinyin

                # Add optional fields
                if english_synonyms:
                    wireword['english_synonyms'] = english_synonyms
                if target_synonyms:
                    wireword['target_synonyms'] = target_synonyms
                    # Add pinyin for Chinese synonyms
                    if self.language == 'zh' and target_synonyms_pinyin:
                        wireword['target_synonyms_pinyin'] = target_synonyms_pinyin

                # Add grammatical forms (conjugations)
                if grammatical_forms:
                    wireword['grammatical_forms'] = grammatical_forms

                if lemma.notes:
                    wireword['notes'] = lemma.notes

                # Add tags
                tags = [lemma.pos_subtype or 'action', f"level_{effective_lemma_level}"]
                if lemma.verified:
                    tags.append('verified')
                wireword['tags'] = tags

                wireword_data.append(wireword)

            # Calculate basic stats
            from .data_models import ExportStats

            # Calculate level distribution
            level_dist = {}
            for w in wireword_data:
                level = str(w.get('level', 0))
                level_dist[level] = level_dist.get(level, 0) + 1

            stats = ExportStats(
                total_entries=len(wireword_data),
                entries_with_guids=sum(1 for w in wireword_data if w.get('guid')),
                pos_distribution={'verb': len(wireword_data)},
                level_distribution=level_dist
            )

            # Write to JSON file
            try:
                # Ensure the directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                with open(output_path, 'w', encoding='utf-8') as f:
                    if pretty_print:
                        # Write with custom formatting for verbs
                        # Each verb entry gets more vertical space, but grammatical forms are condensed to one line each
                        f.write('[\n')
                        for i, entry in enumerate(wireword_data):
                            f.write(self._format_verb_entry(entry, is_last=(i == len(wireword_data) - 1)))
                        f.write(']\n')
                    else:
                        # Compact format
                        json.dump(wireword_data, f, ensure_ascii=False, separators=(',', ':'))

                logger.info(f"✅ Successfully wrote {len(wireword_data)} verb entries to {output_path}")
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
