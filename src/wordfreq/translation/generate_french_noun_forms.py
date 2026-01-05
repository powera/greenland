#!/usr/bin/env python3

"""Batch script to generate French noun forms for all nouns in the database."""

from wordfreq.translation.language_forms.french import NOUN_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation,
    process_lemma_forms,
)
from wordfreq.storage.backend.config import DataSourceConfig

CONFIG = FormGenerationConfig(
    language_code="fr",
    language_name="French",
    pos_type="noun",
    form_mapping=NOUN_FORM_MAPPING,
    client_method_name="query_french_noun_forms",
    min_forms_threshold=2,
    base_form_identifier="singular",
    use_legacy_translation=True,
    translation_field_name="french_translation",
    extract_gender=True,
)


def get_french_noun_lemmas(config: DataSourceConfig, limit: int = None):
    """Get all nouns with French translations from database."""
    return get_lemmas_with_translation(config, CONFIG, limit)


def process_lemma(client, lemma_id: int, config: DataSourceConfig) -> bool:
    """Process a single lemma to generate French noun forms."""
    return process_lemma_forms(client, lemma_id, config, CONFIG)


def main():
    run_form_generation(CONFIG, get_french_noun_lemmas)


if __name__ == "__main__":
    main()
