#!/usr/bin/python3

"""Database models for storing linguistic information about words."""

import datetime
from typing import Dict, List, Optional, Any, Set
from sqlalchemy import String, Integer, Text, ForeignKey, TIMESTAMP, Boolean, create_engine, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase, sessionmaker
from sqlalchemy.sql import func

import constants

# Define the base class for SQLAlchemy models
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

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
    definition_text: Mapped[str] = mapped_column(Text, nullable=False)
    pos_type: Mapped[str] = mapped_column(String, nullable=False)  # Part of speech for this definition
    lemma: Mapped[str] = mapped_column(String, nullable=False)     # Lemma for this definition
    
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
    notes: Optional[str] = None
) -> Definition:
    """Add a definition for a word."""
    definition = Definition(
        word_id=word_obj.id,
        definition_text=definition_text,
        pos_type=pos_type,
        lemma=lemma,
        confidence=confidence,
        multiple_meanings=multiple_meanings,
        special_case=special_case,
        notes=notes
    )
    session.add(definition)
    session.commit()
    return definition

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

def get_common_words_by_pos(session, pos_type: str, limit: int = 50) -> List[Dict[str, Any]]:
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
    lemma: Optional[str] = None,
    confidence: Optional[float] = None,
    multiple_meanings: Optional[bool] = None,
    special_case: Optional[bool] = None,
    verified: Optional[bool] = None,
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
    if notes is not None:
        definition.notes = notes
        
    session.commit()
    return True

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

def migrate_from_old_schema(session):
    """
    Migrate data from the old schema (separate POS and lemmas) to the new schema.
    
    Args:
        session: Database session
        
    Returns:
        Dictionary with migration statistics
    """
    from sqlalchemy import Table, MetaData, inspect
    
    metadata = MetaData()
    
    # Check if old tables exist
    inspector = inspect(session.bind)
    if 'parts_of_speech' not in inspector.get_table_names() or 'lemmas' not in inspector.get_table_names():
        return {"error": "Old schema tables not found"}
        
    # Reflect the old tables
    old_pos_table = Table('parts_of_speech', metadata, autoload_with=session.bind)
    old_lemma_table = Table('lemmas', metadata, autoload_with=session.bind)
    
    # Get all words
    words = session.query(Word).all()
    stats = {
        "words_processed": 0,
        "definitions_created": 0,
        "words_with_pos_but_no_lemma": 0,
        "words_with_lemma_but_no_pos": 0
    }
    
    for word in words:
        # Get old POS and lemma entries
        old_pos_entries = session.query(old_pos_table).filter(old_pos_table.c.word_id == word.id).all()
        old_lemma_entries = session.query(old_lemma_table).filter(old_lemma_table.c.word_id == word.id).all()
        
        if not old_pos_entries and not old_lemma_entries:
            continue
        
        stats["words_processed"] += 1
        
        # Handle case where we have POS but no lemma
        if old_pos_entries and not old_lemma_entries:
            stats["words_with_pos_but_no_lemma"] += 1
            for pos in old_pos_entries:
                # Create definition with the word itself as lemma
                add_definition(
                    session,
                    word,
                    definition_text=f"Definition for {word.word} as {pos.pos_type}",
                    pos_type=pos.pos_type,
                    lemma=word.word,  # Default to the word itself
                    confidence=pos.confidence,
                    multiple_meanings=pos.multiple_meanings,
                    special_case=pos.special_case,
                    notes=pos.notes
                )
                stats["definitions_created"] += 1
        
        # Handle case where we have lemma but no POS
        elif old_lemma_entries and not old_pos_entries:
            stats["words_with_lemma_but_no_pos"] += 1
            for lemma in old_lemma_entries:
                # Create definition with generic POS
                add_definition(
                    session,
                    word,
                    definition_text=f"Definition for {word.word}",
                    pos_type=lemma.pos_type or "unknown",
                    lemma=lemma.lemma,
                    confidence=lemma.confidence,
                    notes=lemma.notes
                )
                stats["definitions_created"] += 1
        
        # Handle case where we have both POS and lemma
        else:
            # Try to match POS and lemmas that go together
            for pos in old_pos_entries:
                # Find matching lemma by POS type if possible
                matching_lemma = next(
                    (l for l in old_lemma_entries if l.pos_type == pos.pos_type), 
                    old_lemma_entries[0] if old_lemma_entries else None
                )
                
                lemma_text = matching_lemma.lemma if matching_lemma else word.word
                lemma_notes = matching_lemma.notes if matching_lemma else None
                
                # Create combined definition
                combined_notes = None
                if pos.notes and lemma_notes:
                    combined_notes = f"POS: {pos.notes}; Lemma: {lemma_notes}"
                elif pos.notes:
                    combined_notes = pos.notes
                elif lemma_notes:
                    combined_notes = lemma_notes
                
                add_definition(
                    session,
                    word,
                    definition_text=f"Definition for {word.word} as {pos.pos_type}",
                    pos_type=pos.pos_type,
                    lemma=lemma_text,
                    confidence=pos.confidence,
                    multiple_meanings=pos.multiple_meanings,
                    special_case=pos.special_case,
                    notes=combined_notes
                )
                stats["definitions_created"] += 1
    
    return stats