#!/usr/bin/env python3

"""Batch script to generate French noun forms for all nouns in the database."""

from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation
)

# Configuration for French noun forms
# The client returns gendered forms (singular_m, plural_m, singular_f, plural_f)
# We map them to generic singular/plural and extract gender separately
FORM_MAPPING = {
    "singular_m": GrammaticalForm.NOUN_FR_SINGULAR,
    "plural_m": GrammaticalForm.NOUN_FR_PLURAL,
    "singular_f": GrammaticalForm.NOUN_FR_SINGULAR,
    "plural_f": GrammaticalForm.NOUN_FR_PLURAL,
}

CONFIG = FormGenerationConfig(
    language_code='fr',
    language_name='French',
    pos_type='noun',
    form_mapping=FORM_MAPPING,
    client_method_name='query_french_noun_forms',
    min_forms_threshold=2,
    base_form_identifier='singular_m',  # Default to masculine as base form
    use_legacy_translation=True,
    translation_field_name='french_translation',
    detect_number_type=True,  # Detect plurale tantum/singulare tantum
    extract_gender=True  # Extract masculine/feminine from form names
)


def get_french_noun_lemmas(db_path: str, limit: int = None):
    """Get all nouns with French translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def main():
    run_form_generation(CONFIG, get_french_noun_lemmas)


if __name__ == '__main__':
    main()
