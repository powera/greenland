#!/usr/bin/env python3

"""
Batch script to generate Lithuanian noun declensions for all nouns in the database.

This script:
1. Queries all lemmas with Lithuanian translations that are nouns
2. For each noun, generates all 14 declension forms (7 cases × 2 numbers)
3. Stores the forms as derivative_forms in the database
"""

import argparse
import logging
import time
import sys
from typing import Dict, List

from wordfreq.translation.client import LinguisticClient
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.storage.connection_pool import get_session
import constants

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Mapping from form field names to GrammaticalForm enum values
FORM_MAPPING = {
    "nominative_singular": GrammaticalForm.NOUN_LT_NOMINATIVE_SINGULAR,
    "genitive_singular": GrammaticalForm.NOUN_LT_GENITIVE_SINGULAR,
    "dative_singular": GrammaticalForm.NOUN_LT_DATIVE_SINGULAR,
    "accusative_singular": GrammaticalForm.NOUN_LT_ACCUSATIVE_SINGULAR,
    "instrumental_singular": GrammaticalForm.NOUN_LT_INSTRUMENTAL_SINGULAR,
    "locative_singular": GrammaticalForm.NOUN_LT_LOCATIVE_SINGULAR,
    "vocative_singular": GrammaticalForm.NOUN_LT_VOCATIVE_SINGULAR,
    "nominative_plural": GrammaticalForm.NOUN_LT_NOMINATIVE_PLURAL,
    "genitive_plural": GrammaticalForm.NOUN_LT_GENITIVE_PLURAL,
    "dative_plural": GrammaticalForm.NOUN_LT_DATIVE_PLURAL,
    "accusative_plural": GrammaticalForm.NOUN_LT_ACCUSATIVE_PLURAL,
    "instrumental_plural": GrammaticalForm.NOUN_LT_INSTRUMENTAL_PLURAL,
    "locative_plural": GrammaticalForm.NOUN_LT_LOCATIVE_PLURAL,
    "vocative_plural": GrammaticalForm.NOUN_LT_VOCATIVE_PLURAL,
}


def get_lithuanian_noun_lemmas(db_path: str, limit: int = None) -> List[Dict]:
    """
    Get all lemmas that are nouns with Lithuanian translations.

    Args:
        db_path: Path to the database
        limit: Optional limit on number of lemmas to return

    Returns:
        List of dictionaries with lemma information
    """
    session = get_session(db_path)

    query = session.query(linguistic_db.Lemma).filter(
        linguistic_db.Lemma.pos_type == 'noun',
        linguistic_db.Lemma.lithuanian_translation.isnot(None),
        linguistic_db.Lemma.lithuanian_translation != ''
    ).order_by(linguistic_db.Lemma.frequency_rank)

    if limit:
        query = query.limit(limit)

    lemmas = query.all()

    result = []
    for lemma in lemmas:
        result.append({
            'id': lemma.id,
            'english': lemma.lemma_text,
            'lithuanian': lemma.lithuanian_translation,
            'pos_subtype': lemma.pos_subtype,
            'frequency_rank': lemma.frequency_rank
        })

    return result


def process_lemma_declensions(client: LinguisticClient, lemma_id: int, db_path: str, source: str = 'llm') -> bool:
    """
    Process a single lemma to generate and store all its declensions.

    Args:
        client: LinguisticClient instance (only used if source='llm')
        lemma_id: ID of the lemma to process
        db_path: Path to the database
        source: Source for noun forms - 'llm' or 'wiki'

    Returns:
        Success flag
    """
    session = get_session(db_path)

    try:
        # Get the lemma
        lemma = session.query(linguistic_db.Lemma).filter(
            linguistic_db.Lemma.id == lemma_id
        ).first()

        if not lemma:
            logger.error(f"Lemma ID {lemma_id} not found")
            return False

        # Check if we already have Lithuanian derivative forms for this lemma
        # Only skip if we have at least 3 forms that are in FORM_MAPPING
        existing_forms = session.query(linguistic_db.DerivativeForm).filter(
            linguistic_db.DerivativeForm.lemma_id == lemma_id,
            linguistic_db.DerivativeForm.language_code == 'lt'
        ).all()

        # Count how many of the existing forms are actual declension forms (in FORM_MAPPING)
        declension_forms_count = sum(
            1 for form in existing_forms
            if form.grammatical_form in [gf.value for gf in FORM_MAPPING.values()]
        )

        if declension_forms_count >= 3:
            logger.info(f"Lemma ID {lemma_id} ({lemma.lemma_text}) already has {declension_forms_count} Lithuanian declension forms, skipping")
            return True

        # Query for declensions based on source
        logger.info(f"Querying declensions for lemma ID {lemma_id}: {lemma.lemma_text} -> {lemma.lithuanian_translation} (source: {source})")

        number_type = 'regular'  # Default value
        if source == 'wiki':
            # Use Wiktionary-based implementation
            from wordfreq.translation.wiki import get_lithuanian_noun_forms
            forms_dict, success = get_lithuanian_noun_forms(lemma.lithuanian_translation)
            # Wiki implementation doesn't return number_type, so we'll try to detect it
            # from the forms: if all singular forms are missing/empty, it's plurale_tantum
            if success and forms_dict:
                singular_forms = [f for f in forms_dict.keys() if f.endswith('_singular')]
                plural_forms = [f for f in forms_dict.keys() if f.endswith('_plural')]
                has_singular = any(forms_dict.get(f) for f in singular_forms)
                has_plural = any(forms_dict.get(f) for f in plural_forms)

                if has_plural and not has_singular:
                    number_type = 'plurale_tantum'
                elif has_singular and not has_plural:
                    number_type = 'singulare_tantum'
        else:  # source == 'llm'
            # Use LLM-based implementation (existing behavior)
            forms_dict, success, number_type = client.query_lithuanian_noun_declensions(lemma_id)

        if not success or not forms_dict:
            logger.error(f"Failed to get declensions for lemma ID {lemma_id}")
            return False

        # Store each form as a derivative form
        stored_forms = 0
        for form_name, form_text in forms_dict.items():
            if form_name not in FORM_MAPPING:
                logger.warning(f"Unknown form name: {form_name}, skipping")
                continue

            # Skip empty or whitespace-only forms
            if not form_text or not form_text.strip():
                logger.debug(f"Skipping empty form: {form_name}")
                continue

            grammatical_form = FORM_MAPPING[form_name]
            is_base_form = (form_name == "nominative_singular")

            # Get or create word token for this Lithuanian form
            word_token = linguistic_db.add_word_token(session, form_text, 'lt')

            # Create derivative form
            derivative_form = linguistic_db.DerivativeForm(
                lemma_id=lemma_id,
                derivative_form_text=form_text,
                word_token_id=word_token.id,
                language_code='lt',
                grammatical_form=grammatical_form.value,
                is_base_form=is_base_form,
                verified=False
            )

            session.add(derivative_form)
            stored_forms += 1

        # Store grammar fact if the noun is plurale tantum or singulare tantum
        if number_type != 'regular':
            grammar_fact = linguistic_db.add_grammar_fact(
                session,
                lemma_id=lemma_id,
                language_code='lt',
                fact_type='number_type',
                fact_value=number_type,
                notes=f"Detected during declension generation (source: {source})",
                verified=False
            )
            if grammar_fact:
                logger.info(f"Added grammar_fact for lemma ID {lemma_id}: number_type={number_type}")
            else:
                logger.debug(f"Grammar fact for number_type={number_type} already exists for lemma ID {lemma_id}")

        session.commit()
        logger.info(f"Successfully added {stored_forms} forms for lemma ID {lemma_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error processing lemma ID {lemma_id}: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate Lithuanian noun declensions for all nouns in the database"
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit the number of lemmas to process (for testing)'
    )
    parser.add_argument(
        '--throttle',
        type=float,
        default=1.0,
        help='Seconds to wait between API calls (default: 1.0)'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=constants.WORDFREQ_DB_PATH,
        help='Path to the database'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='gpt-5-mini',
        help='LLM model to use (default: gpt-5-mini)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--yes',
        '-y',
        action='store_true',
        help='Skip confirmation prompt'
    )
    parser.add_argument(
        '--source',
        type=str,
        choices=['llm', 'wiki'],
        default='llm',
        help='Source for noun forms: llm (default) or wiki (Wiktionary)'
    )

    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Get all Lithuanian noun lemmas
    logger.info("Fetching Lithuanian noun lemmas from database...")
    lemmas = get_lithuanian_noun_lemmas(args.db_path, limit=args.limit)
    logger.info(f"Found {len(lemmas)} Lithuanian noun lemmas to process")

    if len(lemmas) == 0:
        logger.warning("No Lithuanian noun lemmas found")
        return

    # Confirmation prompt
    if not args.yes:
        print(f"\n{'='*60}")
        print(f"Ready to run queries for {len(lemmas)} words")
        print(f"Source: {args.source}")
        if args.source == 'llm':
            print(f"Model: {args.model}")
        print(f"Throttle: {args.throttle}s between calls")
        print(f"{'='*60}")
        response = input("\nContinue? [y/N]: ")
        if response.lower() not in ['y', 'yes']:
            print("Aborted.")
            return

    # Initialize client
    client = LinguisticClient(model=args.model, db_path=args.db_path, debug=args.debug)

    # Process each lemma
    successful = 0
    failed = 0
    skipped = 0

    for i, lemma_info in enumerate(lemmas, 1):
        logger.info(f"\n[{i}/{len(lemmas)}] Processing: {lemma_info['english']} -> {lemma_info['lithuanian']}")

        success = process_lemma_declensions(client, lemma_info['id'], args.db_path, source=args.source)

        if success:
            successful += 1
        else:
            failed += 1

        # Throttle to avoid overloading the API
        if i < len(lemmas):  # Don't sleep after the last one
            time.sleep(args.throttle)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing complete:")
    logger.info(f"  Total lemmas: {len(lemmas)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Skipped: {skipped}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    main()
