#!/usr/bin/env python3

"""Batch script to generate Lithuanian adverb forms for all adverbs in the database."""

from wordfreq.translation.language_forms.lithuanian import ADVERB_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_with_translation,
    run_form_generation,
)

CONFIG = FormGenerationConfig(
    language_code="lt",
    language_name="Lithuanian",
    pos_type="adverb",
    form_mapping=ADVERB_FORM_MAPPING,
    client_method_name="query_lithuanian_adverb_forms",
    min_forms_threshold=1,
    base_form_identifier="positive",
    use_legacy_translation=True,
    translation_field_name="lithuanian_translation",
    extract_gender=False,
)


def get_lithuanian_adverb_lemmas(db_path: str, limit: int = None):
    """Get all adverbs with Lithuanian translations from database."""
    return get_lemmas_with_translation(db_path, CONFIG, limit)


def process_lemma(lemma, client, db_path: str, dry_run: bool = False) -> dict:
    """
    Process a single lemma to generate Lithuanian adverb forms.

    Args:
        lemma: The lemma to process
        client: LLM client for generating forms
        db_path: Path to database
        dry_run: If True, don't save to database

    Returns:
        Dictionary with processing results
    """
    from wordfreq.translation.generate_forms_base import process_lemma_with_config

    return process_lemma_with_config(lemma, client, db_path, CONFIG, dry_run=dry_run)


def main():
    run_form_generation(CONFIG, get_lithuanian_adverb_lemmas)


if __name__ == "__main__":
    main()
