#!/usr/bin/env python3

"""
Batch script to generate English verb conjugations for all verbs in the database.

This script:
1. Queries all lemmas that are English verbs
2. For each verb, generates all conjugation forms (3 tenses × 6 persons + 2 imperatives)
3. Stores the forms as derivative_forms in the database
"""

from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_without_translation,
    run_form_generation
)

# Mapping from form field names to GrammaticalForm enum values
FORM_MAPPING = {
    # Present tense
    "1s_pres": GrammaticalForm.VERB_EN_1S_PRES,
    "2s_pres": GrammaticalForm.VERB_EN_2S_PRES,
    "3s_pres": GrammaticalForm.VERB_EN_3S_PRES,
    "1p_pres": GrammaticalForm.VERB_EN_1P_PRES,
    "2p_pres": GrammaticalForm.VERB_EN_2P_PRES,
    "3p_pres": GrammaticalForm.VERB_EN_3P_PRES,
    # Past tense
    "1s_past": GrammaticalForm.VERB_EN_1S_PAST,
    "2s_past": GrammaticalForm.VERB_EN_2S_PAST,
    "3s_past": GrammaticalForm.VERB_EN_3S_PAST,
    "1p_past": GrammaticalForm.VERB_EN_1P_PAST,
    "2p_past": GrammaticalForm.VERB_EN_2P_PAST,
    "3p_past": GrammaticalForm.VERB_EN_3P_PAST,
    # Future tense
    "1s_fut": GrammaticalForm.VERB_EN_1S_FUT,
    "2s_fut": GrammaticalForm.VERB_EN_2S_FUT,
    "3s_fut": GrammaticalForm.VERB_EN_3S_FUT,
    "1p_fut": GrammaticalForm.VERB_EN_1P_FUT,
    "2p_fut": GrammaticalForm.VERB_EN_2P_FUT,
    "3p_fut": GrammaticalForm.VERB_EN_3P_FUT,
    # Imperative
    "2s_imp": GrammaticalForm.VERB_EN_2S_IMP,
    "2p_imp": GrammaticalForm.VERB_EN_2P_IMP,
}

CONFIG = FormGenerationConfig(
    language_code='en',
    language_name='English',
    pos_type='verb',
    form_mapping=FORM_MAPPING,
    client_method_name='query_english_verb_conjugations',
    min_forms_threshold=3,
    base_form_identifier='1s_pres',
    use_legacy_translation=False
)


def get_english_verb_lemmas(db_path: str, limit: int = None):
    """Get all lemmas that are English verbs."""
    return get_lemmas_without_translation(db_path, 'verb', limit)


def main():
    run_form_generation(CONFIG, get_english_verb_lemmas)


if __name__ == '__main__':
    main()
