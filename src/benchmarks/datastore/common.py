#!/usr/bin/python3

"""Common database utilities and base classes for benchmarks and qualitative tests."""

import datetime
import json
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy import String, Integer, Text, ForeignKey, TIMESTAMP, create_engine, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase, sessionmaker
from sqlalchemy.sql import func

import constants

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

class Model(Base):
    """Model definition."""
    __tablename__ = "model"
    codename: Mapped[str] = mapped_column(String, primary_key=True)
    displayname: Mapped[str] = mapped_column(String, nullable=False)
    launch_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    filesize_mb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    license_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_type: Mapped[str] = mapped_column(String, nullable=False, default="local")

    # benchmark runs and qual runs are populated in those files.

def create_dev_session():
    """Create a database session for development."""
    db_path = constants.SQLITE_DB_PATH
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Session = sessionmaker(bind=engine)
    return Session()

def create_database_and_session(db_path="benchmarks.sqlite"):
    """Create a SQLite database engine and session."""
    engine = create_engine(f'sqlite:///{db_path}', echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

def insert_model(
    session,
    codename: str,
    displayname: str,
    launch_date: str = None,
    filesize_mb: int = None,
    license_name: str = None,
    model_path: str = None,
    model_type: str = "local"
):
    """Insert a new model into the database."""
    try:
        new_model = Model(
            codename=codename,
            displayname=displayname,
            launch_date=launch_date,
            filesize_mb=filesize_mb,
            license_name=license_name,
            model_path=model_path,
            model_type=model_type
        )
        session.add(new_model)
        session.commit()
        return True, f"Model '{codename}' successfully inserted"

    except IntegrityError:
        session.rollback()
        return False, f"Model '{codename}' already exists"
    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error inserting model: {str(e)}"

def list_all_models(session):
    """List all models in the database.

    :param session: SQLAlchemy session
    :return: List of model details
    """
    models = session.query(Model).order_by(Model.displayname).all()
    return [
        {
            "codename": model.codename,
            "displayname": model.displayname,
            "launch_date": model.launch_date,
            "filesize_mb": model.filesize_mb,
            "license_name": model.license_name,
            "model_path": model.model_path,
            "model_type": model.model_type
        }
        for model in models
    ]

def get_model_by_codename(session, codename: str):
    """Get model details by codename.

    :param session: SQLAlchemy session
    :param codename: Model codename
    :return: Model details dictionary or None
    """
    model = session.query(Model).filter(Model.codename == codename).first()
    if not model:
        return None

    return {
        "codename": model.codename,
        "displayname": model.displayname,
        "launch_date": model.launch_date,
        "filesize_mb": model.filesize_mb,
        "license_name": model.license_name,
        "model_path": model.model_path,
        "model_type": model.model_type
    }

def get_default_model_codename(session):
    """Get the default model codename from the database.

    :param session: SQLAlchemy session
    :return: Default model codename or None
    """
    # Get the first model from the database as the default
    model = session.query(Model).first()
    return model.codename if model else None

def decode_json(text: Optional[str]) -> Dict:
    """Safely decode JSON text with proper Unicode handling."""
    if text is None:
        return {}
    try:
        result = json.loads(text)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return {"result": text}