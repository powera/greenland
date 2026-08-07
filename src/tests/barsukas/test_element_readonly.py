"""Characterize read-only POST behavior before shared Element presenters exist."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from storage.models.name_entity import Name
from storage.models.schema import Phrase


def test_phrase_create_is_blocked_in_read_only_mode(
    app: Flask, client: FlaskClient, db_engine: Engine
) -> None:
    app.config["READONLY"] = True

    response = client.post(
        "/phrases/add",
        data={
            "phrase_subtype": "greetings",
            "label": "Good morning",
            "english": "Good morning",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/phrases/")
    with Session(db_engine) as check_session:
        assert check_session.query(Phrase).count() == 0


def test_name_create_is_blocked_in_read_only_mode(
    app: Flask, client: FlaskClient, db_engine: Engine
) -> None:
    app.config["READONLY"] = True

    response = client.post(
        "/names/create",
        data={"name_text": "George", "kind": "given_name"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/names/")
    with Session(db_engine) as check_session:
        assert check_session.query(Name).count() == 0
