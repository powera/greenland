#!/usr/bin/env python3

"""Batch script to generate German noun forms for all nouns in the database."""

from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation
)

# Configuration for German noun forms
FORM_MAPPING = {
    "singular": GrammaticalForm.NOUN_DE_SINGULAR,
    "plural": GrammaticalForm.NOUN_DE_PLURAL,
}

CONFIG = FormGenerationConfig(
    language_code='de',
    language_name='German',
    pos_type='noun',
    form_mapping=FORM_MAPPING,
    client_method_name='query_german_noun_forms',
    min_forms_threshold=2,
    base_form_identifier='singular',
    use_legacy_translation=False
)


def get_german_noun_lemmas(db_path: str, limit: int = None):
    """Get all nouns with German translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def main():
    run_form_generation(CONFIG, get_german_noun_lemmas)


if __name__ == '__main__':
    main()
