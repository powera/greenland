"""Render tests for the shared Element templates and their callers.

These templates are shared across element types, so a break in one of them
silently degrades several pages at once. Assert the rendered markup rather than
just a 200, since a Jinja include that resolves to nothing still returns 200.
"""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from storage.crud.idiom import add_idiom_equivalent, create_idiom
from storage.crud.phrase import add_phrase, set_phrase_translation


def _seed_phrase(db_engine: Engine) -> int:
    with Session(db_engine) as session:
        phrase = add_phrase(
            session,
            phrase_subtype="greetings",
            label="Good morning",
            definition="A morning greeting",
            difficulty_level=2,
        )
        set_phrase_translation(session, phrase, "en", "Good morning")
        set_phrase_translation(session, phrase, "lt", "Labas rytas")
        session.commit()
        return int(phrase.id)


def test_phrase_list_renders_shared_element_table(
    app: Flask, client: FlaskClient, db_engine: Engine
) -> None:
    _seed_phrase(db_engine)

    response = client.get("/phrases/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    # display_text comes from the Element protocol, not phrase.label directly.
    assert "Good morning" in body
    # The phrase-specific extra column still renders through the shared table.
    assert "greetings" in body
    assert "L2" in body


def test_phrase_detail_renders_shared_identity_and_values(
    app: Flask, client: FlaskClient, db_engine: Engine
) -> None:
    phrase_id = _seed_phrase(db_engine)

    response = client.get(f"/phrases/{phrase_id}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    # Shared identity block.
    assert "Difficulty level" in body
    assert "L2" in body
    # Shared language-value table, projected via Element.language_values.
    assert "Labas rytas" in body
    assert "Good morning" in body


def test_phrase_list_empty_state_renders(
    app: Flask, client: FlaskClient, db_engine: Engine
) -> None:
    response = client.get("/phrases/")

    assert response.status_code == 200
    assert "No phrases found." in response.get_data(as_text=True)


def _seed_idiom(db_engine: Engine) -> int:
    with Session(db_engine) as session:
        idiom = create_idiom(
            session,
            source_language_code="en",
            expression="kick the bucket",
            meaning="to die",
            difficulty_level=4,
        )
        add_idiom_equivalent(
            session,
            idiom,
            language_code="lt",
            expression="numirti",
            equivalence_kind="paraphrase",
            literal_gloss="to die",
        )
        add_idiom_equivalent(
            session,
            idiom,
            language_code="lt",
            expression="atiduoti Dievui dūšią",
            equivalence_kind="idiomatic",
        )
        session.commit()
        return int(idiom.id)


def test_idiom_list_renders_through_shared_element_table(
    app: Flask, client: FlaskClient, db_engine: Engine
) -> None:
    _seed_idiom(db_engine)

    response = client.get("/idioms/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "kick the bucket" in body
    assert "M01_001" in body
    assert "L4" in body


def test_idiom_detail_shows_several_equivalents_in_one_language(
    app: Flask, client: FlaskClient, db_engine: Engine
) -> None:
    idiom_id = _seed_idiom(db_engine)

    response = client.get(f"/idioms/{idiom_id}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    # Source expression and meaning stay visually separate.
    assert "kick the bucket" in body
    assert "to die" in body
    # Both equivalents in the same language render, with their kinds.
    assert "numirti" in body
    assert "atiduoti Dievui dūšią" in body
    assert "paraphrase" in body
    assert "idiomatic" in body


def test_idiom_detail_states_missing_coverage_explicitly(
    app: Flask, client: FlaskClient, db_engine: Engine
) -> None:
    """Absent equivalents are a real coverage state, not a blank space."""
    idiom_id = _seed_idiom(db_engine)

    response = client.get(f"/idioms/{idiom_id}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No equivalent recorded for:" in body


def test_idiom_list_empty_state_renders(app: Flask, client: FlaskClient, db_engine: Engine) -> None:
    response = client.get("/idioms/")

    assert response.status_code == 200
    assert "No idioms found." in response.get_data(as_text=True)
