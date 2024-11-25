from sqlalchemy import create_engine, Column, Integer, Text, ForeignKey, Timestamp
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
    runs = relationship("Run", back_populates="benchmark")

class Model(Base):
    __tablename__ = 'model'
    
    codename = Column(Text, primary_key=True)
    displayname = Column(Text, nullable=False)
    launch_date = Column(Text)
    filesize_mb = Column(Integer)
    license_name = Column(Text)
    
    # Relationship to runs
    runs = relationship("Run", back_populates="model")

class Run(Base):
    __tablename__ = 'run'
    
    run_id = Column(Integer, primary_key=True, autoincrement=True)
    runtime = Column(Timestamp, server_default=func.current_timestamp())
    model_name = Column(Text, ForeignKey('model.codename'))
    benchmark_name = Column(Text, ForeignKey('benchmark.codename'))
    
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
