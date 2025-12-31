#!/usr/bin/env python3

"""Batch script to generate German verb conjugations for all verbs in the database."""

from wordfreq.translation.language_forms.german import VERB_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation,
)

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


def get_german_verb_lemmas(db_path: str, limit: int = None):
    """Get all verbs with German translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def process_lemma(client, lemma_id: int, db_path: str) -> bool:
    """Process a single lemma to generate German verb conjugations."""
    from wordfreq.translation.generate_forms_base import process_lemma_forms as process_base
    return process_base(client, lemma_id, db_path, CONFIG)


def main():
    run_form_generation(CONFIG, get_german_verb_lemmas)


if __name__ == "__main__":
    main()
