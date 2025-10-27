#!/usr/bin/env python3
"""
Vovere - Data Import Agent

This agent runs autonomously to import trakaido vocabulary data from JSON exports
into the wordfreq database.

"Vovere" means "squirrel" in Lithuanian - gathering and storing things for later!
"""

import argparse
import logging
import sys
import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import (
    create_database_session,
    get_word_token_by_text,
    add_lemma,
    add_derivative_form,
    update_lemma_translation,
    add_alternative_form
)
from wordfreq.storage.models.schema import WordToken, Lemma, DerivativeForm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Alternative forms mapping
ENGLISH_ALTERNATIVE_MAP = {
    "bicycle": ["bike"],
    "car": ["automobile"],
    "eyeglasses": ["glasses", "spectacles"],
    "telephone": ["phone"],
    "television": ["TV"],
    "refrigerator": ["fridge"],
    "motorcycle": ["motorbike"],
    "airplane": ["plane"],
    "photograph": ["photo"],
    "smartphone": ["phone", "mobile"],
    "laptop": ["notebook"],
    "computer": ["PC"],
    "fire station": ["firehouse"],
    "police officer": ["policeman", "policewoman", "cop"],
    "firefighter": ["fireman"],
    "veterinarian": ["vet"],
    "monitor (computer)": ["screen"],
    "chicken meat": ["chicken"],
}


class VovereAgent:
    """Agent for importing vocabulary data from JSON exports."""

    def __init__(self, db_path: str = None, debug: bool = False):
        """
        Initialize the Vovere agent.

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

    @staticmethod
    def clean_english_word(english_word: str) -> tuple[str, bool]:
        """
        Clean English word by removing parenthetical information.

        Examples:
            "orange (fruit)" -> ("orange", True)
            "cousin (m)" -> ("cousin", True)
            "simple" -> ("simple", False)

        Args:
            english_word: The English word potentially containing parenthetical info

        Returns:
            tuple: (cleaned_word, has_parentheses)
        """
        has_parentheses = bool(re.search(r'\s*\([^)]+\)', english_word))
        cleaned = re.sub(r'\s*\([^)]+\)', '', english_word).strip()
        return cleaned, has_parentheses

    def validate_json_data(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate JSON data structure.

        Args:
            data: List of dictionaries with vocabulary data

        Returns:
            Dictionary with validation results
        """
        logger.info("Validating JSON data structure...")

        if not isinstance(data, list):
            return {
                'is_valid': False,
                'errors': [f"Expected JSON to contain a list, got {type(data)}"]
            }

        required_fields = ["English", "Lithuanian", "GUID", "POS", "subtype"]
        valid_pos_types = {
            "noun", "verb", "adjective", "adverb", "pronoun",
            "preposition", "conjunction", "interjection", "determiner",
            "article", "numeral", "auxiliary", "modal"
        }

        errors = []
        warnings = []

        for i, entry in enumerate(data):
            if not isinstance(entry, dict):
                errors.append(f"Entry {i} is not a dictionary: {entry}")
                continue

            # Check required fields
            missing_fields = [field for field in required_fields if field not in entry]
            if missing_fields:
                errors.append(f"Entry {i} missing required fields: {missing_fields}")
                continue

            # Validate POS type
            pos_type = entry["POS"].lower()
            if pos_type not in valid_pos_types:
                errors.append(
                    f"Entry {i} has invalid POS type '{entry['POS']}'. "
                    f"Valid types: {', '.join(sorted(valid_pos_types))}"
                )

            # Check for empty values
            if not entry["English"] or not entry["English"].strip():
                errors.append(f"Entry {i} has empty English field")
            if not entry["Lithuanian"] or not entry["Lithuanian"].strip():
                errors.append(f"Entry {i} has empty Lithuanian field")
            if not entry["GUID"] or not entry["GUID"].strip():
                errors.append(f"Entry {i} has empty GUID field")

            # Warn if trakaido_level is present (it shouldn't be in new format)
            if "trakaido_level" in entry:
                warnings.append(
                    f"Entry {i} contains 'trakaido_level' field which should be in a separate file"
                )

        result = {
            'is_valid': len(errors) == 0,
            'entry_count': len(data),
            'errors': errors,
            'warnings': warnings
        }

        logger.info(f"Validation complete: {len(errors)} errors, {len(warnings)} warnings")
        return result

    def load_json_file(self, json_path: str) -> Dict[str, Any]:
        """
        Load and validate JSON file.

        Args:
            json_path: Path to JSON file

        Returns:
            Dictionary with load results and data
        """
        logger.info(f"Loading JSON file: {json_path}")

        if not os.path.exists(json_path):
            return {
                'success': False,
                'error': f"File not found: {json_path}"
            }

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return {
                'success': False,
                'error': f"Invalid JSON: {e}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to read file: {e}"
            }

        # Validate the data
        validation = self.validate_json_data(data)

        result = {
            'success': validation['is_valid'],
            'json_path': json_path,
            'entry_count': validation['entry_count'],
            'validation': validation
        }

        if validation['is_valid']:
            result['data'] = data
            logger.info(f"Successfully loaded {len(data)} entries")
        else:
            logger.error(f"JSON validation failed with {len(validation['errors'])} errors")

        return result

    def find_or_create_lemma(
        self,
        session,
        english_word: str,
        lithuanian_word: str,
        guid: str,
        pos_type: str,
        pos_subtype: str,
        difficulty_level: Optional[int] = None
    ) -> Optional[Lemma]:
        """
        Find existing lemma or create new one.

        Args:
            session: Database session
            english_word: English word (may contain parenthetical info)
            lithuanian_word: Lithuanian translation
            guid: Global unique identifier
            pos_type: Part of speech
            pos_subtype: POS subtype
            difficulty_level: Optional difficulty level (1-20)

        Returns:
            Lemma object or None if creation failed
        """
        # Clean the English word
        clean_english, has_parentheses = self.clean_english_word(english_word)
        clean_english = clean_english.strip().lower()

        # Store original form in notes if parentheses were present
        notes = f"Original form: {english_word}" if has_parentheses else None

        # Normalize POS
        pos_type = pos_type.lower()

        # Step 1: Look for existing lemma with matching GUID
        existing_lemma = session.query(Lemma).filter(Lemma.guid == guid).first()

        if existing_lemma:
            # Update existing lemma
            updated = False

            if existing_lemma.lemma_text != clean_english:
                logger.debug(f"Updating lemma text from '{existing_lemma.lemma_text}' to '{clean_english}'")
                existing_lemma.lemma_text = clean_english
                updated = True

            if existing_lemma.lithuanian_translation != lithuanian_word:
                logger.debug(f"Updating Lithuanian translation from '{existing_lemma.lithuanian_translation}' to '{lithuanian_word}'")
                existing_lemma.lithuanian_translation = lithuanian_word
                updated = True

            if existing_lemma.pos_type != pos_type:
                logger.debug(f"Updating POS type from '{existing_lemma.pos_type}' to '{pos_type}'")
                existing_lemma.pos_type = pos_type
                updated = True

            if existing_lemma.pos_subtype != pos_subtype:
                logger.debug(f"Updating POS subtype from '{existing_lemma.pos_subtype}' to '{pos_subtype}'")
                existing_lemma.pos_subtype = pos_subtype
                updated = True

            if difficulty_level is not None and existing_lemma.difficulty_level != difficulty_level:
                logger.debug(f"Updating difficulty level from {existing_lemma.difficulty_level} to {difficulty_level}")
                existing_lemma.difficulty_level = difficulty_level
                updated = True

            if notes and not existing_lemma.notes:
                existing_lemma.notes = notes
                updated = True

            if updated:
                session.commit()
                logger.info(f"Updated existing lemma: {guid}")

            return existing_lemma

        # Step 2: Check for existing lemma with same text and Lithuanian translation (but no GUID)
        existing_lemma = session.query(Lemma)\
            .filter(Lemma.lemma_text == clean_english)\
            .filter(Lemma.lithuanian_translation == lithuanian_word)\
            .first()

        if existing_lemma:
            # Update with GUID
            existing_lemma.guid = guid
            existing_lemma.pos_type = pos_type
            existing_lemma.pos_subtype = pos_subtype
            if difficulty_level is not None:
                existing_lemma.difficulty_level = difficulty_level
            if notes and not existing_lemma.notes:
                existing_lemma.notes = notes
            session.commit()
            logger.info(f"Updated existing lemma with GUID: {guid}")
            return existing_lemma

        # Step 3: Check if we have a word token for frequency data
        word_token = get_word_token_by_text(session, clean_english, "en")

        # Step 4: Create new lemma
        try:
            lemma = add_lemma(
                session=session,
                lemma_text=clean_english,
                definition_text=f"Lithuanian: {lithuanian_word}",
                pos_type=pos_type,
                pos_subtype=pos_subtype,
                difficulty_level=difficulty_level,
                frequency_rank=word_token.frequency_rank if word_token else None,
                lithuanian_translation=lithuanian_word,
                notes=notes,
                auto_generate_guid=False
            )

            # Set the GUID
            lemma.guid = guid
            session.commit()

            # Add English derivative form
            add_derivative_form(
                session=session,
                lemma=lemma,
                derivative_form_text=clean_english,
                language_code="en",
                grammatical_form="singular" if pos_type == "noun" else "base_form",
                word_token=word_token,
                is_base_form=True
            )

            logger.info(f"Created new lemma: {guid} ({english_word})")
            return lemma

        except Exception as e:
            logger.error(f"Error creating lemma for {english_word}: {e}")
            return None

    def create_alternatives_for_lemma(
        self,
        session,
        lemma: Lemma,
        english_word: str
    ) -> int:
        """
        Create alternative forms for a lemma.

        Args:
            session: Database session
            lemma: The lemma to create alternatives for
            english_word: The original English word (cleaned)

        Returns:
            Number of alternatives created
        """
        alternatives_created = 0

        if english_word not in ENGLISH_ALTERNATIVE_MAP:
            return 0

        alternatives = ENGLISH_ALTERNATIVE_MAP[english_word]

        for alternative in alternatives:
            # Determine the grammatical form
            if alternative in ["TV", "PC"]:
                grammatical_form = "abbreviation"
                explanation = f"Abbreviation for {english_word}"
            elif alternative == "spectacles":
                grammatical_form = "archaic"
                explanation = f"Archaic term for {english_word}"
            else:
                grammatical_form = "informal"
                explanation = f"Informal term for {english_word}"

            try:
                # Try to find the word token for the alternative
                alternative_word_token = get_word_token_by_text(session, alternative, "en")

                # Create the alternative form
                add_alternative_form(
                    session=session,
                    lemma=lemma,
                    alternative_text=alternative,
                    language_code="en",
                    alternative_type=grammatical_form,
                    explanation=explanation,
                    word_token=alternative_word_token
                )

                alternatives_created += 1
                logger.debug(f"Added alternative: {alternative} for {english_word}")

            except Exception as e:
                logger.warning(f"Failed to create alternative '{alternative}' for {english_word}: {e}")

        return alternatives_created

    def import_data(
        self,
        json_path: str,
        difficulty_levels: Optional[Dict[str, int]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Import vocabulary data from JSON file.

        Args:
            json_path: Path to JSON file
            difficulty_levels: Optional dict mapping GUID -> difficulty_level
            dry_run: If True, validate without importing

        Returns:
            Dictionary with import results
        """
        logger.info(f"Starting import (dry_run={dry_run})...")
        start_time = datetime.now()

        # Load and validate JSON
        load_result = self.load_json_file(json_path)
        if not load_result['success']:
            return {
                'success': False,
                'error': load_result.get('error', 'Unknown error'),
                'json_path': json_path
            }

        data = load_result['data']

        result = {
            'timestamp': start_time.isoformat(),
            'json_path': json_path,
            'dry_run': dry_run,
            'total_entries': len(data),
            'validation': load_result['validation']
        }

        if dry_run:
            result['message'] = f'Would import {len(data)} entries'
            result['success'] = True
            return result

        # Perform actual import
        session = self.get_session()
        try:
            successful = 0
            failed = 0
            updated = 0
            created = 0
            alternatives_created = 0

            for i, entry in enumerate(data):
                english_word = entry["English"]
                lithuanian_word = entry["Lithuanian"]
                guid = entry["GUID"]
                pos_type = entry["POS"]
                pos_subtype = entry["subtype"]

                # Get difficulty level from separate mapping if provided
                difficulty_level = difficulty_levels.get(guid) if difficulty_levels else None

                # Check if lemma exists
                existing = session.query(Lemma).filter(Lemma.guid == guid).first()

                # Find or create lemma
                lemma = self.find_or_create_lemma(
                    session=session,
                    english_word=english_word,
                    lithuanian_word=lithuanian_word,
                    guid=guid,
                    pos_type=pos_type,
                    pos_subtype=pos_subtype,
                    difficulty_level=difficulty_level
                )

                if lemma:
                    successful += 1
                    if existing:
                        updated += 1
                    else:
                        created += 1

                    # Create alternatives
                    clean_english, _ = self.clean_english_word(english_word)
                    clean_english = clean_english.strip().lower()
                    alts = self.create_alternatives_for_lemma(session, lemma, clean_english)
                    alternatives_created += alts
                else:
                    failed += 1
                    logger.error(f"Failed to import: {english_word} (GUID: {guid})")

                # Progress indicator
                if (i + 1) % 100 == 0:
                    logger.info(f"Progress: {i + 1}/{len(data)} entries processed...")

            # Commit all changes
            session.commit()

            result['success'] = True
            result['successful_imports'] = successful
            result['created'] = created
            result['updated'] = updated
            result['failed_imports'] = failed
            result['alternatives_created'] = alternatives_created

            logger.info(
                f"Import complete: {successful}/{len(data)} successful "
                f"({created} created, {updated} updated, {failed} failed)"
            )

        except Exception as e:
            logger.error(f"Import failed: {e}")
            session.rollback()
            result['success'] = False
            result['error'] = str(e)
        finally:
            session.close()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        result['duration_seconds'] = duration

        return result

    def check_database_state(self) -> Dict[str, Any]:
        """
        Check current database state.

        Returns:
            Dictionary with database statistics
        """
        logger.info("Checking database state...")

        session = self.get_session()
        try:
            total_lemmas = session.query(Lemma).count()
            lemmas_with_guids = session.query(Lemma).filter(Lemma.guid.isnot(None)).count()
            lemmas_with_lithuanian = session.query(Lemma).filter(
                Lemma.lithuanian_translation.isnot(None),
                Lemma.lithuanian_translation != ''
            ).count()
            lemmas_with_difficulty = session.query(Lemma).filter(
                Lemma.difficulty_level.isnot(None)
            ).count()
            derivative_forms = session.query(DerivativeForm).count()

            result = {
                'total_lemmas': total_lemmas,
                'lemmas_with_guids': lemmas_with_guids,
                'lemmas_with_lithuanian': lemmas_with_lithuanian,
                'lemmas_with_difficulty': lemmas_with_difficulty,
                'derivative_forms': derivative_forms
            }

            logger.info(f"Database state: {total_lemmas} lemmas, {lemmas_with_guids} with GUIDs")
            return result

        except Exception as e:
            logger.error(f"Error checking database state: {e}")
            return {'error': str(e)}
        finally:
            session.close()


def main():
    """Main entry point for the vovere agent."""
    parser = argparse.ArgumentParser(
        description="Vovere - Data Import Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check database state
  python vovere.py --check

  # Import from default file (dry run)
  python vovere.py --import --dry-run

  # Import from specific file
  python vovere.py --import-file /path/to/exported_nouns.json

  # Import with separate difficulty levels file
  python vovere.py --import-file exported_nouns.json --levels trakaido_levels.json
        """
    )

    parser.add_argument('--db-path', help='Database path (uses default if not specified)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--output', help='Output JSON file for report')
    parser.add_argument('--dry-run', action='store_true',
                       help='Validate without importing')

    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--check', action='store_true',
                           help='Check database state')
    mode_group.add_argument('--import-file', metavar='JSON_FILE', nargs='?',
                           const='src/wordfreq/trakaido/exported_nouns.json',
                           help='Import from JSON file (default: src/wordfreq/trakaido/exported_nouns.json)')

    # Import options
    parser.add_argument('--levels', metavar='LEVELS_FILE',
                       help='JSON file with difficulty levels (GUID -> level mapping)')

    args = parser.parse_args()

    agent = VovereAgent(db_path=args.db_path, debug=args.debug)

    if args.check:
        result = agent.check_database_state()

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        if 'error' not in result:
            print(f"\nDatabase State:")
            print(f"  Total lemmas: {result['total_lemmas']}")
            print(f"  Lemmas with GUIDs: {result['lemmas_with_guids']}")
            print(f"  Lemmas with Lithuanian: {result['lemmas_with_lithuanian']}")
            print(f"  Lemmas with difficulty levels: {result['lemmas_with_difficulty']}")
            print(f"  Derivative forms: {result['derivative_forms']}")

    elif args.import_file:
        # Load difficulty levels if provided
        difficulty_levels = None
        if args.levels:
            try:
                with open(args.levels, 'r', encoding='utf-8') as f:
                    difficulty_levels = json.load(f)
                logger.info(f"Loaded difficulty levels for {len(difficulty_levels)} GUIDs")
            except Exception as e:
                logger.error(f"Failed to load difficulty levels: {e}")
                return

        result = agent.import_data(
            json_path=args.import_file,
            difficulty_levels=difficulty_levels,
            dry_run=args.dry_run
        )

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

        if result.get('success'):
            if args.dry_run:
                print(f"\nDry run: {result['message']}")
            else:
                print(f"\nImport complete:")
                print(f"  Successful: {result['successful_imports']}/{result['total_entries']}")
                print(f"  Created: {result['created']}")
                print(f"  Updated: {result['updated']}")
                print(f"  Failed: {result['failed_imports']}")
                print(f"  Alternatives created: {result['alternatives_created']}")
                print(f"  Duration: {result['duration_seconds']:.2f}s")
        else:
            error_msg = result.get('error', 'Unknown error')
            print(f"\nImport failed: {error_msg}")

    else:
        # Default: show help
        parser.print_help()


if __name__ == '__main__':
    main()
