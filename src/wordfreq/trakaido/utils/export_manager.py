
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
from wordfreq.trakaido.dict_generator import (
    generate_structure_file,
    generate_dictionary_file
)

from .data_models import ExportStats, create_export_stats
from .text_rendering import format_subtype_display_name

# Configure logging
logger = logging.getLogger(__name__)


class TrakaidoExporter:
    """Main class for exporting trakaido data in various formats."""
    
    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the TrakaidoExporter.
        
        Args:
            db_path: Database path (uses default if None)
            debug: Enable debug logging
        """
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        
        if debug:
            logger.setLevel(logging.DEBUG)
    
    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)
    
    def get_english_word_from_lemma(self, session, lemma: Lemma) -> Optional[str]:
        """
        Get the primary English word for a lemma from its derivative forms.
        
        Args:
            session: Database session
            lemma: Lemma object
            
        Returns:
            English word string or None if not found
        """
        # Look for English derivative forms for this lemma
        english_forms = session.query(DerivativeForm)\
            .filter(DerivativeForm.lemma_id == lemma.id)\
            .filter(DerivativeForm.language_code == "en")\
            .filter(DerivativeForm.is_base_form == True)\
            .all()
        
        if english_forms:
            # Return the first base form
            return english_forms[0].derivative_form_text
        
        # If no base form found, look for any English derivative form
        any_english_forms = session.query(DerivativeForm)\
            .filter(DerivativeForm.lemma_id == lemma.id)\
            .filter(DerivativeForm.language_code == "en")\
            .all()
        
        if any_english_forms:
            # Return the first available form
            return any_english_forms[0].derivative_form_text
        
        # Fallback to lemma text if no derivative forms found
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
        logger.info("Querying database for trakaido data...")
        
        # Build the query
        query = session.query(Lemma)\
            .filter(Lemma.lithuanian_translation != None)\
            .filter(Lemma.lithuanian_translation != "")
        
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
            
            # Create the export entry with standardized key names
            entry = {
                "English": english_word,
                "Lithuanian": lemma.lithuanian_translation,
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
                lithuanian_alternatives = []
                english_synonyms = []
                lithuanian_synonyms = []
                grammatical_forms = {}
                
                for form in derivative_forms:
                    if form.is_base_form:
                        # Skip base forms as they're already in base_lithuanian/base_english
                        continue
                    
                    # Handle different types of derivative forms
                    if form.language_code == 'en':
                        if form.grammatical_form == 'alternative_form':
                            english_alternatives.append(form.derivative_form_text)
                        elif form.grammatical_form == 'synonym':
                            english_synonyms.append(form.derivative_form_text)
                    elif form.language_code == 'lt':
                        if form.grammatical_form == 'alternative_form':
                            lithuanian_alternatives.append(form.derivative_form_text)
                        elif form.grammatical_form == 'synonym':
                            lithuanian_synonyms.append(form.derivative_form_text)
                        elif form.grammatical_form == 'plural_nominative':
                            # Add plural nominative form with appropriate level (minimum level 4)
                            form_level = max(entry['trakaido_level'], 4)
                            grammatical_forms[form.grammatical_form] = {
                                "level": form_level,
                                "lithuanian": form.derivative_form_text,
                                "english": f"{entry['English']} (plural)"  # Simple plural English form
                            }
                        elif form.grammatical_form in ['singular_accusative', 'plural_accusative']:
                            # Add accusative forms with appropriate level (minimum level 9)
                            form_level = max(entry['trakaido_level'], 9)
                            english_suffix = " (accusative singular)" if form.grammatical_form == 'singular_accusative' else " (accusative plural)"
                            grammatical_forms[form.grammatical_form] = {
                                "level": form_level,
                                "lithuanian": form.derivative_form_text,
                                "english": f"{entry['English']}{english_suffix}"
                            }
                
                # Get corpus assignment for this entry
                corpus_key = (entry['trakaido_level'], entry['subtype'])
                assigned_corpus = corpus_assignments.get(corpus_key, 'Trakaido')
                
                # Create WireWord object
                wireword = {
                    'guid': entry['GUID'],
                    'base_lithuanian': entry['Lithuanian'],
                    'base_english': entry['English'],
                    'corpus': assigned_corpus,
                    'group': format_subtype_display_name(entry['subtype']),
                    'level': entry['trakaido_level'],
                    'word_type': self._normalize_pos_type(entry['POS'])
                }
                
                # Add optional fields
                if english_alternatives:
                    wireword['english_alternatives'] = english_alternatives
                if lithuanian_alternatives:
                    wireword['lithuanian_alternatives'] = lithuanian_alternatives
                if english_synonyms:
                    wireword['english_synonyms'] = english_synonyms
                if lithuanian_synonyms:
                    wireword['lithuanian_synonyms'] = lithuanian_synonyms
                
                # Add grammatical forms (for both verbs and nouns with declensions)
                if grammatical_forms:
                    wireword['grammatical_forms'] = grammatical_forms
                
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
