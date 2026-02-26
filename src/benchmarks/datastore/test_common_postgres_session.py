import unittest
from unittest.mock import Mock, patch

from sqlalchemy.exc import SQLAlchemyError

from benchmarks.datastore import common


class TestCreatePostgresSession(unittest.TestCase):
    def setUp(self):
        common._postgres_engine_cache.clear()

    def tearDown(self):
        common._postgres_engine_cache.clear()

    @patch("benchmarks.datastore.common._initialize_postgres_engine")
    @patch("benchmarks.datastore.common.sessionmaker")
    def test_create_postgres_session_initializes_engine_once(self, mock_sessionmaker, mock_initialize):
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


if __name__ == "__main__":
    unittest.main()
