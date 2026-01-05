#!/usr/bin/env python3

"""Batch script to generate English adverb forms for all adverbs in the database."""

from wordfreq.translation.language_forms.english import ADVERB_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_needing_forms,
    run_form_generation,
    process_lemma_forms,
)
from wordfreq.storage.backend.config import DataSourceConfig

CONFIG = FormGenerationConfig(
    language_code="en",
    language_name="English",
    pos_type="adverb",
    form_mapping=ADVERB_FORM_MAPPING,
    client_method_name="query_english_adverb_forms",
    min_forms_threshold=1,
    base_form_identifier="positive",
    use_legacy_translation=False,
    translation_field_name=None,  # English uses lemma_text directly
    extract_gender=False,
)


def get_english_adverb_lemmas(config: DataSourceConfig, limit: int = None):
    """Get all English adverbs from database that need forms."""
    return get_lemmas_needing_forms(config, CONFIG, limit)


def process_lemma(client, lemma_id: int, config: DataSourceConfig) -> bool:
    """Process a single lemma to generate English adverb forms."""
    return process_lemma_forms(client, lemma_id, config, CONFIG)


def main():
    run_form_generation(CONFIG, get_english_adverb_lemmas)


if __name__ == "__main__":
    main()
