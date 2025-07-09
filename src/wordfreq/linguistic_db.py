#!/usr/bin/python3

"""Database models for storing linguistic information about words."""

import datetime
import enum
from typing import Dict, List, Optional, Any, Set
from sqlalchemy import create_engine, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func

# Import models from the models package
from wordfreq.models.schema import Base, WordToken, Lemma, DerivativeForm, ExampleSentence, Corpus, WordFrequency
from wordfreq.models.query_log import QueryLog
from wordfreq.models.enums import NounSubtype, VerbSubtype, AdjectiveSubtype, AdverbSubtype, GrammaticalForm
from wordfreq.models.translations import TranslationSet
import constants

# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# TODO: de-dupe
VALID_POS_TYPES = {
    "noun", "verb", "adjective", "adverb", "pronoun", 
    "preposition", "conjunction", "interjection", "determiner",
    "article", "numeral", "auxiliary", "modal"
}

# Helper functions to initialize corpus data
def initialize_corpora(session):
    """Create the four corpus entries if they don't exist."""
    corpora = [
        {"name": "19th_books", "description": "19th century books from Project Gutenberg"},
        {"name": "20th_books", "description": "20th century books (largely sci-fi)"},
        {"name": "subtitles", "description": "Various TV subtitles"},
        {"name": "wiki_vital", "description": "Vital 1000 Wikipedia articles from 2022"}
    ]
    
    for corpus_data in corpora:
        existing = session.query(Corpus).filter(Corpus.name == corpus_data["name"]).first()
        if not existing:
            new_corpus = Corpus(**corpus_data)
            session.add(new_corpus)
    
    session.commit()

# Helper function to get subtype enum based on POS
def get_subtype_enum(pos_type: str) -> Optional[enum.EnumMeta]:
    """Get the appropriate subtype enum class based on part of speech."""
    pos_type = pos_type.lower()
    if pos_type == 'noun':
        return NounSubtype
    elif pos_type == 'verb':
        return VerbSubtype
    elif pos_type == 'adjective':
        return AdjectiveSubtype
    elif pos_type == 'adverb':
        return AdverbSubtype
    return None

def get_subtype_values_for_pos(pos_type: str) -> List[str]:
    """
    Get all possible subtype values for a given part of speech.
    
    Args:
        pos_type: Part of speech (noun, verb, adjective, adverb)
        
    Returns:
        List of possible subtype values
    """
    enum_class = get_subtype_enum(pos_type)
    if enum_class:
        return [e.value for e in enum_class]
    return []

def get_all_pos_subtypes() -> Dict[str, List[str]]:
    """
    Get all possible POS subtypes for each part of speech.
    
    Returns:
        Dictionary with part of speech as key and list of subtypes as value
    """
    all_subtypes = set()
    all_subtypes.update(get_subtype_values_for_pos('noun'))
    all_subtypes.update(get_subtype_values_for_pos('verb'))
    all_subtypes.update(get_subtype_values_for_pos('adjective'))
    all_subtypes.update(get_subtype_values_for_pos('adverb'))
    all_subtypes.update(VALID_POS_TYPES)
    return sorted(list(all_subtypes))

def create_database_session(db_path: str = constants.WORDFREQ_DB_PATH):
    """Create a new database session."""
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

def ensure_tables_exist(session):
    """
    Ensure tables exist in the database.
    
    Args:
        session: Database session
    """
    engine = session.get_bind().engine
    Base.metadata.create_all(engine)

def add_word_token(session, token: str) -> WordToken:
    """Add a word token to the database if it doesn't exist, or return existing one."""
    existing = session.query(WordToken).filter(WordToken.token == token).first()
    if existing:
        return existing
        
    new_token = WordToken(token=token)
    session.add(new_token)
    session.commit()
    return new_token

def add_word_frequency(session, word_token: WordToken, corpus_name: str, rank: Optional[int] = None, frequency: Optional[float] = None) -> WordFrequency:
    """Add word frequency data for a word token in a specific corpus."""
    # Get or create corpus
    corpus = session.query(Corpus).filter(Corpus.name == corpus_name).first()
    if not corpus:
        corpus = Corpus(name=corpus_name)
        session.add(corpus)
        session.flush()
    
    # Check if frequency already exists
    existing = session.query(WordFrequency).filter(
        WordFrequency.word_token_id == word_token.id,
        WordFrequency.corpus_id == corpus.id
    ).first()
    
    if existing:
        # Update existing frequency
        if rank is not None:
            existing.rank = rank
        if frequency is not None:
            existing.frequency = frequency
        session.commit()
        return existing
    
    # Create new frequency record
    word_freq = WordFrequency(
        word_token_id=word_token.id,
        corpus_id=corpus.id,
        rank=rank,
        frequency=frequency
    )
    session.add(word_freq)
    session.commit()
    return word_freq

def add_lemma(
    session,
    lemma_text: str,
    definition_text: str,
    pos_type: str,
    pos_subtype: Optional[str] = None,
    confidence: float = 0.0,
    verified: bool = False,
    notes: Optional[str] = None
) -> Lemma:
    """Add or get a lemma (concept/meaning)."""
    # Check if lemma already exists with same text, definition, and POS
    existing = session.query(Lemma).filter(
        Lemma.lemma_text == lemma_text,
        Lemma.definition_text == definition_text,
        Lemma.pos_type == pos_type
    ).first()
    
    if existing:
        return existing
    
    lemma = Lemma(
        lemma_text=lemma_text,
        definition_text=definition_text,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        confidence=confidence,
        verified=verified,
        notes=notes
    )
    session.add(lemma)
    session.flush()
    return lemma

def add_derivative_form(
    session,
    word_token: WordToken,
    lemma: Lemma,
    grammatical_form: str,
    is_base_form: bool = False,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    translations: Optional[TranslationSet] = None,
    multiple_meanings: bool = False,
    special_case: bool = False,
    confidence: float = 0.0,
    verified: bool = False,
    notes: Optional[str] = None
) -> DerivativeForm:
    """Add a derivative form linking a word token to a lemma."""
    try:
        # Check if this derivative form already exists
        existing = session.query(DerivativeForm).filter(
            DerivativeForm.word_token_id == word_token.id,
            DerivativeForm.lemma_id == lemma.id,
            DerivativeForm.grammatical_form == grammatical_form
        ).first()
        
        if existing:
            return existing
        
        derivative_form = DerivativeForm(
            word_token_id=word_token.id,
            lemma_id=lemma.id,
            grammatical_form=grammatical_form,
            is_base_form=is_base_form,
            ipa_pronunciation=ipa_pronunciation,
            phonetic_pronunciation=phonetic_pronunciation,
            multiple_meanings=multiple_meanings,
            special_case=special_case,
            confidence=confidence,
            verified=verified,
            notes=notes
        )
        
        # Add translations if provided
        if translations:
            derivative_form.chinese_translation = translations.chinese.text if translations.chinese else None
            derivative_form.french_translation = translations.french.text if translations.french else None
            derivative_form.korean_translation = translations.korean.text if translations.korean else None
            derivative_form.swahili_translation = translations.swahili.text if translations.swahili else None
            derivative_form.lithuanian_translation = translations.lithuanian.text if translations.lithuanian else None
            derivative_form.vietnamese_translation = translations.vietnamese.text if translations.vietnamese else None
        
        session.add(derivative_form)
        session.flush()
        return derivative_form
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding derivative form: {e}")
        return None

def add_complete_word_entry(
    session,
    token: str,
    lemma_text: str,
    definition_text: str,
    pos_type: str,
    grammatical_form: str,
    pos_subtype: Optional[str] = None,
    is_base_form: bool = False,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    translations: Optional[TranslationSet] = None,
    multiple_meanings: bool = False,
    special_case: bool = False,
    confidence: float = 0.0,
    verified: bool = False,
    notes: Optional[str] = None
) -> DerivativeForm:
    """
    Convenience function to add a complete word entry (token + lemma + derivative form).
    This replaces the old add_definition function for most use cases.
    """
    # Add or get word token
    word_token = add_word_token(session, token)
    
    # Add or get lemma
    lemma = add_lemma(
        session=session,
        lemma_text=lemma_text,
        definition_text=definition_text,
        pos_type=pos_type,
        pos_subtype=pos_subtype,
        confidence=confidence,
        verified=verified,
        notes=notes
    )
    
    # Add derivative form
    derivative_form = add_derivative_form(
        session=session,
        word_token=word_token,
        lemma=lemma,
        grammatical_form=grammatical_form,
        is_base_form=is_base_form,
        ipa_pronunciation=ipa_pronunciation,
        phonetic_pronunciation=phonetic_pronunciation,
        translations=translations,
        multiple_meanings=multiple_meanings,
        special_case=special_case,
        confidence=confidence,
        verified=verified,
        notes=notes
    )
    
    return derivative_form

def add_example_sentence(
    session,
    derivative_form: DerivativeForm,
    example_text: str
) -> ExampleSentence:
    """Add an example sentence for a derivative form."""
    example = ExampleSentence(
        derivative_form_id=derivative_form.id,
        example_text=example_text
    )
    session.add(example)
    # Don't commit here, let the caller handle the transaction
    return example

def log_query(
    session,
    word: str,
    query_type: str,
    prompt: str,
    response: str,
    model: str,
    success: bool = True,
    error: Optional[str] = None
) -> QueryLog:
    """Log a query to the database."""
    log = QueryLog(
        word=word,
        query_type=query_type,
        prompt=prompt,
        response=response,
        model=model,
        success=success,
        error=error
    )
    session.add(log)
    session.commit()
    return log

def get_word_tokens_needing_analysis(session, limit: int = 100) -> List[WordToken]:
    """Get word tokens that need linguistic analysis (no derivative forms)."""
    return session.query(WordToken)\
        .outerjoin(DerivativeForm)\
        .filter(DerivativeForm.id == None)\
        .limit(limit)\
        .all()

def get_word_tokens_by_frequency_rank(session, corpus_name: str, limit: int = 100) -> List[WordToken]:
    """Get word tokens ordered by frequency rank in a specific corpus."""
    return session.query(WordToken)\
        .join(WordFrequency)\
        .join(Corpus)\
        .filter(Corpus.name == corpus_name)\
        .filter(WordFrequency.rank != None)\
        .order_by(WordFrequency.rank)\
        .limit(limit)\
        .all()

def get_word_token_by_text(session, token_text: str) -> Optional[WordToken]:
    """Get a word token from the database by its text."""
    return session.query(WordToken).filter(WordToken.token == token_text).first()

def get_all_derivative_forms_for_token(session, token_text: str) -> List[DerivativeForm]:
    """Get all derivative forms for a word token."""
    word_token = get_word_token_by_text(session, token_text)
    if not word_token:
        return []
    return word_token.derivative_forms

def get_all_derivative_forms_for_lemma(session, lemma_text: str, pos_type: Optional[str] = None) -> List[DerivativeForm]:
    """Get all derivative forms for a lemma."""
    query = session.query(DerivativeForm)\
        .join(Lemma)\
        .filter(Lemma.lemma_text == lemma_text)
    
    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)
    
    return query.all()

def get_base_forms_for_lemma(session, lemma_text: str, pos_type: Optional[str] = None) -> List[DerivativeForm]:
    """Get base forms for a lemma."""
    query = session.query(DerivativeForm)\
        .join(Lemma)\
        .filter(Lemma.lemma_text == lemma_text)\
        .filter(DerivativeForm.is_base_form == True)
    
    if pos_type:
        query = query.filter(Lemma.pos_type == pos_type)
    
    return query.all()

def get_common_words_by_pos(session, pos_type: str, pos_subtype: str = None, corpus_name: str = "wiki_vital", limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get the most common word tokens for a specified part of speech.
    
    Args:
        session: Database session
        pos_type: Part of speech type to filter by
        pos_subtype: Optional POS subtype to filter by
        corpus_name: Corpus to use for frequency ranking
        limit: Maximum number of words to return
        
    Returns:
        List of dictionaries containing word information
    """
    # Query word tokens with derivative forms of the specified part of speech, ordered by frequency rank
    query = session.query(WordToken, DerivativeForm, Lemma, WordFrequency)\
        .join(DerivativeForm)\
        .join(Lemma)\
        .join(WordFrequency)\
        .join(Corpus)\
        .filter(Lemma.pos_type == pos_type)\
        .filter(Corpus.name == corpus_name)\
        .filter(WordFrequency.rank != None)
    
    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)
    
    query = query.order_by(WordFrequency.rank).limit(limit)
    
    results = []
    for word_token, derivative_form, lemma, word_frequency in query:
        results.append({
            "token": word_token.token,
            "rank": word_frequency.rank,
            "pos": pos_type,
            "pos_subtype": lemma.pos_subtype,
            "lemma": lemma.lemma_text,
            "definition": lemma.definition_text,
            "grammatical_form": derivative_form.grammatical_form,
            "is_base_form": derivative_form.is_base_form,
            "confidence": derivative_form.confidence,
            "multiple_meanings": derivative_form.multiple_meanings,
            "verified": derivative_form.verified
        })
    
    return results

def get_common_base_forms_by_pos(session, pos_type: str, pos_subtype: str = None, corpus_name: str = "wiki_vital", limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get the most common base forms for a specified part of speech.
    
    Args:
        session: Database session
        pos_type: Part of speech type to filter by
        pos_subtype: Optional POS subtype to filter by
        corpus_name: Corpus to use for frequency ranking
        limit: Maximum number of words to return
        
    Returns:
        List of dictionaries containing base form information
    """
    query = session.query(WordToken, DerivativeForm, Lemma, WordFrequency)\
        .join(DerivativeForm)\
        .join(Lemma)\
        .join(WordFrequency)\
        .join(Corpus)\
        .filter(Lemma.pos_type == pos_type)\
        .filter(DerivativeForm.is_base_form == True)\
        .filter(Corpus.name == corpus_name)\
        .filter(WordFrequency.rank != None)
    
    if pos_subtype:
        query = query.filter(Lemma.pos_subtype == pos_subtype)
    
    query = query.order_by(WordFrequency.rank).limit(limit)
    
    results = []
    for word_token, derivative_form, lemma, word_frequency in query:
        results.append({
            "token": word_token.token,
            "rank": word_frequency.rank,
            "pos": pos_type,
            "pos_subtype": lemma.pos_subtype,
            "lemma": lemma.lemma_text,
            "definition": lemma.definition_text,
            "grammatical_form": derivative_form.grammatical_form,
            "confidence": derivative_form.confidence,
            "verified": derivative_form.verified
        })
    
    return results


def delete_derivative_forms_for_token(session, word_token_id: int) -> bool:
    """
    Delete all derivative forms for a word token.
    
    Args:
        session: Database session
        word_token_id: ID of the word token to delete derivative forms for
        
    Returns:
        Success flag
    """
    try:
        # Query all derivative forms for the word token
        derivative_forms = session.query(DerivativeForm).filter(DerivativeForm.word_token_id == word_token_id).all()
        
        # Delete each derivative form (cascade will handle example sentences)
        for derivative_form in derivative_forms:
            session.delete(derivative_form)
            
        # Commit the transaction
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting derivative forms for word token ID {word_token_id}: {e}")
        return False

def delete_derivative_form(session, derivative_form_id: int) -> bool:
    """
    Delete a specific derivative form.
    
    Args:
        session: Database session
        derivative_form_id: ID of the derivative form to delete
        
    Returns:
        Success flag
    """
    try:
        derivative_form = session.query(DerivativeForm).filter(DerivativeForm.id == derivative_form_id).first()
        if derivative_form:
            session.delete(derivative_form)
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting derivative form ID {derivative_form_id}: {e}")
        return False

def update_lemma(
    session,
    lemma_id: int,
    lemma_text: Optional[str] = None,
    definition_text: Optional[str] = None,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
    confidence: Optional[float] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None
) -> bool:
    """Update lemma information."""
    lemma = session.query(Lemma).filter(Lemma.id == lemma_id).first()
    if not lemma:
        return False
        
    if lemma_text is not None:
        lemma.lemma_text = lemma_text
    if definition_text is not None:
        lemma.definition_text = definition_text
    if pos_type is not None:
        lemma.pos_type = pos_type
    if pos_subtype is not None:
        lemma.pos_subtype = pos_subtype
    if confidence is not None:
        lemma.confidence = confidence
    if verified is not None:
        lemma.verified = verified
    if notes is not None:
        lemma.notes = notes
        
    session.commit()
    return True

def update_derivative_form(
    session,
    derivative_form_id: int,
    grammatical_form: Optional[str] = None,
    is_base_form: Optional[bool] = None,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    translations: Optional[TranslationSet] = None,
    multiple_meanings: Optional[bool] = None,
    special_case: Optional[bool] = None,
    confidence: Optional[float] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None
) -> bool:
    """Update derivative form information."""
    derivative_form = session.query(DerivativeForm).filter(DerivativeForm.id == derivative_form_id).first()
    if not derivative_form:
        return False
        
    if grammatical_form is not None:
        derivative_form.grammatical_form = grammatical_form
    if is_base_form is not None:
        derivative_form.is_base_form = is_base_form
    if ipa_pronunciation is not None:
        derivative_form.ipa_pronunciation = ipa_pronunciation
    if phonetic_pronunciation is not None:
        derivative_form.phonetic_pronunciation = phonetic_pronunciation
    if multiple_meanings is not None:
        derivative_form.multiple_meanings = multiple_meanings
    if special_case is not None:
        derivative_form.special_case = special_case
    if confidence is not None:
        derivative_form.confidence = confidence
    if verified is not None:
        derivative_form.verified = verified
    if notes is not None:
        derivative_form.notes = notes
    
    # Update translations if provided
    if translations:
        if translations.chinese:
            derivative_form.chinese_translation = translations.chinese.text
        if translations.french:
            derivative_form.french_translation = translations.french.text
        if translations.korean:
            derivative_form.korean_translation = translations.korean.text
        if translations.swahili:
            derivative_form.swahili_translation = translations.swahili.text
        if translations.lithuanian:
            derivative_form.lithuanian_translation = translations.lithuanian.text
        if translations.vietnamese:
            derivative_form.vietnamese_translation = translations.vietnamese.text
        
    session.commit()
    return True

def update_korean_translation(
    session,
    derivative_form_id: int,
    korean_translation: str
):
    """Update Korean translation for a derivative form."""
    return update_translation(session, derivative_form_id, 'korean', korean_translation)

def update_translation(
    session,
    derivative_form_id: int,
    language: str,
    translation_text: str
) -> bool:
    """Update translation for a specific language in a derivative form."""
    derivative_form = session.query(DerivativeForm).filter(DerivativeForm.id == derivative_form_id).first()
    if not derivative_form:
        return False
    
    language = language.lower()
    if language == 'chinese':
        derivative_form.chinese_translation = translation_text
    elif language == 'french':
        derivative_form.french_translation = translation_text
    elif language == 'korean':
        derivative_form.korean_translation = translation_text
    elif language == 'swahili':
        derivative_form.swahili_translation = translation_text
    elif language == 'lithuanian':
        derivative_form.lithuanian_translation = translation_text
    elif language == 'vietnamese':
        derivative_form.vietnamese_translation = translation_text
    else:
        return False
    
    session.commit()
    return True

def get_derivative_forms_without_translation(session, language: str, limit: int = 100):
    """
    Get derivative forms that need translations for a specific language.
    
    Args:
        session: Database session
        language: Language name (chinese, french, korean, swahili, lithuanian, vietnamese)
        limit: Maximum number of derivative forms to return
        
    Returns:
        List of DerivativeForm objects without the specified translation
    """
    language = language.lower()
    column_map = {
        'chinese': DerivativeForm.chinese_translation,
        'french': DerivativeForm.french_translation,
        'korean': DerivativeForm.korean_translation,
        'swahili': DerivativeForm.swahili_translation,
        'lithuanian': DerivativeForm.lithuanian_translation,
        'vietnamese': DerivativeForm.vietnamese_translation
    }
    
    if language not in column_map:
        raise ValueError(f"Unsupported language: {language}. Supported languages: {', '.join(column_map.keys())}")
    
    return session.query(DerivativeForm).filter(
        column_map[language].is_(None)
    ).limit(limit).all()

# Legacy functions for backward compatibility - updated to work with new schema
def get_definitions_without_korean_translations(session, limit: int = 100):
    """Get derivative forms that need Korean translations."""
    return get_derivative_forms_without_translation(session, 'korean', limit)

def get_definitions_without_swahili_translations(session, limit: int = 100):
    """Get derivative forms that need Swahili translations."""
    return get_derivative_forms_without_translation(session, 'swahili', limit)

def get_definitions_without_lithuanian_translations(session, limit: int = 100):
    """Get derivative forms that need Lithuanian translations."""
    return get_derivative_forms_without_translation(session, 'lithuanian', limit)

def get_definitions_without_vietnamese_translations(session, limit: int = 100):
    """Get derivative forms that need Vietnamese translations."""
    return get_derivative_forms_without_translation(session, 'vietnamese', limit)

def get_definitions_without_french_translations(session, limit: int = 100):
    """Get derivative forms that need French translations."""
    return get_derivative_forms_without_translation(session, 'french', limit)

def get_definitions_without_chinese_translations(session, limit: int = 100):
    """Get derivative forms that need Chinese translations."""
    return get_derivative_forms_without_translation(session, 'chinese', limit)

def update_chinese_translation(session, derivative_form_id: int, chinese_translation: str):
    """Update Chinese translation for a derivative form."""
    return update_translation(session, derivative_form_id, 'chinese', chinese_translation)

def get_lemmas_without_subtypes(session, limit: int = 100) -> List[Lemma]:
    """Get lemmas that need POS subtypes."""
    return session.query(Lemma)\
        .filter(Lemma.pos_subtype == None)\
        .order_by(Lemma.id.desc())\
        .limit(limit)\
        .all()

def get_derivative_forms_without_pronunciation(session, limit: int = 100) -> List[DerivativeForm]:
    """Get derivative forms that need pronunciation information."""
    return session.query(DerivativeForm)\
        .filter(
            (DerivativeForm.ipa_pronunciation == None) | 
            (DerivativeForm.phonetic_pronunciation == None)
        )\
        .limit(limit)\
        .all()

def get_processing_stats(session) -> Dict[str, Any]:
    """Get statistics about the current processing state."""
    total_word_tokens = session.query(func.count(WordToken.id)).scalar()
    tokens_with_derivative_forms = session.query(func.count(WordToken.id))\
        .join(DerivativeForm).scalar()
    
    # Count tokens with at least one example sentence
    tokens_with_examples = session.query(func.count(WordToken.id))\
        .join(DerivativeForm)\
        .join(ExampleSentence)\
        .scalar()
    
    # Count totals
    total_lemmas = session.query(func.count(Lemma.id)).scalar()
    total_derivative_forms = session.query(func.count(DerivativeForm.id)).scalar()
    total_example_sentences = session.query(func.count(ExampleSentence.id)).scalar()
    
    return {
        "total_word_tokens": total_word_tokens or 0,
        "tokens_with_derivative_forms": tokens_with_derivative_forms or 0,
        "tokens_with_examples": tokens_with_examples or 0,
        "total_lemmas": total_lemmas or 0,
        "total_derivative_forms": total_derivative_forms or 0, 
        "total_example_sentences": total_example_sentences or 0,
        "percent_complete": (tokens_with_derivative_forms / total_word_tokens * 100) if total_word_tokens else 0
    }

# Helper functions for working with grammatical forms
def get_derivative_forms_by_grammatical_form(session, grammatical_form: str, limit: int = 100) -> List[DerivativeForm]:
    """Get derivative forms by specific grammatical form."""
    return session.query(DerivativeForm)\
        .filter(DerivativeForm.grammatical_form == grammatical_form)\
        .limit(limit)\
        .all()

def get_base_forms_only(session, limit: int = 100) -> List[DerivativeForm]:
    """Get only base forms (infinitives, singulars, etc.)."""
    return session.query(DerivativeForm)\
        .filter(DerivativeForm.is_base_form == True)\
        .limit(limit)\
        .all()

def get_grammatical_forms_for_token(session, token_text: str) -> List[str]:
    """Get all grammatical forms available for a specific token."""
    word_token = get_word_token_by_text(session, token_text)
    if not word_token:
        return []
    
    forms = session.query(DerivativeForm.grammatical_form)\
        .filter(DerivativeForm.word_token_id == word_token.id)\
        .distinct()\
        .all()
    
    return [form[0] for form in forms]

# Legacy compatibility functions for reviewer.py
def get_word_by_text(session, word_text: str):
    """
    Legacy function for backward compatibility with reviewer.py.
    Returns a WordToken with a 'definitions' property that contains derivative forms.
    """
    word_token = get_word_token_by_text(session, word_text)
    if not word_token:
        return None
    
    # Create a wrapper object that mimics the old Word model
    class WordWrapper:
        def __init__(self, word_token):
            self.word = word_token.token
            self.frequency_rank = word_token.frequency_rank
            self._word_token = word_token
        
        @property
        def definitions(self):
            """Return derivative forms as 'definitions' for backward compatibility."""
            return self._word_token.derivative_forms
    
    return WordWrapper(word_token)

def add_example(session, definition, example_text: str):
    """
    Legacy function for backward compatibility with reviewer.py.
    'definition' is actually a DerivativeForm in the new schema.
    """
    return add_example_sentence(session, definition, example_text)

def list_problematic_words(session, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get words that have problematic flags (multiple_meanings or special_case).
    Returns data in format expected by reviewer.py.
    """
    # Query derivative forms with problematic flags
    query = session.query(WordToken, DerivativeForm, Lemma, WordFrequency)\
        .join(DerivativeForm)\
        .join(Lemma)\
        .outerjoin(WordFrequency)\
        .outerjoin(Corpus, WordFrequency.corpus_id == Corpus.id)\
        .filter(
            (DerivativeForm.multiple_meanings == True) | 
            (DerivativeForm.special_case == True)
        )\
        .filter((Corpus.name == "wiki_vital") | (Corpus.name == None))\
        .order_by(WordFrequency.rank.nullslast())\
        .limit(limit)
    
    results = []
    word_groups = {}
    
    # Group by word token
    for word_token, derivative_form, lemma, word_frequency in query:
        word_text = word_token.token
        if word_text not in word_groups:
            word_groups[word_text] = {
                'word': word_text,
                'rank': word_frequency.rank if word_frequency else None,
                'definitions': []
            }
        
        word_groups[word_text]['definitions'].append({
            'text': lemma.definition_text,
            'pos': lemma.pos_type,
            'multiple_meanings': derivative_form.multiple_meanings,
            'special_case': derivative_form.special_case
        })
    
    return list(word_groups.values())

def get_words_needing_analysis(session, limit: int = 10) -> List:
    """
    Legacy function for backward compatibility with reviewer.py.
    Returns WordToken objects that need analysis (no derivative forms).
    """
    return get_word_tokens_needing_analysis(session, limit)