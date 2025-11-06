#!/usr/bin/env python3

"""Batch script to generate French noun forms for all nouns in the database."""

from wordfreq.translation.language_forms.french import NOUN_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation
)

CONFIG = FormGenerationConfig(
    language_code='fr',
    language_name='French',
    pos_type='noun',
    form_mapping=NOUN_FORM_MAPPING,
    client_method_name='query_french_noun_forms',
    min_forms_threshold=2,
    base_form_identifier='singular_m',
    use_legacy_translation=True,
    translation_field_name='french_translation',
    extract_gender=True
)


def get_french_noun_lemmas(db_path: str, limit: int = None):
    """Get all nouns with French translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def main():
    run_form_generation(CONFIG, get_french_noun_lemmas)


if __name__ == '__main__':
    main()
