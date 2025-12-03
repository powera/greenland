#!/usr/bin/env python3

"""Batch script to generate Spanish verb conjugations for all verbs in the database."""

from wordfreq.translation.language_forms.spanish import VERB_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation,
)

CONFIG = FormGenerationConfig(
    language_code="es",
    language_name="Spanish",
    pos_type="verb",
    form_mapping=VERB_FORM_MAPPING,
    client_method_name="query_spanish_verb_conjugations",
    min_forms_threshold=20,
    base_form_identifier="1s_pres",
    use_legacy_translation=False,
)


def get_spanish_verb_lemmas(db_path: str, limit: int = None):
    """Get all verbs with Spanish translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def main():
    run_form_generation(CONFIG, get_spanish_verb_lemmas)


if __name__ == "__main__":
    main()
