"""Tests for the golden-mode wordfreq loading indicator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from barsukas.app import create_app
from barsukas.config import Config
from barsukas.golden_wordfreq_status import complete_load, start_load
from barsukas.personas import PERSONAS, PersonaName


class GoldenTestConfig(Config):
    """Minimal config override for a golden-mode app."""

    TESTING = True
    DEBUG = False
    SECRET_KEY = "test"
    DB_PATH = "unused.sqlite"


def _golden_client(monkeypatch: Any, tmp_path: Path) -> Any:
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    golden_persona = PERSONAS[PersonaName.GOLDEN]
    monkeypatch.setattr(golden_persona, "jsonl_data_dir", str(release_dir))
    monkeypatch.setattr(golden_persona, "use_postgres_concepts", False)
    return create_app(config_class=GoldenTestConfig, persona=golden_persona).test_client()


#: A stable fragment of the notice, which names the derived forms the same
#: background load rebuilds as well as the frequency data.
NOTICE = b"Word-frequency data and mechanically-derived forms are loading"


def test_loading_notice_only_appears_on_wordfreq_pages(monkeypatch: Any, tmp_path: Path) -> None:
    """Golden pages that consume wordfreq explain that their data is incomplete."""
    start_load()
    client = _golden_client(monkeypatch, tmp_path)

    home_response = client.get("/")
    assert home_response.status_code == 200
    assert NOTICE not in home_response.data

    wordfreq_response = client.get("/word-tokens/")
    assert wordfreq_response.status_code == 200
    assert NOTICE in wordfreq_response.data


def test_completed_load_hides_banner(monkeypatch: Any, tmp_path: Path) -> None:
    """Completed wordfreq loads do not leave a stale banner behind."""
    start_load()
    complete_load()
    client = _golden_client(monkeypatch, tmp_path)

    response = client.get("/word-tokens/")
    assert response.status_code == 200
    assert NOTICE not in response.data
