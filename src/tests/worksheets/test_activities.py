"""Verify answer integrity, deterministic content, selection, and printable PDFs."""

import json
from typing import cast

import pytest
from flask import Flask, g
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session

from storage.models.schema import Lemma
from worksheets import register
from worksheets.activities.matching import build_matching
from worksheets.activities.spelling import build_spelling
from worksheets.models import Word
from worksheets.rendering.pdf import render_pdf
from worksheets.sources import select_words

WORDS = [
    Word("a", "cat", "A small household animal.", "🐈"),
    Word("b", "sun", "The star that lights our days.", "☀️"),
    Word("c", "dog", "An animal that barks.", "🐕"),
]


@pytest.mark.parametrize("mode", ["missing", "scramble"])
def test_spelling_preserves_answers_and_letters(mode):
    worksheet = build_spelling(WORDS, mode, "definition", 9)
    assert worksheet == build_spelling(WORDS, mode, "definition", 9)
    for question, word in zip(worksheet.questions, WORDS):
        assert question.answer == word.text
        letters = question.prompt.replace(" ", "")
        assert letters != word.text
        if mode == "scramble":
            assert sorted(letters) == sorted(word.text)
        else:
            assert len(letters) == len(word.text)
            assert all(a == b or a == "_" for a, b in zip(letters, word.text))


@pytest.mark.parametrize("clue_type", ["definition", "emoji"])
def test_matching_answer_letters_follow_shuffled_clues(clue_type):
    sheet = build_matching(WORDS, clue_type, 7)
    assert len(set(sheet.choices)) == 3
    for question, word in zip(sheet.questions, WORDS):
        assert sheet.choices[ord(question.answer) - 65] == getattr(word, clue_type)


def test_pdf_student_and_answers_and_pagination():
    sheet = build_spelling(WORDS * 7, "missing", "definition", 2)
    student = render_pdf(sheet)
    answers = render_pdf(sheet, "a4", answers=True)
    assert student.startswith(b"%PDF-")
    assert answers.startswith(b"%PDF-")
    assert student != answers
    # The sample must actually exercise pagination, not just create a header.
    assert student.count(b"/Type /Page\n") >= 2


def test_emoji_pdf_and_missing_font(monkeypatch):
    from pathlib import Path

    if Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf").is_file():
        pdf = render_pdf(build_matching(WORDS, "emoji", 1))
        assert b"/Subtype /Image" in pdf
    monkeypatch.setenv("WORKSHEETS_EMOJI_FONT", "/missing/font.ttf")
    with pytest.raises(ValueError, match="Emoji PDFs need"):
        render_pdf(build_matching(WORDS, "emoji", 1))


def test_selection_excludes_revealed_answers_duplicate_words_and_clues():
    engine = create_engine("sqlite://")
    cast(Table, Lemma.__table__).create(engine)
    with Session(engine) as session:
        for number, word in enumerate(WORDS):
            session.add(
                Lemma(
                    guid=word.source_id,
                    lemma_text=word.text,
                    definition_text=word.definition,
                    pos_type="noun",
                    pos_subtype="animal",
                    emoji=json.dumps([word.emoji]),
                )
            )
        session.add(Lemma(guid="d", lemma_text="cat", definition_text="A feline.", pos_type="noun"))
        session.add(
            Lemma(guid="e", lemma_text="hat", definition_text="A hat for wearing.", pos_type="noun")
        )
        session.commit()
        result = select_words(session, 3, "definition", 4)
        assert {word.text for word in result} == {"cat", "sun", "dog"}
        assert result == select_words(session, 3, "definition", 4)
        with pytest.raises(ValueError, match="Only 3"):
            select_words(session, 4, "emoji", 4)
        with pytest.raises(ValueError, match="Only 0"):
            select_words(session, 2, "emoji", 4, "absent")


def test_barsukas_registration_preview_and_download(monkeypatch):
    # Exercise the package integration independently of Barsukas credentials/workers.
    import worksheets.views as views

    class Query:
        def distinct(self):
            return self

        def all(self):
            return [("animal",)]

    class Database:
        def query(self, column):
            return Query()

    app = Flask(__name__)
    app.jinja_loader = __import__("jinja2").DictLoader(
        {"base.html": "{% block content %}{% endblock %}"}
    )
    register(app)

    @app.before_request
    def setup():
        g.db = Database()

    monkeypatch.setattr(views, "select_words", lambda *args: WORDS)
    client = app.test_client()
    assert client.get("/worksheets/").status_code == 200
    data = {"activity": "matching", "count": "3", "seed": "7"}
    response = client.post("/worksheets/", data=data)
    assert response.status_code == 200
    assert b"English matching preview" in response.data
    response = client.post("/worksheets/", data={**data, "action": "student"})
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF-")
    assert client.post("/worksheets/", data={**data, "count": "900"}).status_code == 400
    assert client.post("/worksheets/", data={**data, "seed": "oops"}).status_code == 400
