#!/usr/bin/env python3

"""
Base module for generating word forms (nouns, verbs, adjectives) across different languages.

This module provides a unified framework to reduce code duplication across
language-specific form generation scripts.
"""

import argparse
import logging
import time
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass

from wordfreq.translation.client import LinguisticClient
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.storage.connection_pool import get_session
import constants

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class FormGenerationConfig:
    """Configuration for language and POS-specific form generation."""

    language_code: str  # e.g., 'fr', 'es', 'pt', 'de', 'en'
    language_name: str  # e.g., 'French', 'Spanish'
    pos_type: str  # e.g., 'noun', 'verb', 'adjective'
    form_mapping: Dict[str, GrammaticalForm]  # Maps form names to GrammaticalForm enums
    client_method_name: str  # Name of the LinguisticClient method to call
    min_forms_threshold: int  # Minimum number of forms to consider complete
    base_form_identifier: str  # Form name that should be marked as base form
    use_legacy_translation: bool = False  # Use old schema (e.g., french_translation column)
    translation_field_name: Optional[str] = None  # Field name for legacy translation (e.g., 'french_translation')
    detect_number_type: bool = True  # Detect plurale_tantum/singulare_tantum for nouns
    extract_gender: bool = False  # Extract grammatical gender from forms (for gendered languages)


def get_lemmas_with_translation(
    db_path: str,
    config: FormGenerationConfig,
    limit: Optional[int] = None
) -> List[Dict]:
    """
    Get lemmas with translations for a specific language and POS type.

    Supports both legacy schema (direct translation column) and new schema
    (LemmaTranslation table).

    Args:
        db_path: Path to the database
        config: FormGenerationConfig with language and POS settings
        limit: Optional limit on number of lemmas

    Returns:
        List of dictionaries with lemma information
    """
    session = get_session(db_path)

    if config.use_legacy_translation:
        # Old schema: direct translation column on Lemma table
        translation_column = getattr(linguistic_db.Lemma, config.translation_field_name)
        query = session.query(linguistic_db.Lemma).filter(
            linguistic_db.Lemma.pos_type == config.pos_type,
            translation_column.isnot(None),
            translation_column != ""
        ).order_by(linguistic_db.Lemma.frequency_rank)

        if limit:
            query = query.limit(limit)

        results = []
        for lemma in query.all():
            translation = getattr(lemma, config.translation_field_name)
            results.append({
                "id": lemma.id,
                "english": lemma.lemma_text,
                config.language_code: translation,
                "pos_subtype": lemma.pos_subtype
            })
        return results
    else:
        # New schema: LemmaTranslation table
        query = session.query(linguistic_db.Lemma).join(
            linguistic_db.LemmaTranslation,
            (linguistic_db.Lemma.id == linguistic_db.LemmaTranslation.lemma_id) &
            (linguistic_db.LemmaTranslation.language_code == config.language_code)
        ).filter(
            linguistic_db.Lemma.pos_type == config.pos_type
        ).order_by(linguistic_db.Lemma.frequency_rank)

        if limit:
            query = query.limit(limit)

        results = []
        for lemma in query.all():
            translation = session.query(linguistic_db.LemmaTranslation).filter(
                linguistic_db.LemmaTranslation.lemma_id == lemma.id,
                linguistic_db.LemmaTranslation.language_code == config.language_code
            ).first()

            if translation:
                results.append({
                    "id": lemma.id,
                    "english": lemma.lemma_text,
                    config.language_code: translation.translation,
                    "pos_subtype": lemma.pos_subtype
                })

        return results


def get_lemmas_without_translation(
    db_path: str,
    pos_type: str,
    limit: Optional[int] = None
) -> List[Dict]:
    """
    Get lemmas without requiring translations (e.g., for English forms).

    Args:
        db_path: Path to the database
        pos_type: Part of speech type (e.g., 'verb', 'noun')
        limit: Optional limit on number of lemmas

    Returns:
        List of dictionaries with lemma information
    """
    session = get_session(db_path)

    query = session.query(linguistic_db.Lemma).filter(
        linguistic_db.Lemma.pos_type == pos_type
    ).order_by(linguistic_db.Lemma.frequency_rank)

    if limit:
        query = query.limit(limit)

    return [
        {
            "id": lemma.id,
            "english": lemma.lemma_text,
            "pos_subtype": lemma.pos_subtype,
            "frequency_rank": lemma.frequency_rank
        }
        for lemma in query.all()
    ]


def detect_number_type_from_forms(forms_dict: Dict[str, str], config: FormGenerationConfig) -> str:
    """
    Detect if a noun is plurale tantum, singulare tantum, or regular.

    Args:
        forms_dict: Dictionary of form names to form texts
        config: Configuration with form mappings

    Returns:
        One of: 'plurale_tantum', 'singulare_tantum', or 'regular'
    """
    # Only detect for nouns and adjectives, not verbs
    if config.pos_type not in ["noun", "adjective"]:
        return "regular"

    # Identify which forms are singular vs plural based on form names
    singular_forms = [name for name in forms_dict.keys() if "singular" in name.lower()]
    plural_forms = [name for name in forms_dict.keys() if "plural" in name.lower()]

    # Check if we have non-empty forms
    has_singular = any(forms_dict.get(f) and forms_dict.get(f).strip() for f in singular_forms)
    has_plural = any(forms_dict.get(f) and forms_dict.get(f).strip() for f in plural_forms)

    if has_plural and not has_singular:
        return "plurale_tantum"
    elif has_singular and not has_plural:
        return "singulare_tantum"
    else:
        return "regular"


def extract_gender_from_forms(forms_dict: Dict[str, str], config: FormGenerationConfig) -> Optional[str]:
    """
    Extract grammatical gender from form names.

    For languages like French that have gendered forms (singular_m, singular_f),
    we can infer the gender by checking which gender forms are populated.

    Args:
        forms_dict: Dictionary of form names to form texts
        config: Configuration with form mappings

    Returns:
        One of: 'masculine', 'feminine', 'neuter', or None if cannot be determined
    """
    # Only extract for nouns and adjectives
    if config.pos_type not in ["noun", "adjective"]:
        return None

    # Check for gender markers in form names
    masculine_forms = [name for name in forms_dict.keys() if "_m" in name.lower()]
    feminine_forms = [name for name in forms_dict.keys() if "_f" in name.lower()]
    neuter_forms = [name for name in forms_dict.keys() if "_n" in name.lower()]

    # Count non-empty forms for each gender
    has_masculine = any(forms_dict.get(f) and forms_dict.get(f).strip() for f in masculine_forms)
    has_feminine = any(forms_dict.get(f) and forms_dict.get(f).strip() for f in feminine_forms)
    has_neuter = any(forms_dict.get(f) and forms_dict.get(f).strip() for f in neuter_forms)

    # If only one gender has forms, that's the word's gender
    gender_count = sum([has_masculine, has_feminine, has_neuter])

    if gender_count == 1:
        if has_masculine:
            return "masculine"
        elif has_feminine:
            return "feminine"
        elif has_neuter:
            return "neuter"

    # If multiple genders or no gender markers, return None
    return None


def process_lemma_forms(
    client: LinguisticClient,
    lemma_id: int,
    db_path: str,
    config: FormGenerationConfig
) -> bool:
    """
    Process and store forms for a single lemma.

    Args:
        client: LinguisticClient instance
        lemma_id: ID of the lemma to process
        db_path: Path to the database
        config: FormGenerationConfig with language and form settings

    Returns:
        True if successful, False otherwise
    """
    session = get_session(db_path)

    try:
        lemma = session.query(linguistic_db.Lemma).filter(
            linguistic_db.Lemma.id == lemma_id
        ).first()

        if not lemma:
            logger.error(f"Lemma ID {lemma_id} not found")
            return False

        # Check if forms already exist
        existing_forms = session.query(linguistic_db.DerivativeForm).filter(
            linguistic_db.DerivativeForm.lemma_id == lemma_id,
            linguistic_db.DerivativeForm.language_code == config.language_code
        ).all()

        # Count existing forms that match our form mapping
        existing_count = sum(
            1 for f in existing_forms
            if f.grammatical_form in [g.value for g in config.form_mapping.values()]
        )

        if existing_count >= config.min_forms_threshold:
            logger.info(
                f"Lemma ID {lemma_id} already has {existing_count} "
                f"{config.language_name} forms, skipping"
            )
            return True

        # Query forms using the specified client method
        client_method = getattr(client, config.client_method_name)
        forms_dict, success = client_method(lemma_id)

        if not success or not forms_dict:
            logger.error(f"Failed to get forms for lemma ID {lemma_id}")
            return False

        # Store each form
        stored = 0
        for form_name, form_text in forms_dict.items():
            if form_name not in config.form_mapping:
                logger.debug(f"Unknown form name: {form_name}, skipping")
                continue

            if not form_text or not form_text.strip():
                logger.debug(f"Skipping empty form: {form_name}")
                continue

            # Get or create word token
            word_token = linguistic_db.add_word_token(
                session, form_text, config.language_code
            )

            # Create derivative form
            session.add(linguistic_db.DerivativeForm(
                lemma_id=lemma_id,
                derivative_form_text=form_text,
                word_token_id=word_token.id,
                language_code=config.language_code,
                grammatical_form=config.form_mapping[form_name].value,
                is_base_form=(form_name == config.base_form_identifier),
                verified=False
            ))
            stored += 1

        # Detect and store grammatical properties
        # Detect number type (plurale_tantum, singulare_tantum) for nouns
        if config.detect_number_type:
            number_type = detect_number_type_from_forms(forms_dict, config)
            if number_type != "regular":
                grammar_fact = linguistic_db.add_grammar_fact(
                    session,
                    lemma_id=lemma_id,
                    language_code=config.language_code,
                    fact_type="number_type",
                    fact_value=number_type,
                    notes=f"Detected during {config.pos_type} form generation",
                    verified=False
                )
                if grammar_fact:
                    logger.info(f"Added grammar_fact for lemma ID {lemma_id}: number_type={number_type}")
                else:
                    logger.debug(f"Grammar fact for number_type={number_type} already exists for lemma ID {lemma_id}")

        # Extract and store grammatical gender for gendered languages
        if config.extract_gender:
            gender = extract_gender_from_forms(forms_dict, config)
            if gender:
                grammar_fact = linguistic_db.add_grammar_fact(
                    session,
                    lemma_id=lemma_id,
                    language_code=config.language_code,
                    fact_type="gender",
                    fact_value=gender,
                    notes=f"Extracted from {config.pos_type} forms",
                    verified=False
                )
                if grammar_fact:
                    logger.info(f"Added grammar_fact for lemma ID {lemma_id}: gender={gender}")
                else:
                    logger.debug(f"Grammar fact for gender={gender} already exists for lemma ID {lemma_id}")

        session.commit()
        logger.info(f"Added {stored} forms for lemma ID {lemma_id}")
        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Error processing lemma ID {lemma_id}: {e}", exc_info=True)
        return False


def run_form_generation(
    config: FormGenerationConfig,
    get_lemmas_func: Callable
):
    """
    Main entry point for form generation scripts.

    Args:
        config: FormGenerationConfig with language and form settings
        get_lemmas_func: Function to retrieve lemmas (takes db_path and limit)
    """
    parser = argparse.ArgumentParser(
        description=f"Generate {config.language_name} {config.pos_type} forms"
    )
    parser.add_argument("--limit", type=int, help="Limit number of lemmas")
    parser.add_argument("--throttle", type=float, default=1.0,
                       help="Seconds between calls")
    parser.add_argument("--db-path", type=str, default=constants.WORDFREQ_DB_PATH)
    parser.add_argument("--model", type=str, default="gpt-5-mini")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--yes", "-y", action="store_true",
                       help="Skip confirmation prompt")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Get lemmas
    logger.info(f"Fetching {config.language_name} {config.pos_type} lemmas...")
    lemmas = get_lemmas_func(args.db_path, args.limit)
    logger.info(f"Found {len(lemmas)} lemmas to process")

    if not lemmas:
        logger.warning("No lemmas found")
        return

    # Confirmation prompt
    if not args.yes:
        print(f"\n{'='*60}")
        print(f"Ready to process {len(lemmas)} {config.pos_type}s")
        print(f"Language: {config.language_name} ({config.language_code})")
        print(f"Model: {args.model}")
        print(f"Throttle: {args.throttle}s between calls")
        print(f"{'='*60}")
        if input("\nContinue? [y/N]: ").lower() not in ["y", "yes"]:
            print("Aborted.")
            return

    # Initialize client and process
    client = LinguisticClient(model=args.model, db_path=args.db_path, debug=args.debug)
    successful = failed = 0

    for i, lemma_info in enumerate(lemmas, 1):
        # Format log message based on available fields
        english = lemma_info.get("english", lemma_info.get("verb", "unknown"))
        translation = lemma_info.get(config.language_code, "")

        if translation:
            logger.info(f"\n[{i}/{len(lemmas)}] {english} -> {translation}")
        else:
            logger.info(f"\n[{i}/{len(lemmas)}] {english}")

        if process_lemma_forms(client, lemma_info["id"], args.db_path, config):
            successful += 1
        else:
            failed += 1

        if i < len(lemmas):
            time.sleep(args.throttle)

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Processing complete:")
    logger.info(f"  Total: {len(lemmas)}")
    logger.info(f"  Successful: {successful}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"{'='*60}")
