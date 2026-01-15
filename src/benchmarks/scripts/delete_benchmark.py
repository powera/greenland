from sqlalchemy import delete

from benchmarks.datastore import benchmarks as datastore_benchmarks
from benchmarks.datastore.common import create_dev_session


def delete_benchmark_completely(session, benchmark_code: str) -> bool:
    """
    Delete a benchmark, all its questions, and all associated runs from the database.

    Args:
        session: SQLAlchemy session
        benchmark_code: Benchmark code to delete (e.g., "0050_translation_es_sw")

    Returns:
        True if successful, False otherwise
    """

    if not session:
        session = create_dev_session()
    try:
        # 1. Find all run IDs associated with this benchmark
        run_ids_query = (
            session.query(datastore_benchmarks.Run.run_id)
            .filter(datastore_benchmarks.Run.benchmark_name == benchmark_code)
            .all()
        )
        run_ids = [row[0] for row in run_ids_query]

        # 2. Delete run details for these runs
        for run_id in run_ids:
            detail_delete = delete(datastore_benchmarks.RunDetail).where(
                datastore_benchmarks.RunDetail.run_id == run_id
            )
            session.execute(detail_delete)

        # 3. Delete the runs themselves
        run_delete = delete(datastore_benchmarks.Run).where(
            datastore_benchmarks.Run.benchmark_name == benchmark_code
        )
        session.execute(run_delete)

        # 4. Delete all questions associated with this benchmark
        question_delete = delete(datastore_benchmarks.Question).where(
            datastore_benchmarks.Question.benchmark_name == benchmark_code
        )
        session.execute(question_delete)

        # 5. Delete the benchmark itself
        benchmark_delete = delete(datastore_benchmarks.Benchmark).where(
            datastore_benchmarks.Benchmark.codename == benchmark_code
        )
        session.execute(benchmark_delete)

        # Commit all changes
        session.commit()
        print(
            f"Successfully deleted benchmark {benchmark_code}, its questions, and {len(run_ids)} associated runs"
        )

        return True

    except Exception as e:
        session.rollback()
        print(f"Error deleting benchmark {benchmark_code}: {str(e)}")
        return False


# Usage example:
# delete_benchmark_completely(session, "0050_translation_es_sw")
