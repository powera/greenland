#!/usr/bin/env python3

"""Batch script to generate Portuguese noun forms for all nouns in the database."""

from wordfreq.translation.language_forms.portuguese import NOUN_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation,
)

CONFIG = FormGenerationConfig(
    language_code="pt",
    language_name="Portuguese",
    pos_type="noun",
    form_mapping=NOUN_FORM_MAPPING,
    client_method_name="query_portuguese_noun_forms",
    min_forms_threshold=2,
    base_form_identifier="singular",
    use_legacy_translation=False,
)


def get_portuguese_noun_lemmas(db_path: str, limit: int = None):
    """Get all nouns with Portuguese translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def main():
    run_form_generation(CONFIG, get_portuguese_noun_lemmas)


if __name__ == "__main__":
    main()
