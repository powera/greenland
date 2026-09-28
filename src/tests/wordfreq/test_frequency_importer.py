"""Tests for reloading a corpus through import_frequency_as_annotations."""

import json
from pathlib import Path
from typing import Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import (
    Base,
    DerivativeForm,
    ExternalLexemeAnnotation,
    ExternalLexemeAnnotationLemma,
    Lemma,
    WordToken,
)
from wordfreq.frequency.importer import import_frequency_as_annotations


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _write_ranked_list(path: Path, words: List[str]) -> str:
    path.write_text(json.dumps(words), encoding="utf-8")
    return str(path)


def _ranks(session: Session, source: str) -> Dict[str, int]:
    rows = (
        session.query(WordToken.token, ExternalLexemeAnnotation.ordinal_rank)
        .join(WordToken, WordToken.id == ExternalLexemeAnnotation.word_token_id)
        .filter(ExternalLexemeAnnotation.source == source)
        .all()
    )
    return {token: rank for token, rank in rows}


def test_reload_deletes_words_the_new_file_dropped(tmp_path: Path) -> None:
    session = _make_session()
    import_frequency_as_annotations(
        session,
        file_path=_write_ranked_list(tmp_path / "v1.json", ["the", "http", "cell"]),
        corpus_name="wiki_test",
    )
    assert _ranks(session, "wordfreq_wiki_test") == {"the": 1, "http": 2, "cell": 3}

    import_frequency_as_annotations(
        session,
        file_path=_write_ranked_list(tmp_path / "v2.json", ["the", "cell"]),
        corpus_name="wiki_test",
    )

    assert _ranks(session, "wordfreq_wiki_test") == {"the": 1, "cell": 2}
    # The token itself stays; only its rank in this corpus goes.
    assert session.query(WordToken).filter(WordToken.token == "http").count() == 1


def test_reload_leaves_other_sources_and_hinted_rows_alone(tmp_path: Path) -> None:
    session = _make_session()
    import_frequency_as_annotations(
        session,
        file_path=_write_ranked_list(tmp_path / "a.json", ["the", "http"]),
        corpus_name="wiki_test",
    )
    import_frequency_as_annotations(
        session,
        file_path=_write_ranked_list(tmp_path / "b.json", ["http"]),
        corpus_name="other",
    )
    http = session.query(WordToken).filter(WordToken.token == "http").one()
    session.add(
        ExternalLexemeAnnotation(
            word_token_id=http.id,
            source="wordfreq_wiki_test",
            tier_name="common",
            pos_hint="noun",
            ordinal_rank=5,
        )
    )
    session.commit()

    import_frequency_as_annotations(
        session,
        file_path=_write_ranked_list(tmp_path / "a2.json", ["the"]),
        corpus_name="wiki_test",
    )

    assert _ranks(session, "wordfreq_other") == {"http": 1}
    hinted = (
        session.query(ExternalLexemeAnnotation)
        .filter(
            ExternalLexemeAnnotation.source == "wordfreq_wiki_test",
            ExternalLexemeAnnotation.word_token_id == http.id,
        )
        .one()
    )
    assert hinted.pos_hint == "noun"


def test_reload_deletes_the_stale_rows_lemma_links(tmp_path: Path) -> None:
    session = _make_session()
    lemma = Lemma(lemma_text="http", pos_type="noun", guid="N01_001", definition_text="x")
    session.add(lemma)
    session.flush()
    session.add(
        DerivativeForm(
            lemma_id=lemma.id,
            derivative_form_text="http",
            language_code="en",
            grammatical_form="noun/singular",
            is_base_form=True,
        )
    )
    session.commit()

    import_frequency_as_annotations(
        session,
        file_path=_write_ranked_list(tmp_path / "v1.json", ["http"]),
        corpus_name="wiki_test",
    )
    assert session.query(ExternalLexemeAnnotationLemma).count() == 1

    import_frequency_as_annotations(
        session,
        file_path=_write_ranked_list(tmp_path / "v2.json", ["the"]),
        corpus_name="wiki_test",
    )

    assert session.query(ExternalLexemeAnnotationLemma).count() == 0
