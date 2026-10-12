"""Score snapshots avoid repeated detail downloads and observe external edits."""

from unittest.mock import patch
from pathlib import Path


from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from benchmarks.datastore.common import Base, Model
from benchmarks.datastore.benchmarks import Benchmark, Question, Run, RunDetail
from benchmarks.server.scores import ScoreCache


def test_precalculated_scores_refresh_after_external_write() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                Model(codename="test", displayname="Test"),
                Benchmark(codename="test", displayname="Test"),
                Question(question_id="q", benchmark_name="test"),
                Run(run_id=1, model_name="test", benchmark_name="test"),
                RunDetail(run_id=1, question_id="q", score=100, eval_msec=10),
            ]
        )
        db.commit()
    queries: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def count_query(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        queries.append(statement)

    cache = ScoreCache(60)
    with patch("benchmarks.server.scores.monotonic", return_value=100):
        with Session(engine) as first:
            summaries = cache.get(first)
        assert summaries[0]["metrics"].effective_score == 100
        assert all("debug_json" not in sql and "question_info_json" not in sql for sql in queries)
        queries.clear()
        with Session(engine) as second:
            assert cache.get(second)[0]["run"].model_name == "test"
        assert not queries
        with Session(engine) as writer:
            writer.query(Question).update({Question.is_excluded: True})
            writer.commit()
        with Session(engine) as reader:
            assert cache.get(reader)[0]["metrics"].effective_score == 100
    with patch("benchmarks.server.scores.monotonic", return_value=161):
        with Session(engine) as reader:
            assert cache.get(reader)[0]["metrics"].included_question_count == 0
    engine.dispose()


def test_scoreboard_pages_render(tmp_path: "Path") -> None:
    from benchmarks.datastore.common import create_database_and_session
    from benchmarks.server.app import create_app
    from benchmarks.server.config import Config

    db_path = tmp_path / "benchmarks.sqlite"
    with create_database_and_session(str(db_path)) as db:
        db.add_all(
            [
                Model(codename="test", displayname="Test"),
                Benchmark(codename="test", displayname="Test"),
                Question(question_id="q", benchmark_name="test"),
                Run(run_id=1, model_name="test", benchmark_name="test"),
                RunDetail(run_id=1, question_id="q", score=100, eval_msec=10),
            ]
        )
        db.commit()

    class TestConfig(Config):
        DB_PATH = str(db_path)
        TESTING = True
        BENCHMARK_RUNNER_ENABLED = False

    client = create_app(TestConfig).test_client()
    for page in ["/dashboard/", "/benchmarks/test", "/models/test"]:
        response = client.get(page)
        assert response.status_code == 200
        assert client.get(page).data == response.data
