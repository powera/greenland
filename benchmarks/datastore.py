#!/usr/bin/python3

import datetime
import json

from typing import List, Optional
from sqlalchemy import String, Integer, Text, ForeignKey, ForeignKeyConstraint, TIMESTAMP, create_engine, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase, sessionmaker
from sqlalchemy.sql import func

# Create a base class for declarative models
class Base(DeclarativeBase):
  pass

# Define ORM models that match the database schema
class Benchmark(Base):
    __tablename__ = 'benchmark'

    codename: Mapped[str] = mapped_column(String, primary_key=True)
    metric: Mapped[str] = mapped_column(String, primary_key=True)
    displayname: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    license_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    runs: Mapped[List['Run']] = relationship(back_populates='benchmark', lazy='noload')
    questions: Mapped[List['Question']] = relationship(back_populates='benchmark')

class Model(Base):
    __tablename__ = 'model'

    codename: Mapped[str] = mapped_column(String, primary_key=True)
    displayname: Mapped[str] = mapped_column(String, nullable=False)
    launch_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    filesize_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    license_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    runs: Mapped[List['Run']] = relationship(back_populates='model', lazy='noload')

class Question(Base):
    __tablename__ = 'question'

    question_id: Mapped[str] = mapped_column(String, primary_key=True)
    benchmark_name: Mapped[str] = mapped_column(String, ForeignKey('benchmark.codename'))
    question_info_json: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Relationships
    benchmark: Mapped['Benchmark'] = relationship(back_populates='questions')
    run_details: Mapped[List['RunDetail']] = relationship(back_populates='question', lazy='noload')

class Run(Base):
    __tablename__ = 'run'

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_ts: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.current_timestamp())
    model_name: Mapped[str] = mapped_column(String, ForeignKey('model.codename'))
    benchmark_name: Mapped[str] = mapped_column(String)
    benchmark_metric: Mapped[str] = mapped_column(String)
    normed_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
      ForeignKeyConstraint(
        ['benchmark_name', 'benchmark_metric'],
        ['benchmark.codename', 'benchmark.metric']
        ),
      )

    # Relationships
    model: Mapped['Model'] = relationship(back_populates='runs')
    benchmark: Mapped['Benchmark'] = relationship(back_populates='runs')
    run_details: Mapped[List['RunDetail']] = relationship(back_populates='run', lazy='noload')

class RunDetail(Base):
    __tablename__ = 'run_detail'

    run_id: Mapped[int] = mapped_column(Integer, ForeignKey('run.run_id'), primary_key=True)
    benchmark_name: Mapped[str] = mapped_column(String)
    benchmark_metric: Mapped[str] = mapped_column(String)
    question_id: Mapped[str] = mapped_column(String, ForeignKey('question.question_id'), primary_key=True)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eval_msec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    debug_json: Mapped[Optional[str]] = mapped_column(String)

    __table_args__ = (
      ForeignKeyConstraint(
        ['benchmark_name', 'benchmark_metric'],
        ['benchmark.codename', 'benchmark.metric']
        ),
      )

    # Relationships
    run: Mapped['Run'] = relationship(back_populates='run_details')
    question: Mapped['Question'] = relationship(back_populates='run_details')


def create_dev_session():
    db_path = "/Users/powera/repo/greenland/schema/benchmarks.db"
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Session = sessionmaker(bind=engine)
    return Session()


def create_database_and_session(db_path='benchmarks.sqlite'):
    """
    Create a SQLite database engine and session.
    
    :param db_path: Path to the SQLite database file
    :return: SQLAlchemy session
    """
    # Create engine
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create a session factory
    Session = sessionmaker(bind=engine)
    
    # Return a new session
    return Session()


def insert_benchmark(session, codename, metric, displayname, description=None, license_name=None):
    """
    Insert a new benchmark into the database.

    :param session: SQLAlchemy session
    :param codename: Identifier for the benchmark
    :param metric: The specific metric used for the benchmark
    :param displayname: Human-readable name of the benchmark
    :param description: Optional description of the benchmark
    :param license_name: Optional license information
    :return: Tuple (success_boolean, message)
    """
    try:
        # Create a new Benchmark object
        new_benchmark = Benchmark(
            codename=codename,
            metric=metric,
            displayname=displayname,
            description=description,
            license_name=license_name
        )

        # Add to session and commit
        session.add(new_benchmark)
        session.commit()

        return True, f"Benchmark '{codename}' successfully inserted"

    except IntegrityError:
        # Rollback the session in case of integrity error (e.g., duplicate primary key)
        session.rollback()
        return False, f"Benchmark '{codename}' already exists"

    except SQLAlchemyError as e:
        # Rollback and catch any other database-related errors
        session.rollback()
        return False, f"Error inserting benchmark: {str(e)}"


def insert_model(session, codename, displayname, launch_date=None, filesize_mb=None, license_name=None):
    """
    Insert a new model into the database.

    :param session: SQLAlchemy session
    :param codename: Unique identifier for the model
    :param displayname: Human-readable name of the model
    :param launch_date: Optional launch date of the model
    :param filesize_mb: Optional file size in megabytes
    :param license_name: Optional license information
    :return: Tuple (success_boolean, message)
    """
    try:
        # Create a new Model object
        new_model = Model(
            codename=codename,
            displayname=displayname,
            launch_date=launch_date,
            filesize_mb=filesize_mb,
            license_name=license_name
        )

        # Add to session and commit
        session.add(new_model)
        session.commit()

        return True, f"Model '{codename}' successfully inserted"

    except IntegrityError:
        # Rollback the session in case of integrity error (e.g., duplicate primary key)
        session.rollback()
        return False, f"Model '{codename}' already exists"

    except SQLAlchemyError as e:
        # Rollback and catch any other database-related errors
        session.rollback()
        return False, f"Error inserting model: {str(e)}"


def insert_question(session, question_id, benchmark_name, question_info_json=None):
    """
    Insert a new question into the database.

    :param session: SQLAlchemy session
    :param question_id: A text string identifying the question
    :param benchmark_name: The benchmark associated with the question.
    :param question_info_json: A json tuple with the necessary information for the benchmark.
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
        # Rollback the session in case of integrity error (e.g., duplicate primary key)
        session.rollback()
        return False, f"Question '{question_id}' already exists"

    except SQLAlchemyError as e:
        # Rollback and catch any other database-related errors
        session.rollback()
        return False, f"Error inserting question: {str(e)}"


def insert_run(session, model_name, benchmark_name, benchmark_metric, normed_score, run_ts=None, run_details=None):
    """
    Insert a new run into the database.

    :param session: SQLAlchemy session
    :param model_name: Codename of the model
    :param benchmark_name: Codename of the benchmark
    :param benchmark_metric: Specific metric of the benchmark
    :param normed_score: Overall score; 100=perfect, 0=random output
    :param run_ts: Optional run_ts timestamp (defaults to current time if None)
    :param run_details: Optional list of run details (dict with question_id and score)
    :return: Tuple (success_boolean, run_id_or_message)
    """
    try:
        # Create a new Run object
        new_run = Run(
            model_name=model_name,
            benchmark_name=benchmark_name,
            benchmark_metric=benchmark_metric,
            normed_score=normed_score,
            run_ts=run_ts or func.current_timestamp()
        )

        # Add to session
        session.add(new_run)

        # Flush to get the run_id without committing
        session.flush()

        # If run details are provided, add them
        if run_details:
            for detail in run_details:
                run_detail = RunDetail(
                    run_id=new_run.run_id,
                    benchmark_name=benchmark_name,
                    benchmark_metric=benchmark_metric,
                    question_id=detail.get('question_id'),
                    score=detail.get('score'),
                    eval_msec=detail.get('eval_msec'),
                    debug_json=detail.get('debug_json', None),  # optional
                )
                session.add(run_detail)

        # Commit the transaction
        session.commit()

        return True, new_run.run_id

    except IntegrityError:
        # Rollback the session in case of foreign key constraint violations
        session.rollback()
        return False, f"Error: Invalid model or benchmark name"

    except SQLAlchemyError as e:
        # Rollback and catch any other database-related errors
        session.rollback()
        return False, f"Error inserting run: {str(e)}"


def list_all_models(session):
    """
    List all models in the database.
    
    :param session: SQLAlchemy session
    :return: List of model details
    """
    models = session.query(Model).all()
    return [
        {
            'codename': model.codename, 
            'displayname': model.displayname,
            'launch_date': model.launch_date,
            'filesize_mb': model.filesize_mb,
            'license_name': model.license_name
        } 
        for model in models
    ]

def list_all_benchmarks(session):
    """
    List all benchmarks in the database.
    
    :param session: SQLAlchemy session
    :return: List of benchmark details
    """
    benchmarks = session.query(Benchmark).all()
    return [
        {
            'codename': benchmark.codename, 
            'metric': benchmark.metric, 
            'displayname': benchmark.displayname,
            'description': benchmark.description,
            'license_name': benchmark.license_name
        } 
        for benchmark in benchmarks
    ]

def load_all_questions_for_benchmark(session, benchmark_name):
    """
    Load all questions associated with a specific benchmark.

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

def find_top_runs_for_benchmark(session, benchmark_codename, benchmark_metric, top_n=5):
    """
    Find the top N runs for a specific benchmark based on average score.
    
    :param session: SQLAlchemy session
    :param benchmark_codename: Codename of the benchmark
    :param benchmark_metric: Metric of the benchmark
    :param top_n: Number of top runs to return (default 5)
    :return: List of top runs with model and average score
    """
    top_runs = (
        session.query(
            Run.run_id, 
            Run.model_name, 
            Model.displayname.label('model_displayname'),
            Run.normed_score,
        )
        .join(Model, Run.model_name == Model.codename)
        .filter(Run.benchmark_name == benchmark_codename)
        .filter(Run.benchmark_metric == benchmark_metric)
        .order_by(Run.normed_score.desc())
        .limit(top_n)
        .all()
    )
    
    return [
        {
            'run_id': run.run_id,
            'model_name': run.model_name,
            'model_displayname': run.model_displayname,
            'normed_score': run.normed_score
        } 
        for run in top_runs
    ]


def get_highest_benchmark_scores(session):
    """
    Get the highest benchmark scores for each (benchmark, model) combination along with their run IDs.

    :param session: SQLAlchemy session
    :return: Dict with (benchmark, model) tuple as key and dict containing score and run_id as value
    """
    # Query to find the highest-score runs, and the run information.
    highest_scores = (
        session.query(
            Run.benchmark_name,
            Run.benchmark_metric,
            Run.model_name,
            Run.normed_score,
            Run.run_id
        )
        .order_by(Run.normed_score)
        .distinct(Run.benchmark_name, Run.benchmark_metric, Run.model_name)
        .all()
    )

    # Convert to dictionary with (benchmark, model) as key
    result = {
        (f"{run.benchmark_name}:{run.benchmark_metric}", run.model_name): {
            'score': run.normed_score,
            'run_id': run.run_id
        }
        for run in highest_scores
    }

    return result


def decode_json(text):
    if text is None:
      return {}
    try:
      result = json.loads(text)
      return result
    except json.JSONDecodeError:
      return {"result": text}


def get_highest_scoring_run_details(session, model_name, benchmark_name, benchmark_metric):
    """
    Retrieve run details for the highest-scoring run for a specific (model, benchmark_name, benchmark_metric) pair.

    :param session: SQLAlchemy session
    :param model_name: Name of the model
    :param benchmark_name: Name of the benchmark
    :param benchmark_metric: Metric of the benchmark
    :return: Dictionary of run details
    """
    # First, find the highest-scoring run
    highest_run = (
        session.query(Run)
        .filter(Run.model_name == model_name)
        .filter(Run.benchmark_name == benchmark_name)
        .filter(Run.benchmark_metric == benchmark_metric)
        .order_by(Run.normed_score.desc())
        .first()
    )

    if not highest_run:
        return None

    # Then, get all run details for this run
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
        'benchmark_metric': highest_run.benchmark_metric,
        'normed_score': highest_run.normed_score,
        'details': [
            {
                'question_id': detail.question_id,
                'score': detail.score,
                'eval_msec': detail.eval_msec,
                'question_info_json': decode_json(query.question_info_json),
                'debug_json': decode_json(detail.debug_json)
            }
            for detail, query in run_details
        ]
    }

