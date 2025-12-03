#!/usr/bin/python3

from sqlalchemy.exc import SQLAlchemyError
import benchmarks.datastore.benchmarks
from benchmarks.datastore.benchmarks import Run, RunDetail


def delete_run(run_id: int, session=None) -> tuple[bool, str]:
    """
    Delete a benchmark run and all its associated run details.

    Args:
        run_id: ID of the run to delete
        session: Optional SQLAlchemy session (will create one if not provided)

    Returns:
        Tuple (success_boolean, message)
    """

    # Create session if not provided
    if session is None:
        session = datastore.benchmarks.create_dev_session()

    try:
        # First delete associated run details due to foreign key constraint
        details_deleted = session.query(RunDetail).filter(RunDetail.run_id == run_id).delete()

        # Then delete the run itself
        run_deleted = session.query(Run).filter(Run.run_id == run_id).delete()

        if run_deleted == 0:
            session.rollback()
            return False, f"Run with ID {run_id} not found"

        # Commit the changes
        session.commit()

        return True, f"Run {run_id} successfully deleted along with {details_deleted} run details"

    except SQLAlchemyError as e:
        session.rollback()
        return False, f"Error deleting run: {str(e)}"
