#!/usr/bin/env python3

"""Batch script to generate French verb conjugations for all verbs in the database."""

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FORM_MAPPING = {
    # Present (8 persons)
    "1s_pres": GrammaticalForm.VERB_FR_1S_PRES, "2s_pres": GrammaticalForm.VERB_FR_2S_PRES,
    "3s-m_pres": GrammaticalForm.VERB_FR_3S_M_PRES, "3s-f_pres": GrammaticalForm.VERB_FR_3S_F_PRES,
    "1p_pres": GrammaticalForm.VERB_FR_1P_PRES, "2p_pres": GrammaticalForm.VERB_FR_2P_PRES,
    "3p-m_pres": GrammaticalForm.VERB_FR_3P_M_PRES, "3p-f_pres": GrammaticalForm.VERB_FR_3P_F_PRES,
    # Imperfect (8 persons)
    "1s_impf": GrammaticalForm.VERB_FR_1S_IMPF, "2s_impf": GrammaticalForm.VERB_FR_2S_IMPF,
    "3s-m_impf": GrammaticalForm.VERB_FR_3S_M_IMPF, "3s-f_impf": GrammaticalForm.VERB_FR_3S_F_IMPF,
    "1p_impf": GrammaticalForm.VERB_FR_1P_IMPF, "2p_impf": GrammaticalForm.VERB_FR_2P_IMPF,
    "3p-m_impf": GrammaticalForm.VERB_FR_3P_M_IMPF, "3p-f_impf": GrammaticalForm.VERB_FR_3P_F_IMPF,
    # Future (8 persons)
    "1s_fut": GrammaticalForm.VERB_FR_1S_FUT, "2s_fut": GrammaticalForm.VERB_FR_2S_FUT,
    "3s-m_fut": GrammaticalForm.VERB_FR_3S_M_FUT, "3s-f_fut": GrammaticalForm.VERB_FR_3S_F_FUT,
    "1p_fut": GrammaticalForm.VERB_FR_1P_FUT, "2p_fut": GrammaticalForm.VERB_FR_2P_FUT,
    "3p-m_fut": GrammaticalForm.VERB_FR_3P_M_FUT, "3p-f_fut": GrammaticalForm.VERB_FR_3P_F_FUT,
    # Conditional (8 persons)
    "1s_cond": GrammaticalForm.VERB_FR_1S_COND, "2s_cond": GrammaticalForm.VERB_FR_2S_COND,
    "3s-m_cond": GrammaticalForm.VERB_FR_3S_M_COND, "3s-f_cond": GrammaticalForm.VERB_FR_3S_F_COND,
    "1p_cond": GrammaticalForm.VERB_FR_1P_COND, "2p_cond": GrammaticalForm.VERB_FR_2P_COND,
    "3p-m_cond": GrammaticalForm.VERB_FR_3P_M_COND, "3p-f_cond": GrammaticalForm.VERB_FR_3P_F_COND,
    # Subjunctive (8 persons)
    "1s_subj": GrammaticalForm.VERB_FR_1S_SUBJ, "2s_subj": GrammaticalForm.VERB_FR_2S_SUBJ,
    "3s-m_subj": GrammaticalForm.VERB_FR_3S_M_SUBJ, "3s-f_subj": GrammaticalForm.VERB_FR_3S_F_SUBJ,
    "1p_subj": GrammaticalForm.VERB_FR_1P_SUBJ, "2p_subj": GrammaticalForm.VERB_FR_2P_SUBJ,
    "3p-m_subj": GrammaticalForm.VERB_FR_3P_M_SUBJ, "3p-f_subj": GrammaticalForm.VERB_FR_3P_F_SUBJ,
    # Passé composé (8 persons)
    "1s_pc": GrammaticalForm.VERB_FR_1S_PC, "2s_pc": GrammaticalForm.VERB_FR_2S_PC,
    "3s-m_pc": GrammaticalForm.VERB_FR_3S_M_PC, "3s-f_pc": GrammaticalForm.VERB_FR_3S_F_PC,
    "1p_pc": GrammaticalForm.VERB_FR_1P_PC, "2p_pc": GrammaticalForm.VERB_FR_2P_PC,
    "3p-m_pc": GrammaticalForm.VERB_FR_3P_M_PC, "3p-f_pc": GrammaticalForm.VERB_FR_3P_F_PC,
}

def get_french_verb_lemmas(db_path: str, limit: int = None) -> List[Dict]:
    session = get_session(db_path)
    query = session.query(linguistic_db.Lemma).filter(
        linguistic_db.Lemma.pos_type == 'verb',
        linguistic_db.Lemma.french_translation.isnot(None),
        linguistic_db.Lemma.french_translation != ''
    ).order_by(linguistic_db.Lemma.frequency_rank)
    if limit:
        query = query.limit(limit)
    return [{'id': l.id, 'english': l.lemma_text, 'french': l.french_translation, 'pos_subtype': l.pos_subtype} for l in query.all()]

def process_lemma_conjugations(client: LinguisticClient, lemma_id: int, db_path: str) -> bool:
    session = get_session(db_path)
    try:
        lemma = session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        if not lemma:
            return False
        existing_forms = session.query(linguistic_db.DerivativeForm).filter(
            linguistic_db.DerivativeForm.lemma_id == lemma_id,
            linguistic_db.DerivativeForm.language_code == 'fr'
        ).all()
        if sum(1 for f in existing_forms if f.grammatical_form in [g.value for g in FORM_MAPPING.values()]) >= 3:
            logger.info(f"Lemma ID {lemma_id} already has French conjugations, skipping")
            return True

        forms_dict, success = client.query_french_verb_conjugations(lemma_id)
        if not success or not forms_dict:
            return False

        stored = 0
        for form_name, form_text in forms_dict.items():
            if form_name not in FORM_MAPPING or not form_text or not form_text.strip():
                continue
            word_token = linguistic_db.add_word_token(session, form_text, 'fr')
            session.add(linguistic_db.DerivativeForm(
                lemma_id=lemma_id, derivative_form_text=form_text, word_token_id=word_token.id,
                language_code='fr', grammatical_form=FORM_MAPPING[form_name].value,
                is_base_form=(form_name == "1s_pres"), verified=False))
            stored += 1
        session.commit()
        logger.info(f"Added {stored} forms for lemma ID {lemma_id}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing lemma ID {lemma_id}: {e}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(description="Generate French verb conjugations")
    parser.add_argument('--limit', type=int, help='Limit number of lemmas')
    parser.add_argument('--throttle', type=float, default=1.0, help='Seconds between calls')
    parser.add_argument('--db-path', type=str, default=constants.WORDFREQ_DB_PATH)
    parser.add_argument('--model', type=str, default='gpt-5-mini')
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--yes', '-y', action='store_true')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    lemmas = get_french_verb_lemmas(args.db_path, limit=args.limit)
    logger.info(f"Found {len(lemmas)} French verb lemmas")
    if not lemmas:
        return

    if not args.yes:
        print(f"\n{'='*60}\nReady to process {len(lemmas)} verbs\nModel: {args.model}\n{'='*60}")
        if input("\nContinue? [y/N]: ").lower() not in ['y', 'yes']:
            return

    client = LinguisticClient(model=args.model, db_path=args.db_path, debug=args.debug)
    successful = failed = 0
    for i, lemma_info in enumerate(lemmas, 1):
        logger.info(f"\n[{i}/{len(lemmas)}] {lemma_info['english']} -> {lemma_info['french']}")
        if process_lemma_conjugations(client, lemma_info['id'], args.db_path):
            successful += 1
        else:
            failed += 1
        if i < len(lemmas):
            time.sleep(args.throttle)

    logger.info(f"\n{'='*60}\nComplete: {successful} successful, {failed} failed\n{'='*60}")

if __name__ == '__main__':
    main()
