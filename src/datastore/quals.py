#!/usr/bin/python3

import datetime
import json
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Integer, Text, ForeignKey, TIMESTAMP, create_engine, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase, sessionmaker
from sqlalchemy.sql import func

# project imports
import constants
from datastore.benchmarks import Base, Model

class QualTest(Base):
    __tablename__ = 'qual_test'

    codename: Mapped[str] = mapped_column(String, primary_key=True)
    displayname: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    runs: Mapped[List['QualRun']] = relationship(back_populates='qual_test', lazy='noload')
    topics: Mapped[List['QualTopic']] = relationship(back_populates='qual_test')

class QualTopic(Base):
    __tablename__ = 'qual_topic'

    topic_id: Mapped[str] = mapped_column(String, primary_key=True)
    qual_test_name: Mapped[str] = mapped_column(String, ForeignKey('qual_test.codename'))
    topic_text: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    qual_test: Mapped['QualTest'] = relationship(back_populates='topics')
    run_details: Mapped[List['QualRunDetail']] = relationship(back_populates='topic', lazy='noload')

class QualRun(Base):
    __tablename__ = 'qual_run'

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_ts: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.current_timestamp())
    model_name: Mapped[str] = mapped_column(String, ForeignKey('model.codename'))
    qual_test_name: Mapped[str] = mapped_column(String, ForeignKey('qual_test.codename'))
    avg_score: Mapped[Optional[float]] = mapped_column(Integer, nullable=True)

    # Relationships
    model: Mapped['Model'] = relationship(back_populates='qual_runs')
    qual_test: Mapped['QualTest'] = relationship(back_populates='runs')
    run_details: Mapped[List['QualRunDetail']] = relationship(back_populates='run', lazy='noload')

class QualRunDetail(Base):
    __tablename__ = 'qual_run_detail'

    run_id: Mapped[int] = mapped_column(Integer, ForeignKey('qual_run.run_id'), primary_key=True)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey('qual_topic.topic_id'), primary_key=True)
    accuracy_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-10
    clarity_score: Mapped[int] = mapped_column(Integer, nullable=False)   # 0-10
    completeness_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-10
    eval_msec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_text: Mapped[str] = mapped_column(Text, nullable=False)
    debug_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    run: Mapped['QualRun'] = relationship(back_populates='run_details')
    topic: Mapped['QualTopic'] = relationship(back_populates='run_details')

# Add this relationship to the Model class in benchmarks.py:
# qual_runs: Mapped[List['QualRun']] = relationship(back_populates='model', lazy='noload')

def create_dev_session():
    """Create a database session for development."""
    db_path = db_path = constants.SQLITE_DB_PATH
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Session = sessionmaker(bind=engine)
    return Session()

def insert_qual_test(session, codename: str, displayname: str, description: str = None) -> tuple[bool, str]:
    """
    Insert a new qualification test into the database.

    Args:
        session: SQLAlchemy session
        codename: Identifier for the qual test
        displayname: Human-readable name of the qual test
        description: Optional description
    Returns:
        Tuple (success_boolean, message)
    """
    try:
        new_qual_test = QualTest(
            codename=codename,
            displayname=displayname,
            description=description
        )
        session.add(new_qual_test)
        session.commit()
        return True, f"Qualification test '{codename}' successfully inserted"

    except IntegrityError:
        session.rollback()
        return False, f"Qualification test '{codename}' already exists"
    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error inserting qualification test: {str(e)}"

def insert_qual_topic(session, topic_id: str, qual_test_name: str, 
                     topic_text: str) -> tuple[bool, str]:
    """
    Insert a new qualification test topic into the database.

    Args:
        session: SQLAlchemy session
        topic_id: Unique identifier for the topic
        qual_test_name: The qual test associated with the topic
        topic_text: The topic text to be analyzed
    Returns:
        Tuple (success_boolean, message)
    """
    try:
        new_topic = QualTopic(
            topic_id=topic_id,
            qual_test_name=qual_test_name,
            topic_text=topic_text
        )
        session.add(new_topic)
        session.commit()
        return True, f"Topic '{topic_id}' successfully inserted"

    except IntegrityError:
        session.rollback()
        return False, f"Topic '{topic_id}' already exists"
    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error inserting topic: {str(e)}"

def insert_qual_run(
    session, 
    model_name: str, 
    qual_test_name: str,
    avg_score: float,
    run_details: List[Dict]
) -> tuple[bool, Any]:
    """
    Insert a new qualification test run into the database.

    Args:
        session: SQLAlchemy session
        model_name: Codename of the model
        qual_test_name: Codename of the qual test
        avg_score: Average score across all topics (0-10)
        run_details: List of run details (dict with topic_id and scores)
    Returns:
        Tuple (success_boolean, run_id_or_message)
    """
    try:
        new_run = QualRun(
            model_name=model_name,
            qual_test_name=qual_test_name,
            avg_score=avg_score
        )
        session.add(new_run)
        session.flush()

        if run_details:
            for detail in run_details:
                run_detail = QualRunDetail(
                    run_id=new_run.run_id,
                    topic_id=detail['topic_id'],
                    accuracy_score=detail['accuracy_score'],
                    clarity_score=detail['clarity_score'],
                    completeness_score=detail['completeness_score'],
                    eval_msec=detail.get('eval_msec'),
                    response_text=detail['response_text'],
                    evaluation_text=detail['evaluation_text'],
                    debug_json=detail.get('debug_json')
                )
                session.add(run_detail)

        session.commit()
        return True, new_run.run_id

    except IntegrityError:
        session.rollback()
        return False, "Error: Invalid model or qual test name"
    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error inserting run: {str(e)}"

def list_all_qual_tests(session) -> List[Dict]:
    """
    List all qualification tests in the database.
    
    Args:
        session: SQLAlchemy session
    Returns:
        List of qual test details
    """
    qual_tests = session.query(QualTest).all()
    return [
        {
            'codename': test.codename,
            'displayname': test.displayname,
            'description': test.description
        }
        for test in qual_tests
    ]
