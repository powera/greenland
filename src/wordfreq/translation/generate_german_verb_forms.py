#!/usr/bin/env python3

"""Batch script to generate German verb conjugations for all verbs in the database."""

from wordfreq.translation.language_forms.german import VERB_FORM_MAPPING
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
    pos_type="verb",
    form_mapping=VERB_FORM_MAPPING,
    client_method_name="query_german_verb_conjugations",
    min_forms_threshold=20,
    base_form_identifier="1s_pres",
    use_legacy_translation=False,
)


def get_german_verb_lemmas(config: DataSourceConfig, limit: int = None):
    """Get all verbs with German translations from database."""
    return get_lemmas_with_translation(config, CONFIG, limit)


def process_lemma(client, lemma_id: int, config: DataSourceConfig) -> bool:
    """Process a single lemma to generate German verb conjugations."""
    return process_lemma_forms(client, lemma_id, config, CONFIG)


def main():
    run_form_generation(CONFIG, get_german_verb_lemmas)


if __name__ == "__main__":
    main()
