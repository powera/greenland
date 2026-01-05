#!/usr/bin/env python3

"""Batch script to generate German noun forms for all nouns in the database."""

from wordfreq.translation.language_forms.german import NOUN_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation,
    process_lemma_forms,
)
from wordfreq.storage.backend.config import DataSourceConfig

CONFIG = FormGenerationConfig(
    language_code="de",
    language_name="German",
    pos_type="noun",
    form_mapping=NOUN_FORM_MAPPING,
    client_method_name="query_german_noun_forms",
    min_forms_threshold=2,
    base_form_identifier="singular",
    use_legacy_translation=False,
)


def get_german_noun_lemmas(config: DataSourceConfig, limit: int = None):
    """Get all nouns with German translations from database."""
    return get_lemmas_with_translation(config, CONFIG, limit)


def process_lemma(client, lemma_id: int, config: DataSourceConfig) -> bool:
    """Process a single lemma to generate German noun forms."""
    return process_lemma_forms(client, lemma_id, config, CONFIG)


def main():
    run_form_generation(CONFIG, get_german_noun_lemmas)


if __name__ == "__main__":
    main()
