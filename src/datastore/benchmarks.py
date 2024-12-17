#!/usr/bin/python3

"""Benchmark definitions and database models."""

import datetime
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import String, Integer, ForeignKey, TIMESTAMP
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from datastore.common import (
    Base, create_dev_session,
    create_database_and_session, decode_json
)

class Benchmark(Base):
    """Benchmark definition."""
    __tablename__ = 'benchmark'
    codename: Mapped[str] = mapped_column(String, primary_key=True)
    displayname: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    license_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    runs: Mapped[List['Run']] = relationship(back_populates='benchmark', lazy='noload')
    questions: Mapped[List['Question']] = relationship(back_populates='benchmark')

class Question(Base):
    """Benchmark question definition."""
    __tablename__ = 'question'

    question_id: Mapped[str] = mapped_column(String, primary_key=True)
    benchmark_name: Mapped[str] = mapped_column(String, ForeignKey('benchmark.codename'))
    question_info_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    benchmark: Mapped['Benchmark'] = relationship(back_populates='questions')
    run_details: Mapped[List['RunDetail']] = relationship(back_populates='question', lazy='noload')

class Run(Base):
    """Benchmark run results."""
    __tablename__ = 'run'
    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_ts: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.current_timestamp()
    )
    model_name: Mapped[str] = mapped_column(String, ForeignKey('model.codename'))

    benchmark_name: Mapped[str] = mapped_column(String, ForeignKey('benchmark.codename'))
    normed_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    model: Mapped['Model'] = relationship(back_populates='benchmark_runs')
    benchmark: Mapped['Benchmark'] = relationship(back_populates='runs')
    run_details: Mapped[List['RunDetail']] = relationship(back_populates='run', lazy='noload')

class RunDetail(Base):
    """Detailed results for a benchmark run."""
    __tablename__ = 'run_detail'
    run_id: Mapped[int] = mapped_column(ForeignKey('run.run_id'), primary_key=True)
    eval_msec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    debug_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    question_id: Mapped[str] = mapped_column(String, ForeignKey('question.question_id'), primary_key=True)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    run: Mapped['Run'] = relationship(back_populates='run_details')
    question: Mapped['Question'] = relationship(back_populates='run_details')

def insert_benchmark(
    session,
    codename: str,
    displayname: str,
    description: str = None,
    license_name: str = None
) -> tuple[bool, str]:
    """Insert a new benchmark into the database.

    :param session: SQLAlchemy session
    :param codename: Identifier for the benchmark
    :param displayname: Human-readable name of the benchmark
    :param description: Optional description of the benchmark
    :param license_name: Optional license information
    :return: Tuple (success_boolean, message)
    """
    try:
        new_benchmark = Benchmark(
            codename=codename,
            displayname=displayname,
            description=description,
            license_name=license_name
        )
        session.add(new_benchmark)
        session.commit()
        return True, f"Benchmark '{codename}' successfully inserted"

    except IntegrityError:
        session.rollback()
        return False, f"Benchmark '{codename}' already exists"
    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error inserting benchmark: {str(e)}"

def insert_question(
    session,
    question_id: str,
    benchmark_name: str,
    question_info_json: str = None
) -> tuple[bool, str]:
    """Insert a new question into the database.

    :param session: SQLAlchemy session
    :param question_id: A text string identifying the question
    :param benchmark_name: The benchmark associated with the question
    :param question_info_json: JSON string with the necessary information for the benchmark
    :return: Tuple (success_boolean, message)
    """
    try:
        new_question = Question(
            question_id=question_id,
            benchmark_name=benchmark_name,
            question_info_json=question_info_json
        )
        session.add(new_question)
        session.commit()
        return True, f"Question '{question_id}' successfully inserted"

    except IntegrityError:
        session.rollback()
        return False, f"Question '{question_id}' already exists"
    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error inserting question: {str(e)}"

def insert_run(
    session,
    model_name: str,
    benchmark_name: str,
    normed_score: int,
    run_details: Optional[List[Dict]] = None
) -> tuple[bool, Any]:
    """Insert a new run into the database.

    :param session: SQLAlchemy session
    :param model_name: Codename of the model
    :param benchmark_name: Codename of the benchmark
    :param normed_score: Overall score; 100=perfect, 0=random output
    :param run_details: Optional list of run details (dict with question_id and score)
    :return: Tuple (success_boolean, run_id_or_message)
    """
    try:
        new_run = Run(
            model_name=model_name,
            benchmark_name=benchmark_name,
            normed_score=normed_score,
            run_ts=func.current_timestamp()
        )
        session.add(new_run)
        session.flush()

        if run_details:
            for detail in run_details:
                run_detail = RunDetail(
                    run_id=new_run.run_id,
                    question_id=detail['question_id'],
                    score=detail.get('score'),
                    eval_msec=detail.get('eval_msec'),
                    debug_json=detail.get('debug_json')
                )
                session.add(run_detail)

        session.commit()
        return True, new_run.run_id

    except IntegrityError:
        session.rollback()
        return False, "Error: Invalid model or benchmark name"
    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error inserting run: {str(e)}"

def list_all_benchmarks(session) -> List[Dict]:
    """List all benchmarks in the database.
    
    :param session: SQLAlchemy session
    :return: List of benchmark details
    """
    benchmarks = session.query(Benchmark).all()
    return [
        {
            'codename': benchmark.codename,
            'displayname': benchmark.displayname,
            'description': benchmark.description,
            'license_name': benchmark.license_name
        }
        for benchmark in benchmarks
    ]

def load_all_questions_for_benchmark(session, benchmark_name: str) -> List[Dict]:
    """Load all questions associated with a specific benchmark.

    :param session: SQLAlchemy session
    :param benchmark_name: Codename of the benchmark
    :return: List of questions with their details
    """
    questions = (
        session.query(Question)
        .filter(Question.benchmark_name == benchmark_name)
        .all()
    )
    
    return [
        {
            'question_id': question.question_id,
            'benchmark_name': question.benchmark_name,
            'question_info_json': question.question_info_json
        } 
        for question in questions
    ]

def get_run_by_run_id(run_id: int, session=None) -> Optional[Dict]:
    """Retrieve run details for a specific run ID.

    :param run_id: ID of the run to retrieve
    :param session: Optional SQLAlchemy session (will create one if not provided)
    :return: Dictionary of run details or None if run not found
    """
    if session is None:
        session = create_dev_session()

    run = (
        session.query(Run)
        .filter(Run.run_id == run_id)
        .first()
    )

    if not run:
        return None

    run_details = (
        session.query(RunDetail, Question)
        .join(Question, RunDetail.question_id == Question.question_id)
        .filter(RunDetail.run_id == run_id)
        .all()
    )

    return {
        'run_id': run.run_id,
        'model_name': run.model_name,
        'benchmark_name': run.benchmark_name,
        'normed_score': run.normed_score,
        'run_ts': run.run_ts,
        'details': [
            {
                'question_id': detail.question_id,
                'score': detail.score,
                'eval_msec': detail.eval_msec,
                'question_info_json': decode_json(question.question_info_json),
                'debug_json': decode_json(detail.debug_json)
            }
            for detail, question in run_details
        ]
    }

def get_highest_benchmark_scores(session) -> Dict:
    """Get the highest benchmark scores for each (benchmark, model) combination with run IDs.

    :param session: SQLAlchemy session
    :return: Dict with (benchmark, model) tuple as key and dict containing score and run_id as value
    """
    highest_scores = (
        session.query(
            Run.benchmark_name,
            Run.model_name,
            Run.normed_score,
            Run.run_id
        )
        .order_by(Run.normed_score)
        .distinct(Run.benchmark_name, Run.model_name)
        .all()
    )

    return {
        (run.benchmark_name, run.model_name): {
            'score': run.normed_score,
            'run_id': run.run_id
        }
        for run in highest_scores
    }

def get_highest_scoring_run_details(
    session,
    model_name: str,
    benchmark_name: str
) -> Optional[Dict]:
    """Retrieve run details for the highest-scoring run for a specific (model, benchmark) pair.

    :param session: SQLAlchemy session
    :param model_name: Name of the model
    :param benchmark_name: Name of the benchmark
    :return: Dictionary of run details or None if no runs found
    """
    highest_run = (
        session.query(Run)
        .filter(Run.model_name == model_name)
        .filter(Run.benchmark_name == benchmark_name)
        .order_by(Run.normed_score.desc())
        .first()
    )

    if not highest_run:
        return None

    run_details = (
        session.query(RunDetail, Question)
        .join(Question, RunDetail.question_id == Question.question_id)
        .filter(RunDetail.run_id == highest_run.run_id)
        .all()
    )

    return {
        'run_id': highest_run.run_id,
        'model_name': highest_run.model_name,
        'benchmark_name': highest_run.benchmark_name,
        'normed_score': highest_run.normed_score,
        'details': [
            {
                'question_id': detail.question_id,
                'score': detail.score,
                'eval_msec': detail.eval_msec,
                'question_info_json': decode_json(question.question_info_json),
                'debug_json': decode_json(detail.debug_json)
            }
            for detail, question in run_details
        ]
    }
