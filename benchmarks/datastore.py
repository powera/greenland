from sqlalchemy import create_engine, Column, Integer, Text, ForeignKey, TIMESTAMP
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func

# Create a base class for declarative models
Base = declarative_base()

# Define ORM models that match the database schema
class Benchmark(Base):
    __tablename__ = 'benchmark'
    
    codename = Column(Text, primary_key=True)
    displayname = Column(Text, nullable=False)
    description = Column(Text)
    license_name = Column(Text)
    
    # Relationship to runs
    run = relationship("Run", back_populates="benchmark")

class Model(Base):
    __tablename__ = 'model'
    
    codename = Column(Text, primary_key=True)
    displayname = Column(Text, nullable=False)
    launch_date = Column(Text)
    filesize_mb = Column(Integer)
    license_name = Column(Text)
    
    # Relationship to runs
    run = relationship("Run", back_populates="model")

class Run(Base):
    __tablename__ = 'run'
    
    run_id = Column(Integer, primary_key=True, autoincrement=True)
    run_ts = Column(TIMESTAMP, server_default=func.current_timestamp())
    model_name = Column(Text, ForeignKey('model.codename'))
    benchmark_name = Column(Text, ForeignKey('benchmark.codename'))
    normed_score = Column(Integer)

    # Relationships
    model = relationship("Model", back_populates="run")
    benchmark = relationship("Benchmark", back_populates="run")
    run_details = relationship("RunDetail", back_populates="run")

class RunDetail(Base):
    __tablename__ = 'run_detail'
    
    run_id = Column(Integer, ForeignKey('run.run_id'), primary_key=True)
    benchmark_name = Column(Text, primary_key=True)
    question_id = Column(Text, primary_key=True)
    score = Column(Integer)
    eval_msec = Column(Integer)
    
    # Relationship to run
    run = relationship("Run", back_populates="run_details")


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


def insert_benchmark(session, codename, displayname, description=None, license_name=None):
    """
    Insert a new benchmark into the database.

    :param session: SQLAlchemy session
    :param codename: Unique identifier for the benchmark
    :param displayname: Human-readable name of the benchmark
    :param description: Optional description of the benchmark
    :param license_name: Optional license information
    :return: Tuple (success_boolean, message)
    """
    try:
        # Create a new Benchmark object
        new_benchmark = Benchmark(
            codename=codename,
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


def insert_run(session, model_name, benchmark_name, normed_Score, run_ts=None, run_details=None):
    """
    Insert a new run into the database.

    :param session: SQLAlchemy session
    :param model_name: Codename of the model
    :param benchmark_name: Codename of the benchmark
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
                    question_id=detail.get('question_id'),
                    score=detail.get('score'),
                    eval_msec=detail.get('eval_msec')
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

def find_top_runs_for_benchmark(session, benchmark_codename, top_n=5):
    """
    Find the top N runs for a specific benchmark based on average score.
    
    :param session: SQLAlchemy session
    :param benchmark_codename: Codename of the benchmark
    :param top_n: Number of top runs to return (default 5)
    :return: List of top runs with model and average score
    """
    # Subquery to calculate average score per run
    top_runs = (
        session.query(
            Run.run_id, 
            Run.model_name, 
            Model.displayname.label('model_displayname'),
            func.avg(RunDetail.score).label('avg_score')
        )
        .join(RunDetail, Run.run_id == RunDetail.run_id)
        .join(Model, Run.model_name == Model.codename)
        .filter(Run.benchmark_name == benchmark_codename)
        .group_by(Run.run_id, Run.model_name, Model.displayname)
        .order_by(func.avg(RunDetail.score).desc())
        .limit(top_n)
        .all()
    )
    
    return [
        {
            'run_id': run.run_id,
            'model_name': run.model_name,
            'model_displayname': run.model_displayname,
            'avg_score': run.avg_score
        } 
        for run in top_runs
    ]

# Example usage
if __name__ == '__main__':
    # Create a session
    session = create_database_and_session()
    
    try:
        # List all models
        print("All Models:")
        models = list_all_models(session)
        for model in models:
            print(model)
        
        # Find top 5 runs for a specific benchmark (replace with an actual benchmark codename)
        print("\nTop 5 Runs for 'my_benchmark':")
        top_runs = find_top_runs_for_benchmark(session, 'my_benchmark')
        for run in top_runs:
            print(run)
    
    finally:
        # Close the session
        session.close()
