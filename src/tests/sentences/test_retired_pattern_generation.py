"""Old pattern entry points must fail before touching the database or a model."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from sentences.generation import generate_examples_for_lemma
from sentences.generation_cli import get_argument_parser
from storage.backend.config import DataSourceConfig


def test_old_pattern_example_job_is_rejected() -> None:
    session: Any = MagicMock()
    with pytest.raises(ValueError, match="retired"):
        generate_examples_for_lemma(session, DataSourceConfig(), lemma_id=1, mode="pattern")
    session.get.assert_not_called()


def test_cli_no_longer_accepts_pattern_work() -> None:
    parser = get_argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--task", "generate-candidates", "--all-patterns"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--task", "generate-sentences", "--mode", "pattern"])
