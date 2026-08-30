"""Tests for barsukas.helpers.flash_helpers."""

import logging
from typing import List, Tuple, cast

import pytest
from flask import Flask, get_flashed_messages

from barsukas.helpers.flash_helpers import flash_and_log, log_and_flash_error


def _flashed_with_categories() -> List[Tuple[str, str]]:
    """get_flashed_messages returns a union; pin the with-categories shape."""
    return cast(List[Tuple[str, str]], get_flashed_messages(with_categories=True))


@pytest.fixture()
def flask_app() -> Flask:
    """Minimal Flask app with a secret key for session/flash support."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test"
    app.config["TESTING"] = True
    return app


class TestFlashAndLog:
    """Tests for flash_and_log."""

    def test_default_category_is_info(self, flask_app: Flask) -> None:
        with flask_app.test_request_context():
            flash_and_log("hello")
            messages = _flashed_with_categories()
            assert ("info", "hello") in messages

    def test_error_category(self, flask_app: Flask) -> None:
        with flask_app.test_request_context():
            flash_and_log("bad thing", category="error")
            messages = _flashed_with_categories()
            assert ("error", "bad thing") in messages

    def test_success_category(self, flask_app: Flask) -> None:
        with flask_app.test_request_context():
            flash_and_log("done!", category="success")
            messages = _flashed_with_categories()
            assert ("success", "done!") in messages

    def test_logs_with_warning_for_error_category(
        self, flask_app: Flask, caplog: pytest.LogCaptureFixture
    ) -> None:
        with flask_app.test_request_context():
            with caplog.at_level(logging.WARNING):
                flash_and_log("oops", category="error")

            assert any("oops" in r.message for r in caplog.records)

    def test_logs_with_info_for_success_category(
        self, flask_app: Flask, caplog: pytest.LogCaptureFixture
    ) -> None:
        with flask_app.test_request_context():
            with caplog.at_level(logging.INFO):
                flash_and_log("yay", category="success")

            assert any("yay" in r.message for r in caplog.records)

    def test_custom_log_level_override(
        self, flask_app: Flask, caplog: pytest.LogCaptureFixture
    ) -> None:
        with flask_app.test_request_context():
            with caplog.at_level(logging.DEBUG):
                flash_and_log("debug msg", category="info", log_level="DEBUG")

            assert any("debug msg" in r.message for r in caplog.records)


class TestLogAndFlashError:
    """Tests for log_and_flash_error."""

    def test_flashes_error_message(self, flask_app: Flask) -> None:
        with flask_app.test_request_context():
            try:
                raise ValueError("something broke")
            except ValueError as e:
                log_and_flash_error(e, "testing")

            messages = _flashed_with_categories()
            assert len(messages) == 1
            category, msg = messages[0]
            assert category == "error"
            assert "something broke" in msg
            assert "testing" in msg

    def test_includes_traceback_location(self, flask_app: Flask) -> None:
        with flask_app.test_request_context():
            try:
                raise RuntimeError("fail")
            except RuntimeError as e:
                log_and_flash_error(e, "operation")

            messages = _flashed_with_categories()
            _, msg = messages[0]
            # Should include file:line from traceback
            assert "test_flash_helpers.py" in msg

    def test_handles_exception_without_traceback(self, flask_app: Flask) -> None:
        with flask_app.test_request_context():
            exc = RuntimeError("no tb")
            exc.__traceback__ = None
            log_and_flash_error(exc, "ctx")

            messages = _flashed_with_categories()
            _, msg = messages[0]
            assert "no tb" in msg
