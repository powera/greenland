#!/usr/bin/env python3

"""Batch script to generate German verb conjugations for all verbs in the database."""

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
    # Present
    "1s_pres": GrammaticalForm.VERB_DE_1S_PRES, "2s_pres": GrammaticalForm.VERB_DE_2S_PRES, "3s_pres": GrammaticalForm.VERB_DE_3S_PRES,
    "1p_pres": GrammaticalForm.VERB_DE_1P_PRES, "2p_pres": GrammaticalForm.VERB_DE_2P_PRES, "3p_pres": GrammaticalForm.VERB_DE_3P_PRES,
    # Past (Perfect - compound past)
    "1s_past": GrammaticalForm.VERB_DE_1S_PAST, "2s_past": GrammaticalForm.VERB_DE_2S_PAST, "3s_past": GrammaticalForm.VERB_DE_3S_PAST,
    "1p_past": GrammaticalForm.VERB_DE_1P_PAST, "2p_past": GrammaticalForm.VERB_DE_2P_PAST, "3p_past": GrammaticalForm.VERB_DE_3P_PAST,
    # Future
    "1s_fut": GrammaticalForm.VERB_DE_1S_FUT, "2s_fut": GrammaticalForm.VERB_DE_2S_FUT, "3s_fut": GrammaticalForm.VERB_DE_3S_FUT,
    "1p_fut": GrammaticalForm.VERB_DE_1P_FUT, "2p_fut": GrammaticalForm.VERB_DE_2P_FUT, "3p_fut": GrammaticalForm.VERB_DE_3P_FUT,
}

def get_german_verb_lemmas(db_path: str, limit: int = None) -> List[Dict]:
    """Get all verbs with German translations from database."""
    session = get_session(db_path)
    query = session.query(linguistic_db.Lemma).join(
        linguistic_db.LemmaTranslation,
        (linguistic_db.Lemma.id == linguistic_db.LemmaTranslation.lemma_id) &
        (linguistic_db.LemmaTranslation.language_code == 'de')
    ).filter(
        linguistic_db.Lemma.pos_type == 'verb'
    ).order_by(linguistic_db.Lemma.frequency_rank)

    if limit:
        query = query.limit(limit)

    results = []
    for lemma in query.all():
        german_trans = session.query(linguistic_db.LemmaTranslation).filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma.id,
            linguistic_db.LemmaTranslation.language_code == 'de'
        ).first()
        if german_trans:
            results.append({
                'id': lemma.id,
                'english': lemma.lemma_text,
                'german': german_trans.translation,
                'pos_subtype': lemma.pos_subtype
            })

    return results

def process_lemma_conjugations(client: LinguisticClient, lemma_id: int, db_path: str) -> bool:
    """Process and store German verb conjugations for a lemma."""
    session = get_session(db_path)
    try:
        lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        if not lemma:
            return False

        existing_forms = session.query(linguistic_db.DerivativeForm).filter(
            linguistic_db.DerivativeForm.lemma_id == lemma_id,
            linguistic_db.DerivativeForm.language_code == 'de'
        ).all()

        if sum(1 for f in existing_forms if f.grammatical_form in [g.value for g in FORM_MAPPING.values()]) >= 15:
            logger.info(f"Lemma ID {lemma_id} already has German verb forms, skipping")
            return True

        forms_dict, success = client.query_german_verb_conjugations(lemma_id)
        if not success or not forms_dict:
            return False

        stored = 0
        for form_name, form_text in forms_dict.items():
            if form_name not in FORM_MAPPING or not form_text or not form_text.strip():
                continue

            word_token = linguistic_db.add_word_token(session, form_text, 'de')
            session.add(linguistic_db.DerivativeForm(
                lemma_id=lemma_id,
                derivative_form_text=form_text,
                word_token_id=word_token.id,
                language_code='de',
                grammatical_form=FORM_MAPPING[form_name].value,
                is_base_form=False,
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
    parser = argparse.ArgumentParser(description="Generate German verb conjugations")
    parser.add_argument('--limit', type=int, help='Limit number of lemmas')
    parser.add_argument('--throttle', type=float, default=1.0, help='Seconds between calls')
    parser.add_argument('--db-path', type=str, default=constants.WORDFREQ_DB_PATH)
    parser.add_argument('--model', type=str, default='gpt-5-mini')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--yes', '-y', action='store_true')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    lemmas = get_german_verb_lemmas(args.db_path, limit=args.limit)
    logger.info(f"Found {len(lemmas)} German verb lemmas")
    if not lemmas:
        return

    if not args.yes:
        print(f"\n{'='*60}\nReady to process {len(lemmas)} words\nModel: {args.model}\n{'='*60}")
        if input("\nContinue? [y/N]: ").lower() not in ['y', 'yes']:
            return

    client = LinguisticClient(model=args.model, db_path=args.db_path, debug=args.debug)
    successful = failed = 0
    for i, lemma_info in enumerate(lemmas, 1):
        logger.info(f"\n[{i}/{len(lemmas)}] {lemma_info['english']} -> {lemma_info['german']}")
        if process_lemma_conjugations(client, lemma_info['id'], args.db_path):
            successful += 1
        else:
            failed += 1
        if i < len(lemmas):
            time.sleep(args.throttle)

    logger.info(f"\n{'='*60}\nComplete: {successful} successful, {failed} failed\n{'='*60}")

if __name__ == '__main__':
    main()
