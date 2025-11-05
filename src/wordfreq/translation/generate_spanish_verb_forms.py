#!/usr/bin/env python3

"""Batch script to generate Spanish verb conjugations for all verbs in the database."""

from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation
)

# Configuration for Spanish verb forms
FORM_MAPPING = {
    # Present (8 persons)
    "1s_pres": GrammaticalForm.VERB_ES_1S_PRES, "2s_pres": GrammaticalForm.VERB_ES_2S_PRES,
    "3s-m_pres": GrammaticalForm.VERB_ES_3S_M_PRES, "3s-f_pres": GrammaticalForm.VERB_ES_3S_F_PRES,
    "1p_pres": GrammaticalForm.VERB_ES_1P_PRES, "2p_pres": GrammaticalForm.VERB_ES_2P_PRES,
    "3p-m_pres": GrammaticalForm.VERB_ES_3P_M_PRES, "3p-f_pres": GrammaticalForm.VERB_ES_3P_F_PRES,
    # Past (Preterite) (8 persons)
    "1s_past": GrammaticalForm.VERB_ES_1S_PAST, "2s_past": GrammaticalForm.VERB_ES_2S_PAST,
    "3s-m_past": GrammaticalForm.VERB_ES_3S_M_PAST, "3s-f_past": GrammaticalForm.VERB_ES_3S_F_PAST,
    "1p_past": GrammaticalForm.VERB_ES_1P_PAST, "2p_past": GrammaticalForm.VERB_ES_2P_PAST,
    "3p-m_past": GrammaticalForm.VERB_ES_3P_M_PAST, "3p-f_past": GrammaticalForm.VERB_ES_3P_F_PAST,
    # Future (8 persons)
    "1s_fut": GrammaticalForm.VERB_ES_1S_FUT, "2s_fut": GrammaticalForm.VERB_ES_2S_FUT,
    "3s-m_fut": GrammaticalForm.VERB_ES_3S_M_FUT, "3s-f_fut": GrammaticalForm.VERB_ES_3S_F_FUT,
    "1p_fut": GrammaticalForm.VERB_ES_1P_FUT, "2p_fut": GrammaticalForm.VERB_ES_2P_FUT,
    "3p-m_fut": GrammaticalForm.VERB_ES_3P_M_FUT, "3p-f_fut": GrammaticalForm.VERB_ES_3P_F_FUT,
}

CONFIG = FormGenerationConfig(
    language_code='es',
    language_name='Spanish',
    pos_type='verb',
    form_mapping=FORM_MAPPING,
    client_method_name='query_spanish_verb_conjugations',
    min_forms_threshold=20,
    base_form_identifier='1s_pres',
    use_legacy_translation=False
)


def get_spanish_verb_lemmas(db_path: str, limit: int = None):
    """Get all verbs with Spanish translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def main():
    run_form_generation(CONFIG, get_spanish_verb_lemmas)


if __name__ == '__main__':
    main()
