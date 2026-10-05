"""The English-base repair restores only missing base forms."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.integrity.lemmas import check_missing_english_base_forms
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation, WordToken


def test_repair_missing_english_bases_is_additive_and_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        europe = Lemma(lemma_text="Europe", definition_text="A continent", pos_type="noun")
        western = Lemma(
            lemma_text="western", definition_text="Toward the west", pos_type="adjective"
        )
        multiword = Lemma(
            lemma_text="North America", definition_text="A continent", pos_type="noun"
        )
        session.add_all([europe, western, multiword])
        session.add(WordToken(token="Europe", language_code="en", frequency_rank=908))
        session.flush()
        session.add(LemmaTranslation(lemma_id=europe.id, language_code="en", translation="Europe"))

        before = check_missing_english_base_forms(session)
        assert before["missing_count"] == 3
        assert session.query(DerivativeForm).count() == 0

        repaired = check_missing_english_base_forms(session, fix=True)
        assert repaired["fixed_count"] == 3
        assert check_missing_english_base_forms(session)["missing_count"] == 0
        assert check_missing_english_base_forms(session, fix=True)["fixed_count"] == 0

        europe_form = session.query(DerivativeForm).filter_by(lemma_id=europe.id).one()
        assert europe_form.grammatical_form == "noun/en_singular"
        assert europe_form.word_token_id is not None
        assert session.query(WordToken).filter_by(token="Europe", language_code="en").count() == 1

        western_form = session.query(DerivativeForm).filter_by(lemma_id=western.id).one()
        assert western_form.grammatical_form == "adjective/en_positive"
        assert western_form.word_token_id is not None
        assert (
            session.query(LemmaTranslation)
            .filter_by(lemma_id=western.id, language_code="en")
            .one()
            .translation
            == "western"
        )

        multiword_form = session.query(DerivativeForm).filter_by(lemma_id=multiword.id).one()
        assert multiword_form.word_token_id is None
        assert session.query(DerivativeForm).count() == 3
    engine.dispose()
