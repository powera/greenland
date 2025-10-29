#!/usr/bin/env python3
"""
Bulk import verbs from verbs.py files to the database.

This script:
1. Loads verbs from data/trakaido_wordlists/lang_{code}/verbs.py
2. Adds each verb to the database with base infinitive form
3. Generates all conjugation forms using the existing conjugation data
4. Assigns levels and groups based on the verbs.py structure
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add the src directory to the path for imports
GREENLAND_SRC_PATH = '/Users/powera/repo/greenland/src'
sys.path.append(GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import (
    add_word_token,
    create_database_session,
)
from wordfreq.storage.models.schema import DerivativeForm, Lemma
from wordfreq.storage.models.enums import GrammaticalForm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Language-specific settings
LANGUAGE_CONFIGS = {
    'lt': {
        'name': 'Lithuanian',
        'verbs_path': '/Users/powera/repo/greenland/data/trakaido_wordlists/lang_lt',
        'translation_field': 'lithuanian_translation',
        'has_conjugations': True,
        'form_mapping': {
            # Present tense
            "1s_pres": "verb/lt_1s_pres",
            "2s_pres": "verb/lt_2s_pres",
            "3s-m_pres": "verb/lt_3s_m_pres",
            "3s-f_pres": "verb/lt_3s_f_pres",
            "1p_pres": "verb/lt_1p_pres",
            "2p_pres": "verb/lt_2p_pres",
            "3p-m_pres": "verb/lt_3p_m_pres",
            "3p-f_pres": "verb/lt_3p_f_pres",
            # Past tense
            "1s_past": "verb/lt_1s_past",
            "2s_past": "verb/lt_2s_past",
            "3s-m_past": "verb/lt_3s_m_past",
            "3s-f_past": "verb/lt_3s_f_past",
            "1p_past": "verb/lt_1p_past",
            "2p_past": "verb/lt_2p_past",
            "3p-m_past": "verb/lt_3p_m_past",
            "3p-f_past": "verb/lt_3p_f_past",
            # Future tense
            "1s_fut": "verb/lt_1s_fut",
            "2s_fut": "verb/lt_2s_fut",
            "3s-m_fut": "verb/lt_3s_m_fut",
            "3s-f_fut": "verb/lt_3s_f_fut",
            "1p_fut": "verb/lt_1p_fut",
            "2p_fut": "verb/lt_2p_fut",
            "3p-m_fut": "verb/lt_3p_m_fut",
            "3p-f_fut": "verb/lt_3p_f_fut",
        },
        'tense_mapping': {
            'present_tense': 'pres',
            'past_tense': 'past',
            'future': 'fut'
        }
    }
}


# Mapping of verb infinitives to groups (from verb_converter.py)
VERB_GROUPS = {
    # Basic Needs & Daily Life
    "valgyti": "Basic Needs & Daily Life",
    "gyventi": "Basic Needs & Daily Life",
    "dirbti": "Basic Needs & Daily Life",
    "gerti": "Basic Needs & Daily Life",
    "miegoti": "Basic Needs & Daily Life",
    "žaisti": "Basic Needs & Daily Life",

    # Learning & Knowledge
    "mokytis": "Learning & Knowledge",
    "mokyti": "Learning & Knowledge",
    "skaityti": "Learning & Knowledge",
    "rašyti": "Learning & Knowledge",
    "žinoti": "Learning & Knowledge",

    # Actions & Transactions
    "būti": "Actions & Transactions",
    "turėti": "Actions & Transactions",
    "gaminti": "Actions & Transactions",
    "pirkti": "Actions & Transactions",
    "duoti": "Actions & Transactions",
    "imti": "Actions & Transactions",

    # Mental & Emotional
    "mėgti": "Mental & Emotional",
    "norėti": "Mental & Emotional",
    "galėti": "Mental & Emotional",
    "kalbėti": "Mental & Emotional",

    # Sensory Perception
    "klausyti": "Sensory Perception",
    "matyti": "Sensory Perception",

    # Movement & Travel
    "eiti": "Movement & Travel",
    "važiuoti": "Movement & Travel",
    "bėgti": "Movement & Travel",
    "vykti": "Movement & Travel",
    "ateiti": "Movement & Travel",
    "grįžti": "Movement & Travel",
}


# Default level mapping (from levels.py patterns)
GROUP_DEFAULT_LEVELS = {
    "Basic Needs & Daily Life": 6,
    "Learning & Knowledge": 8,
    "Actions & Transactions": 6,
    "Mental & Emotional": 7,
    "Sensory Perception": 9,
    "Movement & Travel": 10,
}


def load_verbs_from_file(language: str) -> Dict:
    """Load verbs from the language-specific verbs.py file."""
    config = LANGUAGE_CONFIGS.get(language)
    if not config:
        raise ValueError(f"Unsupported language: {language}")

    verbs_dir = config['verbs_path']
    sys.path.insert(0, verbs_dir)

    try:
        from verbs import verbs_new
        return verbs_new
    except ImportError as e:
        logger.error(f"Could not import verbs.py from {verbs_dir}: {e}")
        raise


def generate_guid(prefix: str, existing_numbers: List[int]) -> str:
    """Generate a unique GUID."""
    next_number = 1
    while next_number in existing_numbers:
        next_number += 1
    return f"{prefix}_{next_number:03d}"


def import_verb(
    verb_infinitive: str,
    verb_data: Dict,
    language: str,
    session,
    existing_guids: List[int],
    dry_run: bool = False
) -> Tuple[bool, str]:
    """
    Import a single verb into the database.

    Args:
        verb_infinitive: The infinitive form in target language
        verb_data: Dictionary with verb conjugations and English translation
        language: Language code (lt, zh, ko, fr)
        session: Database session
        existing_guids: List of existing GUID numbers
        dry_run: If True, don't actually save to database

    Returns:
        Tuple of (success, message)
    """
    config = LANGUAGE_CONFIGS[language]

    # Get English translation
    english_verb = verb_data.get('english', '')
    if not english_verb:
        return False, f"No English translation for {verb_infinitive}"

    # Remove "to " prefix if present
    if english_verb.startswith("to "):
        english_verb = english_verb[3:]

    # Check if verb already exists
    existing = session.query(Lemma).filter(
        Lemma.lemma_text.ilike(english_verb),
        Lemma.pos_type == 'verb'
    ).first()

    if existing:
        return False, f"Verb '{english_verb}' already exists with GUID {existing.guid}"

    # Get group and level
    group = VERB_GROUPS.get(verb_infinitive, "Actions & Transactions")
    level = GROUP_DEFAULT_LEVELS.get(group, 6)

    # Map group to pos_subtype
    subtype_mapping = {
        "Basic Needs & Daily Life": "action",
        "Learning & Knowledge": "mental",
        "Actions & Transactions": "action",
        "Mental & Emotional": "mental",
        "Sensory Perception": "mental",
        "Movement & Travel": "motion",
    }
    pos_subtype = subtype_mapping.get(group, "action")

    # Generate GUID
    guid = generate_guid("V01", existing_guids)
    existing_guids.append(int(guid.split('_')[1]))

    if dry_run:
        return True, f"[DRY RUN] Would import {english_verb} ({verb_infinitive}) with GUID {guid}, level {level}"

    # Create lemma
    lemma = Lemma(
        lemma_text=english_verb,
        definition_text=f"{english_verb} (verb)",
        pos_type='verb',
        pos_subtype=pos_subtype,
        guid=guid,
        difficulty_level=level,
        lithuanian_translation=verb_infinitive if language == 'lt' else None,
        confidence=0.9,
        verified=True
    )

    session.add(lemma)
    session.flush()  # Get the ID

    # Create English derivative form (infinitive)
    english_token = add_word_token(session, english_verb, 'en')
    english_form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=english_verb,
        word_token_id=english_token.id,
        language_code='en',
        grammatical_form='infinitive',
        is_base_form=True,
        verified=True
    )
    session.add(english_form)

    # Create target language derivative form (infinitive)
    target_token = add_word_token(session, verb_infinitive, language)
    target_form = DerivativeForm(
        lemma_id=lemma.id,
        derivative_form_text=verb_infinitive,
        word_token_id=target_token.id,
        language_code=language,
        grammatical_form='infinitive',
        is_base_form=True,
        verified=True
    )
    session.add(target_form)

    # Add conjugation forms if available
    forms_added = 0
    if config['has_conjugations']:
        form_mapping = config['form_mapping']
        tense_mapping = config['tense_mapping']

        for tense_key, tense_data in verb_data.items():
            if tense_key == 'english':
                continue  # Skip the english field

            # Map tense to suffix
            tense_suffix = tense_mapping.get(tense_key)
            if not tense_suffix:
                continue

            for person_key, person_data in tense_data.items():
                # Build the form key
                form_key = f"{person_key}_{tense_suffix}"
                grammatical_form = form_mapping.get(form_key)

                if not grammatical_form:
                    logger.warning(f"No mapping for form key: {form_key}")
                    continue

                # Get the conjugated form text for target language
                target_text = person_data.get(config['name'].lower())
                if not target_text:
                    continue

                # Create derivative form for target language conjugation
                conj_token = add_word_token(session, target_text, language)
                conj_form = DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text=target_text,
                    word_token_id=conj_token.id,
                    language_code=language,
                    grammatical_form=grammatical_form,
                    is_base_form=False,
                    verified=True
                )
                session.add(conj_form)
                forms_added += 1

                # Also store English conjugation if available
                english_text = person_data.get('english')
                if english_text:
                    english_token = add_word_token(session, english_text, 'en')
                    english_conj_form = DerivativeForm(
                        lemma_id=lemma.id,
                        derivative_form_text=english_text,
                        word_token_id=english_token.id,
                        language_code='en',
                        grammatical_form=grammatical_form,
                        is_base_form=False,
                        verified=True
                    )
                    session.add(english_conj_form)
                    forms_added += 1

    session.commit()

    return True, f"✅ Imported {english_verb} ({verb_infinitive}) with GUID {guid}, {forms_added} conjugation forms"


def bulk_import_verbs(
    language: str = 'lt',
    limit: int = None,
    dry_run: bool = False,
    db_path: str = None
) -> Dict:
    """
    Bulk import verbs from verbs.py to database.

    Args:
        language: Language code (default: lt)
        limit: Maximum number of verbs to import
        dry_run: If True, don't actually save to database
        db_path: Database path (uses default if None)

    Returns:
        Dictionary with import results
    """
    if language not in LANGUAGE_CONFIGS:
        raise ValueError(f"Unsupported language: {language}. Supported: {', '.join(LANGUAGE_CONFIGS.keys())}")

    logger.info(f"Starting bulk verb import for {LANGUAGE_CONFIGS[language]['name']}...")

    # Load verbs from file
    try:
        verbs = load_verbs_from_file(language)
        logger.info(f"Loaded {len(verbs)} verbs from verbs.py")
    except Exception as e:
        logger.error(f"Failed to load verbs: {e}")
        return {'success': False, 'error': str(e)}

    # Get database session
    db_path = db_path or constants.WORDFREQ_DB_PATH
    session = create_database_session(db_path)

    # Get existing GUIDs
    existing_guids = session.query(Lemma.guid).filter(
        Lemma.guid.like("V01_%")
    ).all()

    existing_numbers = []
    for guid_tuple in existing_guids:
        guid = guid_tuple[0]
        if guid and '_' in guid:
            try:
                number = int(guid.split('_')[1])
                existing_numbers.append(number)
            except (ValueError, IndexError):
                continue

    # Import verbs
    results = {
        'total_verbs': len(verbs),
        'imported': [],
        'skipped': [],
        'failed': []
    }

    verb_list = list(verbs.items())
    if limit:
        verb_list = verb_list[:limit]

    for verb_infinitive, verb_data in verb_list:
        try:
            success, message = import_verb(
                verb_infinitive,
                verb_data,
                language,
                session,
                existing_numbers,
                dry_run
            )

            if success:
                results['imported'].append(verb_infinitive)
                logger.info(message)
            else:
                results['skipped'].append(verb_infinitive)
                logger.warning(message)

        except Exception as e:
            results['failed'].append((verb_infinitive, str(e)))
            logger.error(f"Failed to import {verb_infinitive}: {e}")
            session.rollback()

    session.close()

    # Print summary
    logger.info("=" * 80)
    logger.info("BULK IMPORT SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total verbs in file: {results['total_verbs']}")
    logger.info(f"Successfully imported: {len(results['imported'])}")
    logger.info(f"Skipped (already exist): {len(results['skipped'])}")
    logger.info(f"Failed: {len(results['failed'])}")

    if results['failed']:
        logger.error("\nFailed imports:")
        for verb, error in results['failed']:
            logger.error(f"  {verb}: {error}")

    results['success'] = True
    return results


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Bulk import verbs from verbs.py to database"
    )
    parser.add_argument('--language', choices=['lt'], default='lt',
                       help='Language code (default: lt)')
    parser.add_argument('--limit', type=int,
                       help='Limit number of verbs to import')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be imported without saving')
    parser.add_argument('--db-path', help='Database path (uses default if not specified)')

    args = parser.parse_args()

    results = bulk_import_verbs(
        language=args.language,
        limit=args.limit,
        dry_run=args.dry_run,
        db_path=args.db_path
    )

    if not results.get('success'):
        sys.exit(1)


if __name__ == '__main__':
    main()
