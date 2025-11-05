#!/usr/bin/env python3

"""Batch script to generate Spanish verb conjugations for all verbs in the database."""

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
    "1s_pres": GrammaticalForm.VERB_ES_1S_PRES, "2s_pres": GrammaticalForm.VERB_ES_2S_PRES, "3s_pres": GrammaticalForm.VERB_ES_3S_PRES,
    "1p_pres": GrammaticalForm.VERB_ES_1P_PRES, "2p_pres": GrammaticalForm.VERB_ES_2P_PRES, "3p_pres": GrammaticalForm.VERB_ES_3P_PRES,
    # Preterite
    "1s_pret": GrammaticalForm.VERB_ES_1S_PRET, "2s_pret": GrammaticalForm.VERB_ES_2S_PRET, "3s_pret": GrammaticalForm.VERB_ES_3S_PRET,
    "1p_pret": GrammaticalForm.VERB_ES_1P_PRET, "2p_pret": GrammaticalForm.VERB_ES_2P_PRET, "3p_pret": GrammaticalForm.VERB_ES_3P_PRET,
    # Imperfect
    "1s_impf": GrammaticalForm.VERB_ES_1S_IMPF, "2s_impf": GrammaticalForm.VERB_ES_2S_IMPF, "3s_impf": GrammaticalForm.VERB_ES_3S_IMPF,
    "1p_impf": GrammaticalForm.VERB_ES_1P_IMPF, "2p_impf": GrammaticalForm.VERB_ES_2P_IMPF, "3p_impf": GrammaticalForm.VERB_ES_3P_IMPF,
    # Future
    "1s_fut": GrammaticalForm.VERB_ES_1S_FUT, "2s_fut": GrammaticalForm.VERB_ES_2S_FUT, "3s_fut": GrammaticalForm.VERB_ES_3S_FUT,
    "1p_fut": GrammaticalForm.VERB_ES_1P_FUT, "2p_fut": GrammaticalForm.VERB_ES_2P_FUT, "3p_fut": GrammaticalForm.VERB_ES_3P_FUT,
    # Conditional
    "1s_cond": GrammaticalForm.VERB_ES_1S_COND, "2s_cond": GrammaticalForm.VERB_ES_2S_COND, "3s_cond": GrammaticalForm.VERB_ES_3S_COND,
    "1p_cond": GrammaticalForm.VERB_ES_1P_COND, "2p_cond": GrammaticalForm.VERB_ES_2P_COND, "3p_cond": GrammaticalForm.VERB_ES_3P_COND,
    # Subjunctive
    "1s_subj": GrammaticalForm.VERB_ES_1S_SUBJ, "2s_subj": GrammaticalForm.VERB_ES_2S_SUBJ, "3s_subj": GrammaticalForm.VERB_ES_3S_SUBJ,
    "1p_subj": GrammaticalForm.VERB_ES_1P_SUBJ, "2p_subj": GrammaticalForm.VERB_ES_2P_SUBJ, "3p_subj": GrammaticalForm.VERB_ES_3P_SUBJ,
}

def get_spanish_verb_lemmas(db_path: str, limit: int = None) -> List[Dict]:
    """Get all verbs with Spanish translations from database."""
    session = get_session(db_path)
    query = session.query(linguistic_db.Lemma).join(
        linguistic_db.LemmaTranslation,
        (linguistic_db.Lemma.id == linguistic_db.LemmaTranslation.lemma_id) &
        (linguistic_db.LemmaTranslation.language_code == 'es')
    ).filter(
        linguistic_db.Lemma.pos_type == 'verb'
    ).order_by(linguistic_db.Lemma.frequency_rank)

    if limit:
        query = query.limit(limit)

    results = []
    for lemma in query.all():
        spanish_trans = session.query(linguistic_db.LemmaTranslation).filter(
            linguistic_db.LemmaTranslation.lemma_id == lemma.id,
            linguistic_db.LemmaTranslation.language_code == 'es'
        ).first()
        if spanish_trans:
            results.append({
                'id': lemma.id,
                'english': lemma.lemma_text,
                'spanish': spanish_trans.translation,
                'pos_subtype': lemma.pos_subtype
            })

    return results

def process_lemma_conjugations(client: LinguisticClient, lemma_id: int, db_path: str) -> bool:
    """Process and store Spanish verb conjugations for a lemma."""
    session = get_session(db_path)
    try:
        lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        if not lemma:
            return False

        existing_forms = session.query(linguistic_db.DerivativeForm).filter(
            linguistic_db.DerivativeForm.lemma_id == lemma_id,
            linguistic_db.DerivativeForm.language_code == 'es'
        ).all()

        if sum(1 for f in existing_forms if f.grammatical_form in [g.value for g in FORM_MAPPING.values()]) >= 30:
            logger.info(f"Lemma ID {lemma_id} already has Spanish verb forms, skipping")
            return True

        forms_dict, success = client.query_spanish_verb_conjugations(lemma_id)
        if not success or not forms_dict:
            return False

        stored = 0
        for form_name, form_text in forms_dict.items():
            if form_name not in FORM_MAPPING or not form_text or not form_text.strip():
                continue

            word_token = linguistic_db.add_word_token(session, form_text, 'es')
            session.add(linguistic_db.DerivativeForm(
                lemma_id=lemma_id,
                derivative_form_text=form_text,
                word_token_id=word_token.id,
                language_code='es',
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
    parser = argparse.ArgumentParser(description="Generate Spanish verb conjugations")
    parser.add_argument('--limit', type=int, help='Limit number of lemmas')
    parser.add_argument('--throttle', type=float, default=1.0, help='Seconds between calls')
    parser.add_argument('--db-path', type=str, default=constants.WORDFREQ_DB_PATH)
    parser.add_argument('--model', type=str, default='gpt-5-mini')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--yes', '-y', action='store_true')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    lemmas = get_spanish_verb_lemmas(args.db_path, limit=args.limit)
    logger.info(f"Found {len(lemmas)} Spanish verb lemmas")
    if not lemmas:
        return

    if not args.yes:
        print(f"\n{'='*60}\nReady to process {len(lemmas)} words\nModel: {args.model}\n{'='*60}")
        if input("\nContinue? [y/N]: ").lower() not in ['y', 'yes']:
            return

    client = LinguisticClient(model=args.model, db_path=args.db_path, debug=args.debug)
    successful = failed = 0
    for i, lemma_info in enumerate(lemmas, 1):
        logger.info(f"\n[{i}/{len(lemmas)}] {lemma_info['english']} -> {lemma_info['spanish']}")
        if process_lemma_conjugations(client, lemma_info['id'], args.db_path):
            successful += 1
        else:
            failed += 1
        if i < len(lemmas):
            time.sleep(args.throttle)

    logger.info(f"\n{'='*60}\nComplete: {successful} successful, {failed} failed\n{'='*60}")

if __name__ == '__main__':
    main()
