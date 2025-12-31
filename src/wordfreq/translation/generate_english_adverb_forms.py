#!/usr/bin/env python3

"""Batch script to generate English adverb forms for all adverbs in the database."""

from wordfreq.translation.language_forms.english import ADVERB_FORM_MAPPING
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_needing_forms,
    run_form_generation,
)

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


def get_english_adverb_lemmas(db_path: str, limit: int = None):
    """Get all English adverbs from database that need forms."""
    return get_lemmas_needing_forms(db_path, CONFIG, limit)


def process_lemma_forms(lemma, client, db_path: str, dry_run: bool = False) -> dict:
    """
    Process a single lemma to generate English adverb forms.

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
    run_form_generation(CONFIG, get_english_adverb_lemmas)


if __name__ == "__main__":
    main()
