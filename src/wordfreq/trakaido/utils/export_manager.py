
#!/usr/bin/env python3
"""
Export manager for trakaido data.

Provides the TrakaidoExporter class for exporting trakaido data
in various formats (JSON, text, wireword, etc.).
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import sys

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'
sys.path.append(GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import WordToken, Lemma, DerivativeForm
from wordfreq.storage.models.grammar_fact import GrammarFact
from wordfreq.trakaido.dict_generator import (
    generate_structure_file,
    generate_dictionary_file
)
from wordfreq.tools.chinese_converter import to_simplified

# Import pypinyin for Chinese pinyin generation
try:
    from pypinyin import lazy_pinyin, Style
    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False
    logger.warning("pypinyin not available - pinyin generation will be disabled")

from .data_models import ExportStats, create_export_stats
from .text_rendering import format_subtype_display_name

# Configure logging
logger = logging.getLogger(__name__)


class TrakaidoExporter:
    """Main class for exporting trakaido data in various formats."""

    # Language configuration mapping
    LANGUAGE_CONFIG = {
        'lt': {
            'name': 'Lithuanian',
            'field': 'lithuanian_translation'
        },
        'zh': {
            'name': 'Chinese',
            'field': 'chinese_translation'
        },
        'ko': {
            'name': 'Korean',
            'field': 'korean_translation'
        },
        'fr': {
            'name': 'French',
            'field': 'french_translation'
        }
    }

    def __init__(self, db_path: str = None, debug: bool = False, language: str = 'lt', simplified_chinese: bool = True):
        """
        Initialize the TrakaidoExporter.

        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
            language: Target language code ('lt' for Lithuanian, 'zh' for Chinese)
            simplified_chinese: If True and language is 'zh', convert to Simplified Chinese (default: True)
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.language = language
        self.simplified_chinese = simplified_chinese

        if language not in self.LANGUAGE_CONFIG:
            raise ValueError(f"Unsupported language: {language}. Supported: {', '.join(self.LANGUAGE_CONFIG.keys())}")

        self.language_name = self.LANGUAGE_CONFIG[language]['name']
        self.language_field = self.LANGUAGE_CONFIG[language]['field']

        if debug:
            logger.setLevel(logging.DEBUG)
    
    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)
    
    def get_english_word_from_lemma(self, session, lemma: Lemma) -> Optional[str]:
        """
        Get the primary English word for a lemma.

        Uses lemma_text directly to preserve proper capitalization
        (e.g., "Christmas", "Monday", "Lithuania").

        Args:
            session: Database session
            lemma: Lemma object

        Returns:
            English word string or None if not found
        """
        # Use lemma_text directly - it has the correct capitalization
        # Derivative forms are typically lowercase for tokenization/matching
        return lemma.lemma_text
    
    def query_trakaido_data(
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
        
        Args:
            session: Database session
            difficulty_level: Filter by specific difficulty level (optional)
            pos_type: Filter by specific POS type (optional)
            pos_subtype: Filter by specific POS subtype (optional)
            limit: Limit number of results (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)
            
        Returns:
            List of dictionaries with trakaido data
        """
        logger.info(f"Querying database for trakaido data (language: {self.language_name})...")

        # Get the language field to query
        language_column = getattr(Lemma, self.language_field)

        # Build the query
        query = session.query(Lemma)\
            .filter(language_column != None)\
            .filter(language_column != "")\
            .filter(Lemma.pos_type != 'verb')  # Exclude verbs - they go in separate file

        # Apply filters
        if not include_without_guid:
            query = query.filter(Lemma.guid != None)
        
        if not include_unverified:
            query = query.filter(Lemma.verified == True)
        
        if difficulty_level is not None:
            query = query.filter(Lemma.difficulty_level == difficulty_level)
            logger.info(f"Filtering by difficulty level: {difficulty_level}")
        
        if pos_type:
            query = query.filter(Lemma.pos_type == pos_type.lower())
            logger.info(f"Filtering by POS type: {pos_type}")
        
        if pos_subtype:
            query = query.filter(Lemma.pos_subtype == pos_subtype)
            logger.info(f"Filtering by POS subtype: {pos_subtype}")
        
        # Order by GUID for consistent output
        query = query.order_by(Lemma.guid.asc().nullslast())
        
        if limit:
            query = query.limit(limit)
            logger.info(f"Limiting results to: {limit}")
        
        lemmas = query.all()
        logger.info(f"Found {len(lemmas)} lemmas matching criteria")
        
        # Convert to export format
        export_data = []
        skipped_count = 0
        
        for lemma in lemmas:
            # Get the English word
            english_word = self.get_english_word_from_lemma(session, lemma)

            if not english_word:
                logger.warning(f"No English word found for lemma ID {lemma.id} (GUID: {lemma.guid})")
                skipped_count += 1
                continue

            # Get the target language translation
            target_translation = getattr(lemma, self.language_field)

            # For Chinese, optionally convert to simplified
            if self.language == 'zh' and self.simplified_chinese and target_translation:
                target_translation = to_simplified(target_translation)

            # Create the export entry with standardized key names
            entry = {
                "English": english_word,
                "Target": target_translation,  # Use "Target" instead of language-specific name
                "GUID": lemma.guid or "",
                "trakaido_level": lemma.difficulty_level or 1,
                "POS": lemma.pos_type or "noun",
                "subtype": lemma.pos_subtype or "other"
            }

            export_data.append(entry)
        
        if skipped_count > 0:
            logger.warning(f"Skipped {skipped_count} lemmas without English words")
        
        # Sort the data by trakaido_level, then POS, then subtype, then English alphabetically
        logger.info("Sorting export data...")
        export_data.sort(key=lambda x: (
            x.get("trakaido_level", 999),  # Sort by level first
            x.get("POS", "zzz"),           # Then by POS
            x.get("subtype", "zzz"),       # Then by subtype
            x.get("English", "").lower()   # Finally by English word alphabetically
        ))
        
        logger.info(f"Successfully prepared {len(export_data)} entries for export")
        return export_data
    
    def write_json_file(self, data: List[Dict[str, Any]], output_path: str, 
                       pretty_print: bool = True) -> ExportStats:
        """
        Write the export data to a JSON file.
        
        Args:
            data: List of dictionaries to export
            output_path: Path to write the JSON file
            pretty_print: Whether to format JSON with indentation
            
        Returns:
            ExportStats object with export statistics
        """
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                if pretty_print:
                    # Write with nice formatting, one entry per line
                    f.write('[\n')
                    for i, entry in enumerate(data):
                        line = json.dumps(entry, ensure_ascii=False, separators=(', ', ': '))
                        if i < len(data) - 1:
                            f.write(f'  {line},\n')
                        else:
                            f.write(f'  {line}\n')
                    f.write(']\n')
                else:
                    # Compact format
                    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            
            # Calculate statistics
            stats = create_export_stats(data)
            
            logger.info(f"✅ Successfully wrote {len(data)} entries to {output_path}")
            logger.info(f"Entries with GUIDs: {stats.entries_with_guids}/{stats.total_entries}")
            logger.info(f"POS distribution: {stats.pos_distribution}")
            logger.info(f"Level distribution: {stats.level_distribution}")
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ Failed to write JSON file: {e}")
            raise
    
    def export_to_json(
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
        Export trakaido data to JSON format.
        
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
            # Query the data
            export_data = self.query_trakaido_data(
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
            
            # Write to JSON file
            stats = self.write_json_file(export_data, output_path, pretty_print)
            
            return True, stats
            
        except Exception as e:
            logger.error(f"Export to JSON failed: {e}")
            return False, None
        finally:
            session.close()
    
    def export_to_text(
        self,
        output_path: str,
        pos_subtype: str,
        difficulty_level: Optional[int] = None,
        include_without_guid: bool = False,
        include_unverified: bool = True
    ) -> Tuple[bool, Optional[ExportStats]]:
        """
        Export trakaido data to simple text format with just "en" and "lt" keys.
        
        Args:
            output_path: Path to write the text file
            pos_subtype: Specific POS subtype to export (required)
            difficulty_level: Filter by specific difficulty level (optional)
            include_without_guid: Include lemmas without GUIDs (default: False)
            include_unverified: Include unverified entries (default: True)
            
        Returns:
            Tuple of (success flag, export statistics)
        """
        session = self.get_session()
        try:
            # Query the data for the specific subtype
            export_data = self.query_trakaido_data(
                session=session,
                difficulty_level=difficulty_level,
                pos_subtype=pos_subtype,
                include_without_guid=include_without_guid,
                include_unverified=include_unverified
            )
            
            if not export_data:
                logger.warning(f"No data found for subtype '{pos_subtype}' matching the specified criteria")
                return False, None
            
            # Convert to simple text format
            text_data = []
            for entry in export_data:
                text_entry = {
                    "en": entry["English"],
                    "lt": entry["Lithuanian"]
                }
                text_data.append(text_entry)
            
            # Write to file
            try:
                # Ensure the directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    # Write as JSON array with nice formatting
                    f.write('[\n')
                    for i, entry in enumerate(text_data):
                        line = json.dumps(entry, ensure_ascii=False, separators=(', ', ': '))
                        if i < len(text_data) - 1:
                            f.write(f'  {line},\n')
                        else:
                            f.write(f'  {line}\n')
                    f.write(']\n')
                
                # Calculate statistics from original data
                stats = create_export_stats(export_data)
                
                logger.info(f"✅ Successfully wrote {len(text_data)} entries to {output_path}")
                logger.info(f"Subtype: {pos_subtype}")
                logger.info(f"Entries with GUIDs: {stats.entries_with_guids}/{stats.total_entries}")
                if difficulty_level is not None:
                    logger.info(f"Difficulty level: {difficulty_level}")
                
                return True, stats
                
            except Exception as e:
                logger.error(f"❌ Failed to write text file: {e}")
                return False, None
            
        except Exception as e:
            logger.error(f"Export to text failed: {e}")
            return False, None
        finally:
            session.close()

    def export_to_lang_lt(self, output_dir: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Export words to lang_lt directory structure using dict_generator.
        
        Args:
            output_dir: Output directory for lang_lt files
            
        Returns:
            Tuple of (success flag, export results dictionary)
        """
        try:
            session = self.get_session()
            
            # Generate structure files for each level
            levels_generated = []
            for level in range(1, 21):  # Levels 1-20
                try:
                    filepath = generate_structure_file(session, level, output_dir)
                    if filepath:
                        levels_generated.append(level)
                        logger.info(f"Generated structure file for level {level}")
                except Exception as e:
                    logger.warning(f"Failed to generate structure file for level {level}: {e}")
            
            # Generate dictionary files for each subtype
            subtypes = session.query(Lemma.pos_subtype).filter(
                Lemma.pos_subtype.isnot(None),
                Lemma.guid.isnot(None)
            ).distinct().all()
            
            dictionaries_generated = []
            for subtype_tuple in subtypes:
                subtype = subtype_tuple[0]
                if subtype:
                    try:
                        filepath = generate_dictionary_file(session, subtype, output_dir)
                        if filepath:
                            dictionaries_generated.append(subtype)
                            logger.info(f"Generated dictionary file for {subtype}")
                    except Exception as e:
                        logger.warning(f"Failed to generate dictionary file for {subtype}: {e}")
            
            session.close()
            
            results = {
                'levels_generated': levels_generated,
                'dictionaries_generated': dictionaries_generated,
                'output_directory': output_dir,
                'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            success = len(levels_generated) > 0 or len(dictionaries_generated) > 0
            
            if success:
                logger.info(f"✅ Export to lang_lt completed:")
                logger.info(f"   Structure files: {len(levels_generated)} levels")
                logger.info(f"   Dictionary files: {len(dictionaries_generated)} subtypes")
                logger.info(f"   Output directory: {output_dir}")
            else:
                logger.error("❌ No files were generated during lang_lt export")
            
            return success, results
            
        except Exception as e:
            logger.error(f"Error exporting to lang_lt: {e}")
            return False, {'error': str(e)}

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
            # Query the data using existing method
            export_data = self.query_trakaido_data(
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

                    # Handle different types of derivative forms
                    if form.language_code == 'en':
                        if form.grammatical_form == 'alternative_form':
                            english_alternatives.append(form.derivative_form_text)
                        elif form.grammatical_form == 'synonym':
                            english_synonyms.append(form.derivative_form_text)
                    elif form.language_code == self.language:
                        if form.grammatical_form == 'alternative_form':
                            target_alternatives.append(form.derivative_form_text)
                            # Generate pinyin for Chinese alternatives (keep arrays parallel)
                            if self.language == 'zh':
                                pinyin = self._generate_pinyin(form.derivative_form_text)
                                target_alternatives_pinyin.append(pinyin if pinyin else '')
                        elif form.grammatical_form == 'synonym':
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
                                "english": f"{entry['English']} (plural)"  # Simple plural English form
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
                                "english": f"{entry['English']}{english_suffix}"
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

                                # Generate a readable English label from the grammatical form
                                english_label = self._generate_grammatical_form_label(
                                    form.grammatical_form,
                                    entry['English'],
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
                    entry['English'],
                    entry['Target'],
                    entry['trakaido_level']
                )
                grammatical_forms.update(derivative_phrases)

                # Get corpus assignment for this entry
                corpus_key = (entry['trakaido_level'], entry['subtype'])
                assigned_corpus = corpus_assignments.get(corpus_key, 'Trakaido')

                # Create WireWord object
                wireword = {
                    'guid': entry['GUID'],
                    'base_target': entry['Target'],
                    'base_english': entry['English'],
                    'corpus': assigned_corpus,
                    'group': format_subtype_display_name(entry['subtype']),
                    'level': entry['trakaido_level'],
                    'word_type': self._normalize_pos_type(entry['POS'])
                }

                # Add pinyin for Chinese language exports
                if self.language == 'zh' and entry['Target']:
                    pinyin = self._generate_pinyin(entry['Target'])
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

    def export_wireword_directory(self, base_output_dir: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Export WireWord format files to lang_lt/generated/wireword/ directory structure.
        Creates separate files for each level and subtype.
        
        Args:
            base_output_dir: Base output directory (e.g., lang_lt/generated)
            
        Returns:
            Tuple of (success flag, export results dictionary)
        """
        try:
            session = self.get_session()
            
            # Create wireword directory
            wireword_dir = os.path.join(base_output_dir, 'wireword')
            os.makedirs(wireword_dir, exist_ok=True)
            
            results = {
                'files_created': [],
                'levels_exported': [],
                'subtypes_exported': [],
                'total_words': 0,
                'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Export by levels (1-20)
            level_dir = os.path.join(wireword_dir, 'by_level')
            os.makedirs(level_dir, exist_ok=True)
            
            for level in range(1, 21):
                level_file = os.path.join(level_dir, f"level_{level:02d}.json")
                
                success, stats = self.export_to_wireword_format(
                    output_path=level_file,
                    difficulty_level=level,
                    include_without_guid=False,
                    include_unverified=True,
                    pretty_print=True
                )
                
                if success and stats and stats.total_entries > 0:
                    results['files_created'].append(level_file)
                    results['levels_exported'].append(level)
                    results['total_words'] += stats.total_entries
                    logger.info(f"Created wireword file for level {level}: {stats.total_entries} words")
            
            # Export by subtypes
            subtype_dir = os.path.join(wireword_dir, 'by_subtype')
            os.makedirs(subtype_dir, exist_ok=True)
            
            # Get all unique subtypes
            subtypes = session.query(Lemma.pos_subtype).filter(
                Lemma.pos_subtype.isnot(None),
                Lemma.pos_subtype != '',
                Lemma.guid.isnot(None)
            ).distinct().all()
            
            for subtype_tuple in subtypes:
                subtype = subtype_tuple[0]
                if subtype:
                    subtype_file = os.path.join(subtype_dir, f"{subtype}.json")
                    
                    success, stats = self.export_to_wireword_format(
                        output_path=subtype_file,
                        pos_subtype=subtype,
                        include_without_guid=False,
                        include_unverified=True,
                        pretty_print=True
                    )
                    
                    if success and stats and stats.total_entries > 0:
                        results['files_created'].append(subtype_file)
                        results['subtypes_exported'].append(subtype)
                        logger.info(f"Created wireword file for subtype '{subtype}': {stats.total_entries} words")
            
            # Export complete dataset
            complete_file = os.path.join(wireword_dir, 'complete.json')
            success, stats = self.export_to_wireword_format(
                output_path=complete_file,
                include_without_guid=False,
                include_unverified=True,
                pretty_print=True
            )
            
            if success and stats:
                results['files_created'].append(complete_file)
                logger.info(f"Created complete wireword file: {stats.total_entries} words")
            
            session.close()
            
            success = len(results['files_created']) > 0

            if success:
                logger.info(f"✅ WireWord directory export completed:")
                logger.info(f"   Files created: {len(results['files_created'])}")
                logger.info(f"   Levels exported: {len(results['levels_exported'])}")
                logger.info(f"   Subtypes exported: {len(results['subtypes_exported'])}")
                logger.info(f"   Output directory: {os.path.abspath(wireword_dir)}")
            else:
                logger.error("❌ No wireword files were created")
            
            return success, results
            
        except Exception as e:
            logger.error(f"Error exporting wireword directory: {e}")
            return False, {'error': str(e)}

    def export_all_text_files(self, lang_lt_dir: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Export text files for all available subtypes to lang_lt/generated/simple directory.
        
        Args:
            lang_lt_dir: Base lang_lt directory
            
        Returns:
            Tuple of (success flag, results dictionary)
        """
        logger.info("Starting text exports for all subtypes...")
        
        session = self.get_session()
        try:
            # Get all unique subtypes from the database
            from sqlalchemy import func
            
            subtypes_query = session.query(
                Lemma.pos_subtype,
                func.count(Lemma.id).label('count')
            ).filter(
                Lemma.pos_subtype.isnot(None),
                Lemma.pos_subtype != '',
                Lemma.lithuanian_translation.isnot(None),
                Lemma.lithuanian_translation != ''
            ).group_by(
                Lemma.pos_subtype
            ).order_by(
                Lemma.pos_subtype
            )
            
            subtypes_data = subtypes_query.all()
            
            if not subtypes_data:
                logger.warning("No subtypes found for text export")
                return False, {'subtypes_exported': [], 'files_created': []}
            
            logger.info(f"Found {len(subtypes_data)} subtypes to export")
            
            # Create the simple directory
            simple_dir = os.path.join(lang_lt_dir, 'simple')
            os.makedirs(simple_dir, exist_ok=True)
            
            results = {
                'subtypes_exported': [],
                'files_created': [],
                'failed_exports': [],
                'total_entries': 0
            }
            
            # Export each subtype
            for subtype, count in subtypes_data:
                logger.info(f"Exporting subtype '{subtype}' ({count} entries)...")
                
                # Create filename: subtype.txt
                filename = f"{subtype}.txt"
                output_path = os.path.join(simple_dir, filename)
                
                # Export this subtype
                success, stats = self.export_to_text(
                    output_path=output_path,
                    pos_subtype=subtype,
                    include_without_guid=False,  # Only include words with GUIDs
                    include_unverified=True      # Include unverified entries
                )
                
                if success and stats:
                    results['subtypes_exported'].append({
                        'subtype': subtype,
                        'count': stats.total_entries,
                        'entries_with_guids': stats.entries_with_guids,
                        'filename': filename
                    })
                    results['files_created'].append(output_path)
                    results['total_entries'] += stats.total_entries
                    logger.info(f"✅ Exported {stats.total_entries} entries for '{subtype}' to {filename}")
                else:
                    results['failed_exports'].append(subtype)
                    logger.error(f"❌ Failed to export subtype '{subtype}'")
            
            # Summary
            successful_count = len(results['subtypes_exported'])
            failed_count = len(results['failed_exports'])
            
            if successful_count > 0:
                logger.info(f"✅ Text export completed: {successful_count} subtypes exported, {results['total_entries']} total entries")
                logger.info(f"Files created in: {simple_dir}")
                
                if failed_count > 0:
                    logger.warning(f"⚠️  {failed_count} subtypes failed to export: {', '.join(results['failed_exports'])}")
                
                return True, results
            else:
                logger.error("❌ No subtypes were successfully exported")
                return False, results
                
        except Exception as e:
            logger.error(f"Error during text export: {e}")
            return False, {'error': str(e), 'subtypes_exported': [], 'files_created': []}
        finally:
            session.close()

    def export_all(
        self,
        json_path: str,
        lang_lt_dir: str,
        wireword_path: str = None,
        include_wireword_directory: bool = True,
        **json_kwargs
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Export to JSON, lang_lt, text, and WireWord formats.
        
        Args:
            json_path: Path for JSON export
            lang_lt_dir: Directory for lang_lt export
            wireword_path: Path for single WireWord format export (optional)
            include_wireword_directory: Whether to create wireword directory structure (default: True)
            **json_kwargs: Additional arguments for JSON export
            
        Returns:
            Tuple of (success flag, combined results dictionary)
        """
        logger.info("Starting full export...")
        
        json_success, json_stats = self.export_to_json(json_path, **json_kwargs)
        lang_lt_success, lang_lt_results = self.export_to_lang_lt(lang_lt_dir)
        
        # Export text files for all subtypes to lang_lt/generated/simple
        text_success, text_results = self.export_all_text_files(lang_lt_dir)
        
        # Export WireWord format if path provided
        wireword_success, wireword_stats = True, None
        if wireword_path:
            wireword_success, wireword_stats = self.export_to_wireword_format(wireword_path, **json_kwargs)
        
        # Export WireWord directory structure
        wireword_dir_success, wireword_dir_results = True, None
        if include_wireword_directory:
            wireword_dir_success, wireword_dir_results = self.export_wireword_directory(lang_lt_dir)
        
        results = {
            'json_export': {
                'success': json_success,
                'stats': json_stats,
                'path': json_path
            },
            'lang_lt_export': {
                'success': lang_lt_success,
                'results': lang_lt_results,
                'directory': lang_lt_dir
            },
            'text_export': {
                'success': text_success,
                'results': text_results,
                'directory': f"{lang_lt_dir}/simple"
            },
            'wireword_directory_export': {
                'success': wireword_dir_success,
                'results': wireword_dir_results,
                'directory': f"{lang_lt_dir}/wireword"
            },
            'overall_success': json_success and lang_lt_success and text_success and wireword_success and wireword_dir_success,
            'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        if wireword_path:
            results['wireword_export'] = {
                'success': wireword_success,
                'stats': wireword_stats,
                'path': wireword_path
            }
        
        # Update success tracking
        all_exports_successful = json_success and lang_lt_success and text_success and wireword_success and wireword_dir_success
        
        if all_exports_successful:
            logger.info("✅ Full export completed successfully!")
        else:
            failed_exports = []
            successful_exports = []
            
            if json_success:
                successful_exports.append("JSON")
            else:
                failed_exports.append("JSON")
                
            if lang_lt_success:
                successful_exports.append("lang_lt")
            else:
                failed_exports.append("lang_lt")
                
            if text_success:
                successful_exports.append("text")
            else:
                failed_exports.append("text")
                
            if wireword_path:
                if wireword_success:
                    successful_exports.append("WireWord")
                else:
                    failed_exports.append("WireWord")
            
            if include_wireword_directory:
                if wireword_dir_success:
                    successful_exports.append("WireWord Directory")
                else:
                    failed_exports.append("WireWord Directory")
            
            if len(failed_exports) == 0:
                logger.info("✅ All exports completed successfully!")
            elif len(successful_exports) == 0:
                logger.error("❌ All exports failed")
            else:
                logger.warning(f"⚠️  {', '.join(successful_exports)} export(s) succeeded, but {', '.join(failed_exports)} export(s) failed")
        
        return results['overall_success'], results

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
        session = self.get_session()
        try:
            # Get the language field to query
            language_column = getattr(Lemma, self.language_field)

            # Build the query for verbs
            query = session.query(Lemma)\
                .filter(Lemma.pos_type == 'verb')\
                .filter(language_column != None)\
                .filter(language_column != "")

            # Apply filters
            if not include_without_guid:
                query = query.filter(Lemma.guid != None)

            if not include_unverified:
                query = query.filter(Lemma.verified == True)

            if difficulty_level is not None:
                query = query.filter(Lemma.difficulty_level == difficulty_level)
                logger.info(f"Filtering by difficulty level: {difficulty_level}")

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
                # Get all derivative forms for this verb
                derivative_forms = session.query(DerivativeForm).filter(
                    DerivativeForm.lemma_id == lemma.id
                ).all()

                # Get base English and target language forms
                base_english = self.get_english_word_from_lemma(session, lemma)
                base_target = getattr(lemma, self.language_field)

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
                            form_level = max(lemma.difficulty_level or 1, 1)

                            # Apply tense-specific minimum levels for Lithuanian
                            if self.language == 'lt':
                                # Extract tense from grammatical_form (format: "1s_past", "3p-m_fut", etc.)
                                if '_' in form.grammatical_form:
                                    tense_suffix = form.grammatical_form.split('_')[-1]
                                    if tense_suffix == 'past':
                                        # Past tense minimum level is 7
                                        form_level = max(form_level, 7)
                                    elif tense_suffix == 'fut':
                                        # Future tense minimum level is 12
                                        form_level = max(form_level, 12)

                            # Try to find corresponding English conjugation in database
                            english_conjugation = session.query(DerivativeForm).filter(
                                DerivativeForm.lemma_id == lemma.id,
                                DerivativeForm.language_code == 'en',
                                DerivativeForm.grammatical_form == form.grammatical_form
                            ).first()

                            if english_conjugation:
                                # Use the stored English conjugation
                                english_label = english_conjugation.derivative_form_text
                            else:
                                # Generate readable English label for the form
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

                            grammatical_forms[form.grammatical_form] = gram_form

                # Create WireWord object
                wireword = {
                    'guid': lemma.guid,
                    'base_target': base_target,
                    'base_english': base_english,
                    'corpus': 'VERBS',
                    'group': format_subtype_display_name(lemma.pos_subtype or 'action'),
                    'level': lemma.difficulty_level or 1,
                    'word_type': 'verb'
                }

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
                tags = [lemma.pos_subtype or 'action', f"level_{lemma.difficulty_level or 1}"]
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
def export_trakaido_data(
    session, 
    difficulty_level: Optional[int] = None,
    pos_type: Optional[str] = None,
    limit: Optional[int] = None,
    include_without_guid: bool = False
) -> List[Dict[str, Any]]:
    """
    Legacy function for backward compatibility with database_to_json.py.
    
    Args:
        session: Database session
        difficulty_level: Filter by specific difficulty level (optional)
        pos_type: Filter by specific POS type (optional)
        limit: Limit number of results (optional)
        include_without_guid: Include lemmas without GUIDs (default: False)
        
    Returns:
        List of dictionaries with trakaido data
    """
    exporter = TrakaidoExporter()
    return exporter.query_trakaido_data(
        session=session,
        difficulty_level=difficulty_level,
        pos_type=pos_type,
        limit=limit,
        include_without_guid=include_without_guid
    )

def write_json_file(data: List[Dict[str, Any]], output_path: str) -> None:
    """
    Legacy function for backward compatibility with database_to_json.py.
    
    Args:
        data: List of dictionaries to export
        output_path: Path to write the JSON file
    """
    exporter = TrakaidoExporter()
    exporter.write_json_file(data, output_path, pretty_print=True)

def get_english_word_from_lemma(session, lemma: Lemma) -> Optional[str]:
    """
    Legacy function for backward compatibility with database_to_json.py.
    
    Args:
        session: Database session
        lemma: Lemma object
        
    Returns:
        English word string or None if not found
    """
    exporter = TrakaidoExporter()
    return exporter.get_english_word_from_lemma(session, lemma)
