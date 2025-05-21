#!/usr/bin/python3

"""Database models for storing linguistic information about words."""

import datetime
import enum
from typing import Dict, List, Optional, Any, Set
from sqlalchemy import String, Integer, Text, Float, ForeignKey, TIMESTAMP, Boolean, create_engine, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase, sessionmaker
from sqlalchemy.sql import func

from wordfreq.models.translations import TranslationSet
import constants


# Configure logging
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the base class for SQLAlchemy models
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Define the subtype enumerations
class NounSubtype(enum.Enum):
    """Subtypes for nouns."""
    HUMAN = "human"
    ANIMAL = "animal"
    PLANT = "plant"
    BUILDING_STRUCTURE = "building_structure"
    SMALL_MOVABLE_OBJECT = "small_movable_object"
    NATURAL_FEATURE = "natural_feature"
    TOOL_MACHINE = "tool_machine"
    MATERIAL_SUBSTANCE = "material_substance"
    CONCEPT_IDEA = "concept_idea"
    EMOTION_FEELING = "emotion_feeling"
    PROCESS_EVENT = "process_event"
    TIME_PERIOD = "time_period"
    GROUP_PEOPLE = "group_people"
    GROUP_ANIMAL = "group_animal"
    COLLECTION_THINGS = "collection_things"
    PERSONAL_NAME = "personal_name"
    PLACE_NAME = "place_name"
    ORGANIZATION_NAME = "organization_name"
    OTHER = "other"

class VerbSubtype(enum.Enum):
    """Subtypes for verbs."""
    PHYSICAL_ACTION = "physical_action"
    CREATION_ACTION = "creation_action"
    DESTRUCTION_ACTION = "destruction_action"
    MENTAL_STATE = "mental_state"
    EMOTIONAL_STATE = "emotional_state"
    POSSESSION = "possession"
    DEVELOPMENT = "development"
    CHANGE = "change"
    SPEAKING = "speaking"
    WRITING = "writing"
    EXPRESSING = "expressing"
    DIRECTIONAL_MOVEMENT = "directional_movement"
    MANNER_MOVEMENT = "manner_movement"
    OTHER = "other"

class AdjectiveSubtype(enum.Enum):
    """Subtypes for adjectives."""
    SIZE = "size"
    COLOR = "color"
    SHAPE = "shape"
    TEXTURE = "texture"
    QUALITY = "quality"
    AESTHETIC = "aesthetic"
    IMPORTANCE = "importance"
    ORIGIN = "origin"
    PURPOSE = "purpose"
    MATERIAL = "material"
    DEFINITE_QUANTITY = "definite_quantity"
    INDEFINITE_QUANTITY = "indefinite_quantity"
    DURATION = "duration"
    FREQUENCY = "frequency"
    SEQUENCE = "sequence"
    OTHER = "other"

class AdverbSubtype(enum.Enum):
    """Subtypes for adverbs."""
    STYLE = "style"
    ATTITUDE = "attitude"
    SPECIFIC_TIME = "specific_time"
    RELATIVE_TIME = "relative_time"
    DURATION = "duration"
    DIRECTION = "direction"
    LOCATION = "location"
    DISTANCE = "distance"
    INTENSITY = "intensity"
    COMPLETENESS = "completeness"
    APPROXIMATION = "approximation"
    DEFINITE_FREQUENCY = "definite_frequency"
    INDEFINITE_FREQUENCY = "indefinite_frequency"
    OTHER = "other"


class Word(Base):
    """Model for storing word information."""
    __tablename__ = 'words'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    frequency_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships - now to definitions instead of directly to POS and lemmas
    definitions = relationship("Definition", back_populates="word", cascade="all, delete-orphan")

class Definition(Base):
    """Model for storing definitions of a word."""
    __tablename__ = 'definitions'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False)
    ipa_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # IPA pronunciation
    phonetic_pronunciation: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Phonetic pronunciation
    definition_text: Mapped[str] = mapped_column(Text, nullable=False)
    pos_type: Mapped[str] = mapped_column(String, nullable=False)  # Part of speech for this definition
    pos_subtype: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Store the subtype as string for flexibility
    lemma: Mapped[str] = mapped_column(String, nullable=False)     # Lemma for this definition
    chinese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    french_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    korean_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    swahili_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lithuanian_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vietnamese_translation: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Special flags for handling complex cases (moved from POS to definition level)
    multiple_meanings: Mapped[bool] = mapped_column(Boolean, default=False)
    special_case: Mapped[bool] = mapped_column(Boolean, default=False)
    
    confidence: Mapped[float] = mapped_column(Integer, default=0.0)  # 0-1 score from LLM
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    word = relationship("Word", back_populates="definitions")
    examples = relationship("Example", back_populates="definition", cascade="all, delete-orphan")

class Example(Base):
    """Model for storing example sentences for a definition."""
    __tablename__ = 'examples'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("definitions.id"), nullable=False)
    example_text: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    
    # Relationships
    definition = relationship("Definition", back_populates="examples")

class QueryLog(Base):
    """Model for tracking LLM queries for auditing and debugging."""
    __tablename__ = 'query_logs'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String, nullable=False)
    query_type: Mapped[str] = mapped_column(String, nullable=False)  # 'definition', 'examples', etc.
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

class Corpus(Base):
    """Model for storing corpus information."""
    __tablename__ = 'corpus'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=True)
    
    # Relationships
    word_frequencies = relationship("WordFrequency", back_populates="corpus", cascade="all, delete-orphan")

class WordFrequency(Base):
    """Model for storing word frequency in different corpora."""
    __tablename__ = 'word_frequencies'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False)
    corpus_id: Mapped[int] = mapped_column(ForeignKey("corpus.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=True)
    frequency: Mapped[float] = mapped_column(Float, nullable=True)  # Optional raw frequency
    
    # Relationships
    word = relationship("Word", back_populates="frequencies")
    corpus = relationship("Corpus", back_populates="word_frequencies")

# Add relationship to Word model
Word.frequencies = relationship("WordFrequency", back_populates="word", cascade="all, delete-orphan")

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

def add_word(session, word: str, rank: Optional[int] = None) -> Word:
    """Add a word to the database if it doesn't exist, or return existing one."""
    existing = session.query(Word).filter(Word.word == word).first()
    if existing:
        # Update rank if provided and different
        if rank is not None and existing.frequency_rank != rank:
            existing.frequency_rank = rank
            session.commit()
        return existing
        
    new_word = Word(word=word, frequency_rank=rank)
    session.add(new_word)
    session.commit()
    return new_word

def add_definition(
    session, 
    word_obj: Word,
    definition_text: str,
    pos_type: str,
    lemma: str,
    confidence: float = 0.0,
    multiple_meanings: bool = False,
    special_case: bool = False,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    translations: Optional[TranslationSet] = None,
    notes: Optional[str] = None
):
    """Add a definition for a word."""
    try:
        definition = Definition(
            word_id=word_obj.id,
            definition_text=definition_text,
            pos_type=pos_type,
            lemma=lemma,
            confidence=confidence,
            multiple_meanings=multiple_meanings,
            special_case=special_case,
            ipa_pronunciation=ipa_pronunciation,
            phonetic_pronunciation=phonetic_pronunciation,
            notes=notes
        )
        
        # Add translations if provided
        if translations:
            definition.chinese_translation = translations.chinese.text if translations.chinese else None
            definition.french_translation = translations.french.text if translations.french else None
            definition.korean_translation = translations.korean.text if translations.korean else None
            definition.swahili_translation = translations.swahili.text if translations.swahili else None
            definition.lithuanian_translation = translations.lithuanian.text if translations.lithuanian else None
            definition.vietnamese_translation = translations.vietnamese.text if translations.vietnamese else None
        
        session.add(definition)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error adding definition: {e}")
        return False

def add_example(
    session,
    definition_obj: Definition,
    example_text: str
) -> Example:
    """Add an example sentence for a definition."""
    example = Example(
        definition_id=definition_obj.id,
        example_text=example_text
    )
    session.add(example)
    session.commit()
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

def get_words_needing_analysis(session, limit: int = 100) -> List[Word]:
    """Get words that need linguistic analysis (no definitions)."""
    return session.query(Word)\
        .outerjoin(Definition)\
        .filter(Definition.id == None)\
        .order_by(Word.frequency_rank)\
        .limit(limit)\
        .all()

def get_word_by_text(session, word_text: str) -> Optional[Word]:
    """Get a word from the database by its text."""
    return session.query(Word).filter(Word.word == word_text).first()

def get_all_definitions_for_word(session, word_text: str) -> List[Definition]:
    """Get all definitions for a word."""
    word = get_word_by_text(session, word_text)
    if not word:
        return []
    return word.definitions

def get_common_words_by_pos(session, pos_type: str, pos_subtype: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get the most common words for a specified part of speech.
    
    Args:
        session: Database session
        pos_type: Part of speech type to filter by
        limit: Maximum number of words to return
        
    Returns:
        List of dictionaries containing word information
    """
    # Query words with definitions of the specified part of speech, ordered by frequency rank
    if pos_subtype:
        query = session.query(Word, Definition)\
            .join(Definition)\
            .filter(Definition.pos_type == pos_type)\
            .filter(Definition.pos_subtype == pos_subtype)\
            .order_by(Word.frequency_rank)\
            .limit(limit)
    else:
        query = session.query(Word, Definition)\
            .join(Definition)\
            .filter(Definition.pos_type == pos_type)\
            .order_by(Word.frequency_rank)\
            .limit(limit)
    
    results = []
    for word, definition in query:
        results.append({
            "word": word.word,
            "rank": word.frequency_rank,
            "pos": pos_type,
            "lemma": definition.lemma,
            "definition": definition.definition_text,
            "confidence": definition.confidence,
            "multiple_meanings": definition.multiple_meanings,
            "verified": definition.verified
        })
    
    return results


def update_definition(
    session,
    definition_id: int,
    definition_text: Optional[str] = None,
    pos_type: Optional[str] = None,
    pos_subtype: Optional[str] = None,
    lemma: Optional[str] = None,
    confidence: Optional[float] = None,
    multiple_meanings: Optional[bool] = None,
    special_case: Optional[bool] = None,
    verified: Optional[bool] = None,
    ipa_pronunciation: Optional[str] = None,
    phonetic_pronunciation: Optional[str] = None,
    translations: Optional[TranslationSet] = None,
    notes: Optional[str] = None
) -> bool:
    """Update definition information."""
    definition = session.query(Definition).filter(Definition.id == definition_id).first()
    if not definition:
        return False
        
    if definition_text is not None:
        definition.definition_text = definition_text
    if pos_type is not None:
        definition.pos_type = pos_type
    if pos_subtype is not None:
        definition.pos_subtype = pos_subtype
    if lemma is not None:
        definition.lemma = lemma
    if confidence is not None:
        definition.confidence = confidence
    if multiple_meanings is not None:
        definition.multiple_meanings = multiple_meanings
    if special_case is not None:
        definition.special_case = special_case
    if verified is not None:
        definition.verified = verified
    if ipa_pronunciation is not None:
        definition.ipa_pronunciation = ipa_pronunciation
    if phonetic_pronunciation is not None:
        definition.phonetic_pronunciation = phonetic_pronunciation
    if notes is not None:
        definition.notes = notes
    
    # Update translations if provided
    if translations:
        if translations.chinese:
            definition.chinese_translation = translations.chinese.text
        if translations.french:
            definition.french_translation = translations.french.text
        if translations.korean:
            definition.korean_translation = translations.korean.text
        if translations.swahili:
            definition.swahili_translation = translations.swahili.text
        if translations.lithuanian:
            definition.lithuanian_translation = translations.lithuanian.text
        if translations.vietnamese:
            definition.vietnamese_translation = translations.vietnamese.text
        
    session.commit()
    return True

def update_korean_translation(
    session,
    definition_id: int,
    korean_translation: str
):
    """Update Korean translation for a definition."""
    return update_translation(session, definition_id, 'korean', korean_translation)

def get_definitions_without_translation(session, language: str, limit: int = 100):
    """
    Get definitions that need translations for a specific language.
    
    Args:
        session: Database session
        language: Language name (chinese, french, korean, swahili, lithuanian, vietnamese)
        limit: Maximum number of definitions to return
        
    Returns:
        List of Definition objects without the specified translation
    """
    language = language.lower()
    column_map = {
        'chinese': Definition.chinese_translation,
        'french': Definition.french_translation,
        'korean': Definition.korean_translation,
        'swahili': Definition.swahili_translation,
        'lithuanian': Definition.lithuanian_translation,
        'vietnamese': Definition.vietnamese_translation
    }
    
    if language not in column_map:
        raise ValueError(f"Unsupported language: {language}. Supported languages: {', '.join(column_map.keys())}")
    
    return session.query(Definition).filter(
        column_map[language].is_(None)
    ).limit(limit).all()

def update_translation(
    session,
    definition_id: int,
    language: str,
    translation: str
):
    """
    Update translation for a definition in a specific language.
    
    Args:
        session: Database session
        definition_id: ID of the definition to update
        language: Language name (chinese, french, korean, swahili, lithuanian, vietnamese)
        translation: Translation text
    """
    language = language.lower()
    column_map = {
        'chinese': 'chinese_translation',
        'french': 'french_translation',
        'korean': 'korean_translation',
        'swahili': 'swahili_translation',
        'lithuanian': 'lithuanian_translation',
        'vietnamese': 'vietnamese_translation'
    }
    
    if language not in column_map:
        raise ValueError(f"Unsupported language: {language}. Supported languages: {', '.join(column_map.keys())}")
    
    definition = session.query(Definition).filter_by(id=definition_id).first()
    if definition:
        setattr(definition, column_map[language], translation)
        definition.updated_at = func.now()
        session.commit()

# Legacy functions for backward compatibility
def get_definitions_without_korean_translations(session, limit: int = 100):
    """Get definitions that need Korean translations."""
    return get_definitions_without_translation(session, 'korean', limit)

def update_korean_translation(session, definition_id: int, korean_translation: str):
    """Update Korean translation for a definition."""
    return update_translation(session, definition_id, 'korean', korean_translation)

def get_definitions_without_swahili_translations(session, limit: int = 100):
    """Get definitions that need Swahili translations."""
    return get_definitions_without_translation(session, 'swahili', limit)

def update_swahili_translation(session, definition_id: int, swahili_translation: str):
    """Update Swahili translation for a definition."""
    return update_translation(session, definition_id, 'swahili', swahili_translation)

def get_definitions_without_lithuanian_translations(session, limit: int = 100):
    """Get definitions that need Lithuanian translations."""
    return get_definitions_without_translation(session, 'lithuanian', limit)

def update_lithuanian_translation(session, definition_id: int, lithuanian_translation: str):
    """Update Lithuanian translation for a definition."""
    return update_translation(session, definition_id, 'lithuanian', lithuanian_translation)

def get_definitions_without_vietnamese_translations(session, limit: int = 100):
    """Get definitions that need Vietnamese translations."""
    return get_definitions_without_translation(session, 'vietnamese', limit)

def update_vietnamese_translation(session, definition_id: int, vietnamese_translation: str):
    """Update Vietnamese translation for a definition."""
    return update_translation(session, definition_id, 'vietnamese', vietnamese_translation)

def get_definitions_without_french_translations(session, limit: int = 100):
    """Get definitions that need French translations."""
    return get_definitions_without_translation(session, 'french', limit)

def update_french_translation(session, definition_id: int, french_translation: str):
    """Update French translation for a definition."""
    return update_translation(session, definition_id, 'french', french_translation)

def get_definitions_without_chinese_translations(session, limit: int = 100):
    """Get definitions that need Chinese translations."""
    return get_definitions_without_translation(session, 'chinese', limit)

def update_chinese_translation(session, definition_id: int, chinese_translation: str):
    """Update Chinese translation for a definition."""
    return update_translation(session, definition_id, 'chinese', chinese_translation)

def get_definitions_without_subtypes(session, limit: int = 100) -> List[Definition]:
    """Get definitions that need POS subtypes."""
    return session.query(Definition)\
        .filter(Definition.pos_subtype == None)\
        .order_by(Definition.id.desc())\
        .limit(limit)\
        .all()


def get_definitions_without_pronunciation(session, limit: int = 100) -> List[Definition]:
    """Get definitions that need pronunciation information."""
    return session.query(Definition)\
        .filter(
            (Definition.ipa_pronunciation == None) | 
            (Definition.phonetic_pronunciation == None)
        )\
        .limit(limit)\
        .all()

def get_processing_stats(session) -> Dict[str, Any]:
    """Get statistics about the current processing state."""
    total_words = session.query(func.count(Word.id)).scalar()
    words_with_definitions = session.query(func.count(Word.id))\
        .join(Definition).scalar()
    
    # Count words with at least one example
    words_with_examples = session.query(func.count(Word.id))\
        .join(Definition)\
        .join(Example)\
        .scalar()
    
    # Count total definitions and examples
    total_definitions = session.query(func.count(Definition.id)).scalar()
    total_examples = session.query(func.count(Example.id)).scalar()
    
    return {
        "total_words": total_words or 0,
        "words_with_definitions": words_with_definitions or 0,
        "words_with_examples": words_with_examples or 0,
        "total_definitions": total_definitions or 0, 
        "total_examples": total_examples or 0,
        "percent_complete": (words_with_definitions / total_words * 100) if total_words else 0
    }

def list_problematic_words(session, limit: int = 100) -> List[Dict[str, Any]]:
    """List words that have been flagged as problematic (special cases, multiple meanings, etc.)."""
    query = session.query(Word).join(Definition)\
        .filter(
            (Definition.multiple_meanings == True) |
            (Definition.special_case == True)
        ).limit(limit)
    
    results = []
    for word in query:
        definitions_data = []
        for definition in word.definitions:
            examples = [example.example_text for example in definition.examples]
            
            definitions_data.append({
                "text": definition.definition_text,
                "pos": definition.pos_type,
                "lemma": definition.lemma,
                "multiple_meanings": definition.multiple_meanings,
                "special_case": definition.special_case,
                "notes": definition.notes,
                "examples": examples
            })
        
        results.append({
            "word": word.word,
            "rank": word.frequency_rank,
            "definitions": definitions_data
        })
    
    return results