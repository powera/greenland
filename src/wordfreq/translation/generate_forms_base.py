#!/usr/bin/env python3

"""
Base module for generating word forms (nouns, verbs, adjectives) across different languages.

This module provides a unified framework to reduce code duplication across
language-specific form generation scripts.
"""

import argparse
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.exc import OperationalError

import constants
from agents.common.common_args import get_data_source_config
from wordfreq.storage import database as linguistic_db
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.storage.connection_pool import get_session
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.translation.client import LinguisticClient

# Retry settings for transient SQLite errors (e.g., database locked)
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds, doubles each retry

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
    translation_field_name: Optional[str] = (
        None  # Field name for legacy translation (e.g., 'french_translation')
    )
    detect_number_type: bool = True  # Detect plurale_tantum/singulare_tantum for nouns
    extract_gender: bool = False  # Extract grammatical gender from forms (for gendered languages)


def get_lemmas_with_translation(
    config: DataSourceConfig, form_config: FormGenerationConfig, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get lemmas with translations for a specific language and POS type.

    Supports both legacy schema (direct translation column) and new schema
    (LemmaTranslation table).

    Args:
        config: DataSourceConfig with database configuration
        form_config: FormGenerationConfig with language and POS settings
        limit: Optional limit on number of lemmas

    Returns:
        List of dictionaries with lemma information
    """
    session = get_session(config)

    if form_config.use_legacy_translation:
        # Old schema: direct translation column on Lemma table
        translation_column = getattr(linguistic_db.Lemma, form_config.translation_field_name or "")
        query = (
            session.query(linguistic_db.Lemma)
            .filter(
                linguistic_db.Lemma.pos_type == form_config.pos_type,
                translation_column.isnot(None),
                translation_column != "",
            )
            .order_by(linguistic_db.Lemma.frequency_rank)
        )

        if limit:
            query = query.limit(limit)

        results = []
        for lemma in query.all():
            translation = getattr(lemma, form_config.translation_field_name or "")
            results.append(
                {
                    "id": lemma.id,
                    "english": lemma.lemma_text,
                    form_config.language_code: translation,
                    "pos_subtype": lemma.pos_subtype,
                }
            )
        return results
    else:
        # New schema: LemmaTranslation table
        query = (
            session.query(linguistic_db.Lemma)
            .join(
                linguistic_db.LemmaTranslation,
                (linguistic_db.Lemma.id == linguistic_db.LemmaTranslation.lemma_id)
                & (linguistic_db.LemmaTranslation.language_code == form_config.language_code),
            )
            .filter(linguistic_db.Lemma.pos_type == form_config.pos_type)
            .order_by(linguistic_db.Lemma.frequency_rank)
        )

        if limit:
            query = query.limit(limit)

        results = []
        for lemma in query.all():
            translation = (
                session.query(linguistic_db.LemmaTranslation)
                .filter(
                    linguistic_db.LemmaTranslation.lemma_id == lemma.id,
                    linguistic_db.LemmaTranslation.language_code == form_config.language_code,
                )
                .first()
            )

            if translation:
                results.append(
                    {
                        "id": lemma.id,
                        "english": lemma.lemma_text,
                        form_config.language_code: translation.translation,
                        "pos_subtype": lemma.pos_subtype,
                    }
                )

        return results


def get_lemmas_without_translation(
    config: DataSourceConfig, pos_type: str, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get lemmas without requiring translations (e.g., for English forms).

    Args:
        config: DataSourceConfig with database configuration
        pos_type: Part of speech type (e.g., 'verb', 'noun')
        limit: Optional limit on number of lemmas

    Returns:
        List of dictionaries with lemma information
    """
    session = get_session(config)

    query = (
        session.query(linguistic_db.Lemma)
        .filter(linguistic_db.Lemma.pos_type == pos_type)
        .order_by(linguistic_db.Lemma.frequency_rank)
    )

    if limit:
        query = query.limit(limit)

    return [
        {
            "id": lemma.id,
            "english": lemma.lemma_text,
            "pos_subtype": lemma.pos_subtype,
            "frequency_rank": lemma.frequency_rank,
        }
        for lemma in query.all()
    ]


def get_lemmas_needing_forms(
    config: DataSourceConfig, form_config: FormGenerationConfig, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get lemmas that need forms generated (those with insufficient derivative forms).

    Args:
        config: DataSourceConfig with database configuration
        form_config: FormGenerationConfig with language and POS settings
        limit: Optional limit on number of lemmas

    Returns:
        List of dictionaries with lemma information
    """
    session = get_session(config)

    # Get all lemmas of the specified POS type
    query = (
        session.query(linguistic_db.Lemma)
        .filter(linguistic_db.Lemma.pos_type == form_config.pos_type)
        .order_by(linguistic_db.Lemma.frequency_rank)
    )

    results = []
    for lemma in query.all():
        # Count existing derivative forms for this lemma in the target language
        form_count = (
            session.query(linguistic_db.DerivativeForm)
            .filter(
                linguistic_db.DerivativeForm.lemma_id == lemma.id,
                linguistic_db.DerivativeForm.language_code == form_config.language_code,
            )
            .count()
        )

        # If forms are below threshold, this lemma needs forms generated
        if form_count <= form_config.min_forms_threshold:
            results.append(
                {
                    "id": lemma.id,
                    "english": lemma.lemma_text,
                    "pos_subtype": lemma.pos_subtype,
                    "frequency_rank": lemma.frequency_rank,
                    "current_form_count": form_count,
                }
            )

            # Check if we've reached the limit
            if limit and len(results) >= limit:
                break

    return results


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
    def has_non_empty_form(form_name: str) -> bool:
        form_text = forms_dict.get(form_name)
        return bool(form_text and isinstance(form_text, str) and form_text.strip())

    has_singular = any(has_non_empty_form(f) for f in singular_forms)
    has_plural = any(has_non_empty_form(f) for f in plural_forms)

    if has_plural and not has_singular:
        return "plurale_tantum"
    elif has_singular and not has_plural:
        return "singulare_tantum"
    else:
        return "regular"


def extract_gender_from_forms(
    forms_dict: Dict[str, str], config: FormGenerationConfig
) -> Optional[str]:
    """
    Extract grammatical gender from form data.

    Two strategies are used:
    1. Form key inspection: For forms with gendered keys (e.g., singular_m,
       singular_f), infer gender by checking which gender forms are populated.
    2. Article detection: For noun forms whose keys are ungendered (e.g.,
       singular/plural), infer gender from the article in the singular form
       text (e.g., "il gatto" → masculine, "het huis" → neuter).

    Args:
        forms_dict: Dictionary of form names to form texts
        config: Configuration with form mappings

    Returns:
        One of: 'masculine', 'feminine', 'neuter', or None if cannot be determined
    """
    # Only extract for nouns and adjectives
    if config.pos_type not in ["noun", "adjective"]:
        return None

    # Strategy 1: Check for gender markers in form key names
    masculine_forms = [name for name in forms_dict.keys() if "_m" in name.lower()]
    feminine_forms = [name for name in forms_dict.keys() if "_f" in name.lower()]
    neuter_forms = [name for name in forms_dict.keys() if "_n" in name.lower()]

    # Count non-empty forms for each gender
    def has_non_empty_form(form_name: str) -> bool:
        form_text = forms_dict.get(form_name)
        return bool(form_text and isinstance(form_text, str) and form_text.strip())

    has_masculine = any(has_non_empty_form(f) for f in masculine_forms)
    has_feminine = any(has_non_empty_form(f) for f in feminine_forms)
    has_neuter = any(has_non_empty_form(f) for f in neuter_forms)

    # If only one gender has forms, that's the word's gender
    gender_count = sum([has_masculine, has_feminine, has_neuter])

    if gender_count == 1:
        if has_masculine:
            return "masculine"
        elif has_feminine:
            return "feminine"
        elif has_neuter:
            return "neuter"

    # Strategy 2: Detect gender from articles in the singular form text.
    # This works for noun forms where keys are just "singular"/"plural"
    # (or case-based like "nominative_singular") and the LLM includes the
    # article in the form text.
    if config.pos_type == "noun":
        gender = _detect_gender_from_article(forms_dict, config.language_code)
        if gender:
            return gender

    # If no gender could be determined, return None
    return None


# Per-language article → gender mappings for singular nouns.
# Each entry is (lowercase_article, gender).  Order matters: longer / more
# specific articles should come first so that "gli" is tried before "i", etc.
_ARTICLE_GENDER_MAP: Dict[str, List[Tuple[str, Optional[str]]]] = {
    "it": [
        ("lo ", "masculine"),
        ("il ", "masculine"),
        ("l'", "masculine"),  # ambiguous, but masculine more common; see below
        ("la ", "feminine"),
        ("gli ", "masculine"),  # plural masculine, useful as fallback
        ("le ", "feminine"),  # plural feminine
        ("i ", "masculine"),  # plural masculine
    ],
    "nl": [
        ("het ", "neuter"),
        ("de ", "common"),
    ],
    "fr": [
        ("le ", "masculine"),
        ("la ", "feminine"),
        ("l'", None),  # ambiguous — skip
        ("les ", None),  # plural — skip
    ],
    "es": [
        ("el ", "masculine"),
        ("la ", "feminine"),
        ("los ", "masculine"),  # plural masculine
        ("las ", "feminine"),  # plural feminine
    ],
    "pt": [
        ("o ", "masculine"),
        ("a ", "feminine"),
        ("os ", "masculine"),  # plural masculine
        ("as ", "feminine"),  # plural feminine
    ],
    "de": [
        ("der ", "masculine"),
        ("die ", "feminine"),  # also plural, but singular first
        ("das ", "neuter"),
    ],
}


def _detect_gender_from_article(forms_dict: Dict[str, str], language_code: str) -> Optional[str]:
    """Infer gender from the article prefixing a singular noun form.

    The LLM prompts ask for forms with articles (e.g. "il gatto", "het huis").
    We look at the singular form text (trying several key names) and match the
    leading article against a per-language table.

    Returns 'masculine', 'feminine', 'neuter', 'common', or None.
    """
    if language_code not in _ARTICLE_GENDER_MAP:
        return None

    # Try to find a singular form to inspect
    singular_keys = [
        "singular",
        "nominative_singular",
    ]
    singular_text: Optional[str] = None
    for key in singular_keys:
        candidate = forms_dict.get(key)
        if candidate and isinstance(candidate, str) and candidate.strip():
            singular_text = candidate.strip().lower()
            break

    if not singular_text:
        return None

    for article, gender in _ARTICLE_GENDER_MAP[language_code]:
        if singular_text.startswith(article):
            return gender

    # Italian l' is ambiguous; try the plural to disambiguate
    if language_code == "it" and singular_text.startswith("l'"):
        plural_text = forms_dict.get("plural")
        if plural_text and isinstance(plural_text, str):
            plural_lower = plural_text.strip().lower()
            if plural_lower.startswith("gli ") or plural_lower.startswith("i "):
                return "masculine"
            elif plural_lower.startswith("le "):
                return "feminine"

    return None


def _commit_with_retry(session: Any, lemma_id: int) -> None:
    """Commit with retry logic for transient SQLite errors (e.g., database locked)."""
    for attempt in range(MAX_RETRIES):
        try:
            session.commit()
            return
        except OperationalError as e:
            session.rollback()
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning(
                    f"Database locked on commit for lemma ID {lemma_id}, "
                    f"retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                )
                time.sleep(delay)
            else:
                raise


def process_lemma_forms(
    client: LinguisticClient,
    lemma_id: int,
    data_config: DataSourceConfig,
    form_config: FormGenerationConfig,
) -> bool:
    """
    Process and store forms for a single lemma.

    Args:
        client: LinguisticClient instance
        lemma_id: ID of the lemma to process
        data_config: DataSourceConfig with database configuration
        form_config: FormGenerationConfig with language and form settings

    Returns:
        True if successful, False otherwise
    """
    session = get_session(data_config)

    try:
        lemma = (
            session.query(linguistic_db.Lemma).filter(linguistic_db.Lemma.id == lemma_id).first()
        )

        if not lemma:
            logger.error(f"Lemma ID {lemma_id} not found")
            return False

        # Check if forms already exist - skip LLM query if they do
        existing_forms = (
            session.query(linguistic_db.DerivativeForm)
            .filter(
                linguistic_db.DerivativeForm.lemma_id == lemma_id,
                linguistic_db.DerivativeForm.language_code == form_config.language_code,
            )
            .all()
        )

        # Build set of existing grammatical forms for efficient lookup
        existing_grammatical_forms = {f.grammatical_form for f in existing_forms}
        expected_grammatical_forms = {g.value for g in form_config.form_mapping.values()}

        # Count existing forms that match our form mapping
        existing_count = len(existing_grammatical_forms & expected_grammatical_forms)

        if existing_count >= form_config.min_forms_threshold:
            logger.info(
                f"Lemma ID {lemma_id} already has {existing_count} "
                f"{form_config.language_name} forms, skipping"
            )
            return True

        # Query forms using the specified client method
        client_method = getattr(client, form_config.client_method_name)
        forms_dict, success = client_method(lemma_id)

        if not success or not forms_dict:
            logger.error(f"Failed to get forms for lemma ID {lemma_id}")
            return False

        # Store each form
        stored = 0
        skipped = 0
        for form_name, form_text in forms_dict.items():
            if form_name not in form_config.form_mapping:
                logger.debug(f"Unknown form name: {form_name}, skipping")
                continue

            if not form_text or not form_text.strip():
                logger.debug(f"Skipping empty form: {form_name}")
                continue

            # Check if this specific form already exists (using the set we built earlier)
            grammatical_form_enum = form_config.form_mapping[form_name].value
            if grammatical_form_enum in existing_grammatical_forms:
                logger.debug(f"Form {form_name} already exists for lemma ID {lemma_id}, skipping")
                skipped += 1
                continue

            # Get or create word token
            word_token = linguistic_db.add_word_token(session, form_text, form_config.language_code)

            # Create derivative form
            session.add(
                linguistic_db.DerivativeForm(
                    lemma_id=lemma_id,
                    derivative_form_text=form_text,
                    word_token_id=word_token.id,
                    language_code=form_config.language_code,
                    grammatical_form=grammatical_form_enum,
                    is_base_form=(form_name == form_config.base_form_identifier),
                    verified=False,
                )
            )
            stored += 1

        # Detect and store grammatical properties
        # Detect number type (plurale_tantum, singulare_tantum) for nouns
        if form_config.detect_number_type:
            number_type = detect_number_type_from_forms(forms_dict, form_config)
            if number_type != "regular":
                grammar_fact = linguistic_db.add_grammar_fact(
                    session,
                    lemma_id=lemma_id,
                    language_code=form_config.language_code,
                    fact_type="number_type",
                    fact_value=number_type,
                    notes=f"Detected during {form_config.pos_type} form generation",
                    verified=False,
                )
                if grammar_fact:
                    logger.info(
                        f"Added grammar_fact for lemma ID {lemma_id}: number_type={number_type}"
                    )
                else:
                    logger.debug(
                        f"Grammar fact for number_type={number_type} already exists for lemma ID {lemma_id}"
                    )

        # Extract and store grammatical gender for gendered languages
        if form_config.extract_gender:
            gender = extract_gender_from_forms(forms_dict, form_config)
            if gender:
                grammar_fact = linguistic_db.add_grammar_fact(
                    session,
                    lemma_id=lemma_id,
                    language_code=form_config.language_code,
                    fact_type="gender",
                    fact_value=gender,
                    notes=f"Extracted from {form_config.pos_type} forms",
                    verified=False,
                )
                if grammar_fact:
                    logger.info(f"Added grammar_fact for lemma ID {lemma_id}: gender={gender}")
                else:
                    logger.debug(
                        f"Grammar fact for gender={gender} already exists for lemma ID {lemma_id}"
                    )

        _commit_with_retry(session, lemma_id)
        logger.info(f"Added {stored} forms for lemma ID {lemma_id}")
        return True

    except OperationalError as oe:
        session.rollback()
        logger.error(f"Database error processing lemma ID {lemma_id}: {oe}")
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error processing lemma ID {lemma_id}: {e}", exc_info=True)
        return False


def run_form_generation(
    form_config: FormGenerationConfig,
    get_lemmas_func: Callable[[DataSourceConfig, Optional[int]], List[Dict[str, Any]]],
) -> None:
    """
    Main entry point for form generation scripts.

    Args:
        form_config: FormGenerationConfig with language and form settings
        get_lemmas_func: Function to retrieve lemmas (takes DataSourceConfig and limit)
    """
    parser = argparse.ArgumentParser(
        description=f"Generate {form_config.language_name} {form_config.pos_type} forms"
    )
    parser.add_argument("--limit", type=int, help="Limit number of lemmas")
    parser.add_argument("--throttle", type=float, default=1.0, help="Seconds between calls")
    parser.add_argument("--db-path", type=str, default=constants.WORDFREQ_DB_PATH)
    parser.add_argument("--model", type=str, default="gpt-5-mini")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Create DataSourceConfig from args
    data_config = get_data_source_config(args, default_model=args.model)

    # Get lemmas
    logger.info(f"Fetching {form_config.language_name} {form_config.pos_type} lemmas...")
    lemmas = get_lemmas_func(data_config, args.limit)
    logger.info(f"Found {len(lemmas)} lemmas to process")

    if not lemmas:
        logger.warning("No lemmas found")
        return

    # Confirmation prompt
    if not args.yes:
        print(f"\n{'='*60}")
        print(f"Ready to process {len(lemmas)} {form_config.pos_type}s")
        print(f"Language: {form_config.language_name} ({form_config.language_code})")
        print(f"Model: {data_config.model}")
        print(f"Throttle: {args.throttle}s between calls")
        print(f"{'='*60}")
        if input("\nContinue? [y/N]: ").lower() not in ["y", "yes"]:
            print("Aborted.")
            return

    # Initialize client and process
    client = LinguisticClient(config=data_config)
    successful = failed = 0

    for i, lemma_info in enumerate(lemmas, 1):
        # Format log message based on available fields
        english = lemma_info.get("english", lemma_info.get("verb", "unknown"))
        translation = lemma_info.get(form_config.language_code, "")

        if translation:
            logger.info(f"\n[{i}/{len(lemmas)}] {english} -> {translation}")
        else:
            logger.info(f"\n[{i}/{len(lemmas)}] {english}")

        if process_lemma_forms(client, lemma_info["id"], data_config, form_config):
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
