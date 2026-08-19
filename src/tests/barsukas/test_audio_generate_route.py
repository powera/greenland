#!/usr/bin/env python3
"""Tests for the Barsukas /audio/generate POST handler.

Regression coverage: the handler called the agents' generate_batch() without a
lemmas argument, which makes it return an empty result immediately. The page
flashed "Generated audio ... for 0 lemmas" and wrote nothing, while reporting
success.
"""

from typing import Any
from unittest.mock import MagicMock, patch

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import AudioQualityReview


def _fake_audio(*_args: Any, **_kwargs: Any) -> MagicMock:
    """Stand in for a TTS backend call, returning a tiny successful result."""
    result = MagicMock()
    result.success = True
    result.audio_data = b"ID3fake-mp3-bytes"
    result.duration_ms = 100.0
    result.error = None
    return result


def _review_rows(db_path: str) -> list[AudioQualityReview]:
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with Session(engine) as session:
            return session.query(AudioQualityReview).all()
    finally:
        engine.dispose()


def test_generate_post_creates_audio_for_selected_lemmas(
    client: FlaskClient, app: Flask, db_path: str, tmp_path: Any
) -> None:
    """A submitted form generates audio and writes review rows."""
    app.config["AUDIO_BASE_DIR"] = str(tmp_path / "audio")

    with patch("agents.strazdas.espeak_generate_audio", side_effect=_fake_audio) as tts:
        response = client.post(
            "/audio/generate",
            data={
                "language": "fr",
                "tts_engine": "espeak-ng",
                "voices": ["CLAIRE"],
            },
            follow_redirects=False,
        )

    assert response.status_code == 302

    # The seed data has exactly one lemma with a French translation ("manger").
    assert tts.call_count == 1
    assert tts.call_args.kwargs["text"] == "manger"

    rows = _review_rows(db_path)
    assert len(rows) == 1
    assert rows[0].language_code == "fr"
    assert rows[0].expected_text == "manger"
    assert rows[0].status == "pending_review"


def test_generate_post_reports_when_no_lemmas_match(
    client: FlaskClient, app: Flask, db_path: str, tmp_path: Any
) -> None:
    """A filter matching nothing says so, rather than claiming success."""
    app.config["AUDIO_BASE_DIR"] = str(tmp_path / "audio")

    with patch("agents.strazdas.espeak_generate_audio", side_effect=_fake_audio) as tts:
        response = client.post(
            "/audio/generate",
            data={
                "language": "fr",
                "tts_engine": "espeak-ng",
                "voices": ["CLAIRE"],
                "difficulty_level": "19",  # no seeded lemma sits at this level
            },
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert b"No lemmas found" in response.data
    tts.assert_not_called()
    assert _review_rows(db_path) == []


def test_generate_post_respects_limit(
    client: FlaskClient, app: Flask, db_path: str, tmp_path: Any
) -> None:
    """The submitted limit reaches lemma selection instead of being ignored."""
    app.config["AUDIO_BASE_DIR"] = str(tmp_path / "audio")

    with patch("agents.strazdas.espeak_generate_audio", side_effect=_fake_audio):
        with patch("barsukas.routes.audio.get_lemmas_for_processing", return_value=[]) as select:
            client.post(
                "/audio/generate",
                data={
                    "language": "fr",
                    "tts_engine": "espeak-ng",
                    "voices": ["CLAIRE"],
                    "limit": "5",
                    "difficulty_level": "3",
                },
                follow_redirects=True,
            )

    assert select.call_args.kwargs["limit"] == 5
    assert select.call_args.kwargs["difficulty_level"] == 3
    assert select.call_args.kwargs["language_code"] == "fr"


def test_generate_post_caps_unbounded_batches(
    client: FlaskClient, app: Flask, db_path: str, tmp_path: Any
) -> None:
    """An empty limit is capped, so one submit cannot start an unbounded run."""
    from barsukas.routes.audio import MAX_LEMMAS_PER_GENERATE_REQUEST

    app.config["AUDIO_BASE_DIR"] = str(tmp_path / "audio")

    with patch("agents.strazdas.espeak_generate_audio", side_effect=_fake_audio):
        with patch("barsukas.routes.audio.get_lemmas_for_processing", return_value=[]) as select:
            client.post(
                "/audio/generate",
                data={"language": "fr", "tts_engine": "espeak-ng", "voices": ["CLAIRE"]},
                follow_redirects=True,
            )

    assert select.call_args.kwargs["limit"] == MAX_LEMMAS_PER_GENERATE_REQUEST


def test_generate_post_caps_oversized_limit(
    client: FlaskClient, app: Flask, db_path: str, tmp_path: Any
) -> None:
    """A limit above the ceiling is clamped rather than honored."""
    from barsukas.routes.audio import MAX_LEMMAS_PER_GENERATE_REQUEST

    app.config["AUDIO_BASE_DIR"] = str(tmp_path / "audio")

    with patch("agents.strazdas.espeak_generate_audio", side_effect=_fake_audio):
        with patch("barsukas.routes.audio.get_lemmas_for_processing", return_value=[]) as select:
            client.post(
                "/audio/generate",
                data={
                    "language": "fr",
                    "tts_engine": "espeak-ng",
                    "voices": ["CLAIRE"],
                    "limit": str(MAX_LEMMAS_PER_GENERATE_REQUEST + 500),
                },
                follow_redirects=True,
            )

    assert select.call_args.kwargs["limit"] == MAX_LEMMAS_PER_GENERATE_REQUEST


def test_generate_post_caps_nonpositive_limit(
    client: FlaskClient, app: Flask, db_path: str, tmp_path: Any
) -> None:
    """A zero or negative limit cannot slip past the cap.

    SQLite reads a negative LIMIT as "no limit", so a hand-crafted POST that
    bypasses the form's min attribute must still be clamped.
    """
    from barsukas.routes.audio import MAX_LEMMAS_PER_GENERATE_REQUEST

    app.config["AUDIO_BASE_DIR"] = str(tmp_path / "audio")

    for bad_limit in ("0", "-1", "-500"):
        with patch("agents.strazdas.espeak_generate_audio", side_effect=_fake_audio):
            with patch(
                "barsukas.routes.audio.get_lemmas_for_processing", return_value=[]
            ) as select:
                client.post(
                    "/audio/generate",
                    data={
                        "language": "fr",
                        "tts_engine": "espeak-ng",
                        "voices": ["CLAIRE"],
                        "limit": bad_limit,
                    },
                    follow_redirects=True,
                )

        assert select.call_args.kwargs["limit"] == MAX_LEMMAS_PER_GENERATE_REQUEST, bad_limit
