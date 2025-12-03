#!/usr/bin/env python3

"""
Batch script to generate Lithuanian verb conjugations for all verbs in the database.

This script:
1. Queries all lemmas with Lithuanian translations that are verbs
2. For each verb, generates all 24 conjugation forms (3 tenses × 8 persons)
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
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Mapping from form field names to GrammaticalForm enum values
FORM_MAPPING = {
    # Present tense
    "1s_pres": GrammaticalForm.VERB_LT_1S_PRES,
    "2s_pres": GrammaticalForm.VERB_LT_2S_PRES,
    "3s_m_pres": GrammaticalForm.VERB_LT_3S_M_PRES,
    "3s_f_pres": GrammaticalForm.VERB_LT_3S_F_PRES,
    "1p_pres": GrammaticalForm.VERB_LT_1P_PRES,
    "2p_pres": GrammaticalForm.VERB_LT_2P_PRES,
    "3p_m_pres": GrammaticalForm.VERB_LT_3P_M_PRES,
    "3p_f_pres": GrammaticalForm.VERB_LT_3P_F_PRES,
    # Past tense
    "1s_past": GrammaticalForm.VERB_LT_1S_PAST,
    "2s_past": GrammaticalForm.VERB_LT_2S_PAST,
    "3s_m_past": GrammaticalForm.VERB_LT_3S_M_PAST,
    "3s_f_past": GrammaticalForm.VERB_LT_3S_F_PAST,
    "1p_past": GrammaticalForm.VERB_LT_1P_PAST,
    "2p_past": GrammaticalForm.VERB_LT_2P_PAST,
    "3p_m_past": GrammaticalForm.VERB_LT_3P_M_PAST,
    "3p_f_past": GrammaticalForm.VERB_LT_3P_F_PAST,
    # Future tense
    "1s_fut": GrammaticalForm.VERB_LT_1S_FUT,
    "2s_fut": GrammaticalForm.VERB_LT_2S_FUT,
    "3s_m_fut": GrammaticalForm.VERB_LT_3S_M_FUT,
    "3s_f_fut": GrammaticalForm.VERB_LT_3S_F_FUT,
    "1p_fut": GrammaticalForm.VERB_LT_1P_FUT,
    "2p_fut": GrammaticalForm.VERB_LT_2P_FUT,
    "3p_m_fut": GrammaticalForm.VERB_LT_3P_M_FUT,
    "3p_f_fut": GrammaticalForm.VERB_LT_3P_F_FUT,
}


def get_lithuanian_verb_lemmas(db_path: str, limit: int = None) -> List[Dict]:
    """
    Get all lemmas that are verbs with Lithuanian translations.

    Args:
        db_path: Path to the database
        limit: Optional limit on number of lemmas to return

    Returns:
        List of dictionaries with lemma information
    """
    session = get_session(db_path)

    query = (
        session.query(linguistic_db.Lemma)
        .filter(
            linguistic_db.Lemma.pos_type == "verb",
            linguistic_db.Lemma.lithuanian_translation.isnot(None),
            linguistic_db.Lemma.lithuanian_translation != "",
        )
        .order_by(linguistic_db.Lemma.frequency_rank)
    )

    if limit:
        query = query.limit(limit)

    lemmas = query.all()

    result = []
    for lemma in lemmas:
        result.append(
            {
                "id": lemma.id,
                "english": lemma.lemma_text,
                "lithuanian": lemma.lithuanian_translation,
                "pos_subtype": lemma.pos_subtype,
                "frequency_rank": lemma.frequency_rank,
            }
        )

    return result


def process_lemma_conjugations(client: LinguisticClient, lemma_id: int, db_path: str) -> bool:
    """
    Process a single lemma to generate and store all its conjugations.

    Args:
        client: LinguisticClient instance
        lemma_id: ID of the lemma to process
        db_path: Path to the database

    Returns:
        Success flag
    """
    session = get_session(db_path)

    try:
        # Get the lemma
        lemma = (
            session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        )

        if not lemma:
            logger.error(f"Lemma ID {lemma_id} not found")
            return False

        # Check if we already have Lithuanian derivative forms for this lemma
        # Only skip if we have at least 3 forms that are in FORM_MAPPING
        existing_forms = (
            session.query(linguistic_db.DerivativeForm)
            .filter(
                linguistic_db.DerivativeForm.lemma_id == lemma_id,
                linguistic_db.DerivativeForm.language_code == "lt",
            )
            .all()
        )

        # Count how many of the existing forms are actual conjugation forms (in FORM_MAPPING)
        conjugation_forms_count = sum(
            1
            for form in existing_forms
            if form.grammatical_form in [gf.value for gf in FORM_MAPPING.values()]
        )

        if conjugation_forms_count >= 3:
            logger.info(
                f"Lemma ID {lemma_id} ({lemma.lemma_text}) already has {conjugation_forms_count} Lithuanian conjugation forms, skipping"
            )
            return True

        # Query for conjugations
        logger.info(
            f"Querying conjugations for lemma ID {lemma_id}: {lemma.lemma_text} -> {lemma.lithuanian_translation}"
        )

        forms_dict, success = client.query_lithuanian_verb_conjugations(lemma_id)

        if not success or not forms_dict:
            logger.error(f"Failed to get conjugations for lemma ID {lemma_id}")
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
            # The infinitive is the base form for verbs, but we don't have it in these conjugations
            # So we'll mark the 1st person singular present as base form as a convention
            is_base_form = form_name == "1s_pres"

            # Get or create word token for this Lithuanian form
            word_token = linguistic_db.add_word_token(session, form_text, "lt")

            # Create derivative form
            derivative_form = linguistic_db.DerivativeForm(
                lemma_id=lemma_id,
                derivative_form_text=form_text,
                word_token_id=word_token.id,
                language_code="lt",
                grammatical_form=grammatical_form.value,
                is_base_form=is_base_form,
                verified=False,
            )

            session.add(derivative_form)
            stored_forms += 1

        session.commit()
        logger.info(f"Successfully added {stored_forms} forms for lemma ID {lemma_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error processing lemma ID {lemma_id}: {e}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Generate Lithuanian verb conjugations for all verbs in the database"
    )
    parser.add_argument(
        "--limit", type=int, help="Limit the number of lemmas to process (for testing)"
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=1.0,
        help="Seconds to wait between API calls (default: 1.0)",
    )
    parser.add_argument(
        "--db-path", type=str, default=constants.WORDFREQ_DB_PATH, help="Path to the database"
    )
    parser.add_argument(
        "--model", type=str, default="gpt-5-mini", help="LLM model to use (default: gpt-5-mini)"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Get all Lithuanian verb lemmas
    logger.info("Fetching Lithuanian verb lemmas from database...")
    lemmas = get_lithuanian_verb_lemmas(args.db_path, limit=args.limit)
    logger.info(f"Found {len(lemmas)} Lithuanian verb lemmas to process")

    if len(lemmas) == 0:
        logger.warning("No Lithuanian verb lemmas found")
        return

    # Confirmation prompt
    if not args.yes:
        print(f"\n{'='*60}")
        print(f"Ready to run queries for {len(lemmas)} words")
        print(f"Model: {args.model}")
        print(f"Throttle: {args.throttle}s between calls")
        print(f"{'='*60}")
        response = input("\nContinue? [y/N]: ")
        if response.lower() not in ["y", "yes"]:
            print("Aborted.")
            return

    # Initialize client
    client = LinguisticClient(model=args.model, db_path=args.db_path, debug=args.debug)

    # Process each lemma
    successful = 0
    failed = 0
    skipped = 0

    for i, lemma_info in enumerate(lemmas, 1):
        logger.info(
            f"\n[{i}/{len(lemmas)}] Processing: {lemma_info['english']} -> {lemma_info['lithuanian']}"
        )

        success = process_lemma_conjugations(client, lemma_info["id"], args.db_path)

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


if __name__ == "__main__":
    main()
