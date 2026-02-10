#!/usr/bin/python3

"""
Database models for storing linguistic information about words.

This module has been refactored into smaller, focused modules.
It now serves as a backward-compatible convenience import module.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from storage.models.enums import (
    AdjectiveSubtype,
    AdverbSubtype,
    GrammaticalForm,
    NounSubtype,
    VerbSubtype,
)
from storage.models.grammar_fact import GrammarFact
from storage.models.guid_tombstone import GuidTombstone
from storage.models.query_log import QueryLog

# Import models from the models package
from storage.models.schema import (
    Base,
    Corpus,
    DerivativeForm,
    Lemma,
    LemmaTranslation,
    Sentence,
    SentenceTranslation,
    SentenceWord,
    WordFrequency,
    WordToken,
)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from storage.crud.derivative_form import (
    add_alternative_form,
    add_complete_word_entry,
    add_derivative_form,
    add_noun_derivative_form,
    delete_derivative_form,
    delete_derivative_forms_for_token,
    get_all_derivative_forms_for_lemma,
    get_all_derivative_forms_for_token,
    get_alternative_forms_for_lemma,
    get_base_forms_for_lemma,
    get_base_forms_only,
    get_derivative_forms_by_grammatical_form,
    get_derivative_forms_without_pronunciation,
    get_grammatical_forms_for_token,
    get_noun_derivative_forms,
    has_specific_noun_forms,
    update_derivative_form,
)
from storage.crud.grammar_fact import (
    add_grammar_fact,
    delete_grammar_fact,
    get_grammar_fact_value,
    get_grammar_facts,
    is_plurale_tantum,
)
from storage.crud.guid_tombstone import (
    create_tombstone,
    get_replacement_chain,
    get_tombstone_by_guid,
    get_tombstones_by_lemma_id,
    is_guid_tombstoned,
)
from storage.crud.lemma import (
    add_lemma,
    get_all_subtypes,
    get_lemma_by_guid,
    get_lemmas_by_subtype,
    get_lemmas_by_subtype_and_level,
    get_lemmas_without_subtypes,
    handle_lemma_type_subtype_change,
    update_lemma,
)
from storage.crud.sentence import (
    add_sentence,
    calculate_minimum_level,
    delete_sentence,
    get_sentence_by_id,
    get_sentences_by_level,
    update_sentence,
)
from storage.crud.sentence_translation import (
    add_sentence_translation,
    delete_sentence_translation,
    get_or_create_sentence_translation,
    get_sentence_translation,
    update_sentence_translation,
)
from storage.crud.sentence_word import (
    add_sentence_word,
    delete_sentence_word,
    find_lemma_by_guid,
    get_lemmas_for_sentence,
    get_sentence_words,
    update_sentence_word,
)
from storage.crud.word_frequency import add_word_frequency

# Import CRUD operations
from storage.crud.word_token import (
    add_word_token,
    get_word_token_by_text,
    get_word_tokens_by_combined_frequency_rank,
    get_word_tokens_by_frequency_rank,
    get_word_tokens_needing_analysis,
)

# Import legacy functions
from storage.legacy import get_word_by_text
from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.queries.noun_forms import (
    check_noun_forms_coverage,
    get_all_noun_forms,
    get_noun_form,
)

# Import query functions
from storage.queries.pos import get_common_base_forms_by_pos, get_common_words_by_pos
from storage.queries.stats import get_processing_stats, list_problematic_words
from storage.queries.translation import (
    get_definitions_without_chinese_translations,
    get_definitions_without_french_translations,
    get_definitions_without_korean_translations,
    get_definitions_without_lithuanian_translations,
    get_definitions_without_swahili_translations,
    get_definitions_without_vietnamese_translations,
    get_lemmas_without_translation,
    update_chinese_translation,
    update_korean_translation,
    update_lemma_translation,
)

# Import utilities
from storage.utils.enums import (
    VALID_POS_TYPES,
    get_all_pos_subtypes,
    get_subtype_enum,
    get_subtype_values_for_pos,
)
from storage.utils.guid import generate_guid
from storage.utils.initialization import initialize_corpora
from storage.utils.session import create_database_session, ensure_tables_exist


# Query logging function
def log_query(
    session: Session,
    word: str,
    query_type: str,
    prompt: str,
    response: str,
    model: Optional[str],
    success: bool = True,
    error: Optional[str] = None,
) -> Optional[QueryLog]:
    """Log a query to the database.

    Returns the QueryLog on success, or None if logging failed.
    On failure, rolls back the session so it remains usable by the caller.
    """
    log = QueryLog(
        word=word,
        query_type=query_type,
        prompt=prompt,
        response=response,
        model=model,
        success=success,
        error=error,
    )
    try:
        session.add(log)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning(f"Failed to log query for '{word}' ({query_type}): {e}")
        return None
    return log


# Export all public functions and classes
__all__ = [
    # Models
    "Base",
    "WordToken",
    "Lemma",
    "LemmaTranslation",
    "DerivativeForm",
    "Sentence",
    "SentenceTranslation",
    "SentenceWord",
    "Corpus",
    "WordFrequency",
    "QueryLog",
    "GrammarFact",
    "GuidTombstone",
    # Enums
    "NounSubtype",
    "VerbSubtype",
    "AdjectiveSubtype",
    "AdverbSubtype",
    "GrammaticalForm",
    # Constants
    "VALID_POS_TYPES",
    "SUBTYPE_GUID_PREFIXES",
    # Utilities
    "get_subtype_enum",
    "get_subtype_values_for_pos",
    "get_all_pos_subtypes",
    "generate_guid",
    "create_database_session",
    "ensure_tables_exist",
    "initialize_corpora",
    # Word Token CRUD
    "add_word_token",
    "get_word_token_by_text",
    "get_word_tokens_needing_analysis",
    "get_word_tokens_by_frequency_rank",
    "get_word_tokens_by_combined_frequency_rank",
    # Lemma CRUD
    "add_lemma",
    "update_lemma",
    "get_lemma_by_guid",
    "get_lemmas_without_subtypes",
    "get_all_subtypes",
    "get_lemmas_by_subtype",
    "get_lemmas_by_subtype_and_level",
    "handle_lemma_type_subtype_change",
    # Derivative Form CRUD
    "add_derivative_form",
    "update_derivative_form",
    "delete_derivative_form",
    "delete_derivative_forms_for_token",
    "get_all_derivative_forms_for_token",
    "get_all_derivative_forms_for_lemma",
    "get_base_forms_for_lemma",
    "get_derivative_forms_without_pronunciation",
    "get_derivative_forms_by_grammatical_form",
    "get_base_forms_only",
    "add_noun_derivative_form",
    "get_noun_derivative_forms",
    "has_specific_noun_forms",
    "get_grammatical_forms_for_token",
    "add_alternative_form",
    "get_alternative_forms_for_lemma",
    "add_complete_word_entry",
    # Word Frequency CRUD
    "add_word_frequency",
    # Sentence CRUD
    "add_sentence",
    "get_sentence_by_id",
    "get_sentences_by_level",
    "calculate_minimum_level",
    "update_sentence",
    "delete_sentence",
    # Sentence Translation CRUD
    "add_sentence_translation",
    "get_sentence_translation",
    "update_sentence_translation",
    "delete_sentence_translation",
    "get_or_create_sentence_translation",
    # Sentence Word CRUD
    "add_sentence_word",
    "get_sentence_words",
    "get_lemmas_for_sentence",
    "update_sentence_word",
    "delete_sentence_word",
    "find_lemma_by_guid",
    # Grammar Fact CRUD
    "add_grammar_fact",
    "get_grammar_facts",
    "get_grammar_fact_value",
    "is_plurale_tantum",
    "delete_grammar_fact",
    # GUID Tombstone CRUD
    "create_tombstone",
    "get_tombstone_by_guid",
    "get_tombstones_by_lemma_id",
    "is_guid_tombstoned",
    "get_replacement_chain",
    # POS Queries
    "get_common_words_by_pos",
    "get_common_base_forms_by_pos",
    # Translation Queries
    "get_lemmas_without_translation",
    "update_lemma_translation",
    "get_definitions_without_korean_translations",
    "get_definitions_without_swahili_translations",
    "get_definitions_without_lithuanian_translations",
    "get_definitions_without_vietnamese_translations",
    "get_definitions_without_french_translations",
    "get_definitions_without_chinese_translations",
    "update_chinese_translation",
    "update_korean_translation",
    # Stats Queries
    "get_processing_stats",
    "list_problematic_words",
    # Noun Form Queries
    "get_noun_form",
    "get_all_noun_forms",
    "check_noun_forms_coverage",
    # Legacy Functions
    "get_word_by_text",
    # Logging
    "log_query",
]
