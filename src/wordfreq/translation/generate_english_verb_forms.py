#!/usr/bin/env python3

"""Batch script to generate English verb conjugations for all verbs in the database."""

from wordfreq.translation.language_forms.english import VERB_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_without_translation,
    run_form_generation,
)

CONFIG = FormGenerationConfig(
    language_code="en",
    language_name="English",
    pos_type="verb",
    form_mapping=VERB_FORM_MAPPING,
    client_method_name="query_english_verb_conjugations",
    min_forms_threshold=3,
    base_form_identifier="1s_pres",
    use_legacy_translation=False,
)


def get_english_verb_lemmas(db_path: str, limit: int = None):
    """Get all lemmas that are English verbs."""
    return get_lemmas_without_translation(db_path, "verb", limit)


def main():
    run_form_generation(CONFIG, get_english_verb_lemmas)


if __name__ == "__main__":
    main()
