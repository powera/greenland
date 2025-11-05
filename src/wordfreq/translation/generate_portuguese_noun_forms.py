#!/usr/bin/env python3

"""Batch script to generate Portuguese noun forms for all nouns in the database."""

import argparse
import logging
import time
from typing import Dict, List

from wordfreq.translation.client import LinguisticClient
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.storage.connection_pool import get_session
import constants

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FORM_MAPPING = {
    "singular": GrammaticalForm.NOUN_PT_SINGULAR,
    "plural": GrammaticalForm.NOUN_PT_PLURAL,
}

def get_portuguese_noun_lemmas(db_path: str, limit: int = None) -> List[Dict]:
    """Get all nouns with Portuguese translations from database."""
    session = get_session(db_path)
    query = session.query(linguistic_db.Lemma).join(
        linguistic_db.LemmaTranslation,
        (linguistic_db.Lemma.id == linguistic_db.LemmaTranslation.lemma_id) &
        (linguistic_db.LemmaTranslation.language_code == 'pt')
    ).filter(
        linguistic_db.Lemma.pos_type == 'noun'
    ).order_by(linguistic_db.Lemma.frequency_rank)

    if limit:
        query = query.limit(limit)

    results = []
    for lemma in query.all():
        portuguese_trans = session.query(linguistic_db.LemmaTranslation).filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma.id,
            linguistic_db.LemmaTranslation.language_code == 'pt'
        ).first()
        if portuguese_trans:
            results.append({
                'id': lemma.id,
                'english': lemma.lemma_text,
                'portuguese': portuguese_trans.translation,
                'pos_subtype': lemma.pos_subtype
            })

    return results

def process_lemma_forms(client: LinguisticClient, lemma_id: int, db_path: str) -> bool:
    """Process and store Portuguese noun forms for a lemma."""
    session = get_session(db_path)
    try:
        lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        if not lemma:
            return False

        # Check if forms already exist
        existing_forms = session.query(linguistic_db.DerivativeForm).filter(
            linguistic_db.DerivativeForm.lemma_id == lemma_id,
            linguistic_db.DerivativeForm.language_code == 'pt'
        ).all()

        if sum(1 for f in existing_forms if f.grammatical_form in [g.value for g in FORM_MAPPING.values()]) >= 2:
            logger.info(f"Lemma ID {lemma_id} already has Portuguese forms, skipping")
            return True

        forms_dict, success = client.query_portuguese_noun_forms(lemma_id)
        if not success or not forms_dict:
            return False

        stored = 0
        for form_name, form_text in forms_dict.items():
            if form_name not in FORM_MAPPING or not form_text or not form_text.strip():
                continue

            word_token = linguistic_db.add_word_token(session, form_text, 'pt')
            session.add(linguistic_db.DerivativeForm(
                lemma_id=lemma_id,
                derivative_form_text=form_text,
                word_token_id=word_token.id,
                language_code='pt',
                grammatical_form=FORM_MAPPING[form_name].value,
                is_base_form=(form_name == "singular"),
                verified=False
            ))
            stored += 1

        session.commit()
        logger.info(f"Added {stored} forms for lemma ID {lemma_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error processing lemma ID {lemma_id}: {e}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(description="Generate Portuguese noun forms")
    parser.add_argument('--limit', type=int, help='Limit number of lemmas')
    parser.add_argument('--throttle', type=float, default=1.0, help='Seconds between calls')
    parser.add_argument('--db-path', type=str, default=constants.WORDFREQ_DB_PATH)
    parser.add_argument('--model', type=str, default='gpt-5-mini')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--yes', '-y', action='store_true')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    lemmas = get_portuguese_noun_lemmas(args.db_path, limit=args.limit)
    logger.info(f"Found {len(lemmas)} Portuguese noun lemmas")
    if not lemmas:
        return

    if not args.yes:
        print(f"\n{'='*60}\nReady to process {len(lemmas)} words\nModel: {args.model}\n{'='*60}")
        if input("\nContinue? [y/N]: ").lower() not in ['y', 'yes']:
            return

    client = LinguisticClient(model=args.model, db_path=args.db_path, debug=args.debug)
    successful = failed = 0
    for i, lemma_info in enumerate(lemmas, 1):
        logger.info(f"\n[{i}/{len(lemmas)}] {lemma_info['english']} -> {lemma_info['portuguese']}")
        if process_lemma_forms(client, lemma_info['id'], args.db_path):
            successful += 1
        else:
            failed += 1
        if i < len(lemmas):
            time.sleep(args.throttle)

    logger.info(f"\n{'='*60}\nComplete: {successful} successful, {failed} failed\n{'='*60}")

if __name__ == '__main__':
    main()
