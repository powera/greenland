import unittest
from unittest.mock import Mock, patch

from sqlalchemy.exc import SQLAlchemyError

from benchmarks.benchmark_constants import BENCHMARKS_POSTGRES_SCHEMA
from benchmarks.datastore import common


class TestCreatePostgresSession(unittest.TestCase):
    def setUp(self):
        common._postgres_engine_cache.clear()

    def tearDown(self):
        common._postgres_engine_cache.clear()

    @patch("benchmarks.datastore.common._initialize_postgres_engine")
    @patch("benchmarks.datastore.common.sessionmaker")
    def test_create_postgres_session_initializes_engine_once(
        self, mock_sessionmaker, mock_initialize
    ):
        engine = Mock(name="engine")
        mock_initialize.return_value = engine

        session_factory = Mock()
        session_factory.return_value = "session"
        mock_sessionmaker.return_value = session_factory

        session = common.create_postgres_session("postgresql://example")

        self.assertEqual(session, "session")
        mock_initialize.assert_called_once_with("postgresql://example")
        mock_sessionmaker.assert_called_once_with(bind=engine)

    @patch("benchmarks.datastore.common._initialize_postgres_engine")
    @patch("benchmarks.datastore.common._probe_postgres_engine")
    @patch("benchmarks.datastore.common.sessionmaker")
    def test_create_postgres_session_rebuilds_cached_engine_on_probe_failure(
        self,
        mock_sessionmaker,
        mock_probe,
        mock_initialize,
    ):
        stale_engine = Mock(name="stale_engine")
        common._postgres_engine_cache["postgresql://example"] = stale_engine

        fresh_engine = Mock(name="fresh_engine")
        mock_initialize.return_value = fresh_engine
        mock_probe.side_effect = SQLAlchemyError("stale connection")

        session_factory = Mock()
        session_factory.return_value = "session"
        mock_sessionmaker.return_value = session_factory

        session = common.create_postgres_session("postgresql://example")

        self.assertEqual(session, "session")
        stale_engine.dispose.assert_called_once_with()
        mock_initialize.assert_called_once_with("postgresql://example")
        self.assertIs(common._postgres_engine_cache["postgresql://example"], fresh_engine)

    @patch("benchmarks.datastore.common.Base.metadata.create_all")
    @patch("benchmarks.datastore.common.event.listens_for")
    @patch("benchmarks.datastore.common.create_engine")
    def test_initialize_postgres_engine_sets_explicit_schema_for_orm_queries(
        self,
        mock_create_engine,
        mock_listens_for,
        mock_create_all,
    ):
        base_engine = Mock(name="base_engine")
        translated_engine = Mock(name="translated_engine")
        mock_create_engine.return_value = base_engine
        base_engine.execution_options.return_value = translated_engine

        mock_listens_for.side_effect = lambda *_args, **_kwargs: (lambda fn: fn)

        connect_context = Mock(name="connect_context")
        connect_context.__enter__ = Mock(return_value=connect_context)
        connect_context.__exit__ = Mock(return_value=False)
        base_engine.connect.return_value = connect_context

        engine = common._initialize_postgres_engine("postgresql://example")

        self.assertIs(engine, translated_engine)
        base_engine.execution_options.assert_called_once_with(
            schema_translate_map={None: BENCHMARKS_POSTGRES_SCHEMA}
        )
        connect_context.execute.assert_called_once()
        execute_sql = str(connect_context.execute.call_args.args[0])
        self.assertEqual(execute_sql, f"CREATE SCHEMA IF NOT EXISTS {BENCHMARKS_POSTGRES_SCHEMA}")
        connect_context.commit.assert_called_once_with()
        mock_create_all.assert_called_once_with(translated_engine)


if __name__ == "__main__":
    unittest.main()
