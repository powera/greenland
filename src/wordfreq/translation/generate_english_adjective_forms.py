#!/usr/bin/env python3

"""Batch script to generate English adjective forms for all adjectives in the database."""

from wordfreq.translation.language_forms.english import ADJECTIVE_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_needing_forms,
    run_form_generation,
)

CONFIG = FormGenerationConfig(
    language_code="en",
    language_name="English",
    pos_type="adjective",
    form_mapping=ADJECTIVE_FORM_MAPPING,
    client_method_name="query_english_adjective_forms",
    min_forms_threshold=1,
    base_form_identifier="positive",
    use_legacy_translation=False,
    translation_field_name=None,  # English uses lemma_text directly
    extract_gender=False,
)


def get_english_adjective_lemmas(db_path: str, limit: int = None):
    """Get all English adjectives from database that need forms."""
    return get_lemmas_needing_forms(db_path, CONFIG, limit)


def process_lemma(client, lemma_id: int, db_path: str) -> bool:
    """Process a single lemma to generate English adjective forms."""
    from wordfreq.translation.generate_forms_base import process_lemma_forms as process_base
    return process_base(client, lemma_id, db_path, CONFIG)


def main():
    run_form_generation(CONFIG, get_english_adjective_lemmas)


if __name__ == "__main__":
    main()
