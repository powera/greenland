#!/usr/bin/python3

"""Database models for storing linguistic information about words."""

import datetime
from typing import Dict, List, Optional, Any, Set
from sqlalchemy import String, Integer, Text, ForeignKey, TIMESTAMP, Boolean, create_engine, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase, sessionmaker
from sqlalchemy.sql import func

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
    
    # Relationships
    parts_of_speech = relationship("PartOfSpeech", back_populates="word", cascade="all, delete-orphan")
    lemmas = relationship("Lemma", back_populates="word", cascade="all, delete-orphan")

class PartOfSpeech(Base):
    """Model for storing part of speech information for a word."""
    __tablename__ = 'parts_of_speech'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False)
    pos_type: Mapped[str] = mapped_column(String, nullable=False)
    
    # Special flags for handling complex cases
    multiple_meanings: Mapped[bool] = mapped_column(Boolean, default=False)
    different_pos: Mapped[bool] = mapped_column(Boolean, default=False)
    special_case: Mapped[bool] = mapped_column(Boolean, default=False)
    
    confidence: Mapped[float] = mapped_column(Integer, default=0.0)  # 0-1 score from LLM
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    word = relationship("Word", back_populates="parts_of_speech")

class Lemma(Base):
    """Model for storing lemma information for a word."""
    __tablename__ = 'lemmas'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), nullable=False)
    lemma: Mapped[str] = mapped_column(String, nullable=False)
    pos_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Associated POS for this lemma
    
    confidence: Mapped[float] = mapped_column(Integer, default=0.0)  # 0-1 score from LLM
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    word = relationship("Word", back_populates="lemmas")

class QueryLog(Base):
    """Model for tracking LLM queries for auditing and debugging."""
    __tablename__ = 'query_logs'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String, nullable=False)
    query_type: Mapped[str] = mapped_column(String, nullable=False)  # 'pos', 'lemma', 'both'
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

def create_database_session(db_path: str = 'linguistics.sqlite'):
    """Create a new database session."""
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

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

def add_part_of_speech(
    session, 
    word_obj: Word, 
    pos_type: str,
    confidence: float = 0.0,
    multiple_meanings: bool = False,
    different_pos: bool = False,
    special_case: bool = False,
    notes: Optional[str] = None
) -> PartOfSpeech:
    """Add part of speech information for a word."""
    pos = PartOfSpeech(
        word_id=word_obj.id,
        pos_type=pos_type,
        confidence=confidence,
        multiple_meanings=multiple_meanings,
        different_pos=different_pos,
        special_case=special_case,
        notes=notes
    )
    session.add(pos)
    session.commit()
    return pos

def add_lemma(
    session, 
    word_obj: Word, 
    lemma: str, 
    pos_type: Optional[str] = None,
    confidence: float = 0.0,
    notes: Optional[str] = None
) -> Lemma:
    """Add lemma information for a word."""
    lemma_obj = Lemma(
        word_id=word_obj.id,
        lemma=lemma,
        pos_type=pos_type,
        confidence=confidence,
        notes=notes
    )
    session.add(lemma_obj)
    session.commit()
    return lemma_obj

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
    """Get words that need linguistic analysis (no POS or lemma info)."""
    return session.query(Word)\
        .outerjoin(PartOfSpeech)\
        .outerjoin(Lemma)\
        .filter((PartOfSpeech.id == None) | (Lemma.id == None))\
        .limit(limit)\
        .all()

def get_word_by_text(session, word_text: str) -> Optional[Word]:
    """Get a word from the database by its text."""
    return session.query(Word).filter(Word.word == word_text).first()

def get_all_pos_for_word(session, word_text: str) -> List[PartOfSpeech]:
    """Get all parts of speech for a word."""
    word = get_word_by_text(session, word_text)
    if not word:
        return []
    return word.parts_of_speech

def get_all_lemmas_for_word(session, word_text: str) -> List[Lemma]:
    """Get all lemmas for a word."""
    word = get_word_by_text(session, word_text)
    if not word:
        return []
    return word.lemmas

def update_part_of_speech(
    session,
    pos_id: int,
    pos_type: Optional[str] = None,
    confidence: Optional[float] = None,
    multiple_meanings: Optional[bool] = None,
    different_pos: Optional[bool] = None,
    special_case: Optional[bool] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None
) -> bool:
    """Update part of speech information."""
    pos = session.query(PartOfSpeech).filter(PartOfSpeech.id == pos_id).first()
    if not pos:
        return False
        
    if pos_type is not None:
        pos.pos_type = pos_type
    if confidence is not None:
        pos.confidence = confidence
    if multiple_meanings is not None:
        pos.multiple_meanings = multiple_meanings
    if different_pos is not None:
        pos.different_pos = different_pos
    if special_case is not None:
        pos.special_case = special_case
    if verified is not None:
        pos.verified = verified
    if notes is not None:
        pos.notes = notes
        
    session.commit()
    return True

def update_lemma(
    session,
    lemma_id: int,
    lemma: Optional[str] = None,
    pos_type: Optional[str] = None,
    confidence: Optional[float] = None,
    verified: Optional[bool] = None,
    notes: Optional[str] = None
) -> bool:
    """Update lemma information."""
    lemma_obj = session.query(Lemma).filter(Lemma.id == lemma_id).first()
    if not lemma_obj:
        return False
        
    if lemma is not None:
        lemma_obj.lemma = lemma
    if pos_type is not None:
        lemma_obj.pos_type = pos_type
    if confidence is not None:
        lemma_obj.confidence = confidence
    if verified is not None:
        lemma_obj.verified = verified
    if notes is not None:
        lemma_obj.notes = notes
        
    session.commit()
    return True

def get_processing_stats(session) -> Dict[str, Any]:
    """Get statistics about the current processing state."""
    total_words = session.query(func.count(Word.id)).scalar()
    words_with_pos = session.query(func.count(Word.id))\
        .join(PartOfSpeech).scalar()
    words_with_lemma = session.query(func.count(Word.id))\
        .join(Lemma).scalar()
    words_complete = session.query(func.count(Word.id))\
        .join(PartOfSpeech)\
        .join(Lemma)\
        .scalar()
    
    return {
        "total_words": total_words or 0,
        "words_with_pos": words_with_pos or 0,
        "words_with_lemma": words_with_lemma or 0, 
        "words_complete": words_complete or 0,
        "percent_complete": (words_complete / total_words * 100) if total_words else 0
    }

def list_problematic_words(session, limit: int = 100) -> List[Dict[str, Any]]:
    """List words that have been flagged as problematic (special cases, multiple meanings, etc.)."""
    query = session.query(Word).join(PartOfSpeech)\
        .filter(
            (PartOfSpeech.multiple_meanings == True) |
            (PartOfSpeech.different_pos == True) |
            (PartOfSpeech.special_case == True)
        ).limit(limit)
    
    results = []
    for word in query:
        parts_of_speech = [(pos.pos_type, pos.multiple_meanings, pos.different_pos, pos.special_case, pos.notes) 
                           for pos in word.parts_of_speech]
        lemmas = [(lemma.lemma, lemma.pos_type, lemma.notes) for lemma in word.lemmas]
        
        results.append({
            "word": word.word,
            "rank": word.frequency_rank,
            "parts_of_speech": parts_of_speech,
            "lemmas": lemmas
        })
    
    return results
