#!/usr/bin/env python3

"""Batch script to generate French verb conjugations for all verbs in the database."""

from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation
)

# Configuration for French verb forms
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
    # Passé composé (8 persons)
    "1s_pc": GrammaticalForm.VERB_FR_1S_PC, "2s_pc": GrammaticalForm.VERB_FR_2S_PC,
    "3s-m_pc": GrammaticalForm.VERB_FR_3S_M_PC, "3s-f_pc": GrammaticalForm.VERB_FR_3S_F_PC,
    "1p_pc": GrammaticalForm.VERB_FR_1P_PC, "2p_pc": GrammaticalForm.VERB_FR_2P_PC,
    "3p-m_pc": GrammaticalForm.VERB_FR_3P_M_PC, "3p-f_pc": GrammaticalForm.VERB_FR_3P_F_PC,
}

CONFIG = FormGenerationConfig(
    language_code='fr',
    language_name='French',
    pos_type='verb',
    form_mapping=FORM_MAPPING,
    client_method_name='query_french_verb_conjugations',
    min_forms_threshold=25,
    base_form_identifier='1s_pres',
    use_legacy_translation=True,
    translation_field_name='french_translation'
)


def get_french_verb_lemmas(db_path: str, limit: int = None):
    """Get all verbs with French translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def main():
    run_form_generation(CONFIG, get_french_verb_lemmas)


if __name__ == '__main__':
    main()
