"""Route-level tests for /rhymes language filtering behavior."""

from flask.testing import FlaskClient
from sqlalchemy.orm import Session, sessionmaker

from storage.models.schema import DerivativeForm, Lemma


def _seed_rhyme_data(db_session: Session) -> None:
    """Insert multilingual lemma/derivative rows with rhyme keys."""
    lemmas = [
        Lemma(
            id=101,
            lemma_text="chanter",
            definition_text="to sing",
            pos_type="verb",
            guid="V01_101",
            difficulty_level=1,
            confidence=1.0,
            verified=True,
        ),
        Lemma(
            id=102,
            lemma_text="danser",
            definition_text="to dance",
            pos_type="verb",
            guid="V01_102",
            difficulty_level=1,
            confidence=1.0,
            verified=True,
        ),
        Lemma(
            id=103,
            lemma_text="canto",
            definition_text="I sing",
            pos_type="verb",
            guid="V01_103",
            difficulty_level=1,
            confidence=1.0,
            verified=True,
        ),
        Lemma(
            id=104,
            lemma_text="manto",
            definition_text="cloak",
            pos_type="noun",
            guid="N01_104",
            difficulty_level=1,
            confidence=1.0,
            verified=True,
        ),
        Lemma(
            id=105,
            lemma_text="cat",
            definition_text="a feline",
            pos_type="noun",
            guid="N01_105",
            difficulty_level=1,
            confidence=1.0,
            verified=True,
        ),
        Lemma(
            id=106,
            lemma_text="bat",
            definition_text="a flying mammal",
            pos_type="noun",
            guid="N01_106",
            difficulty_level=1,
            confidence=1.0,
            verified=True,
        ),
    ]
    db_session.add_all(lemmas)
    db_session.flush()

    forms = [
        DerivativeForm(
            lemma_id=101,
            language_code="fr",
            derivative_form_text="chanter",
            grammatical_form="infinitive",
            is_base_form=True,
            ipa_pronunciation="ʃɑ̃te",
            rhyme_key="e",
        ),
        DerivativeForm(
            lemma_id=102,
            language_code="fr",
            derivative_form_text="danser",
            grammatical_form="infinitive",
            is_base_form=True,
            ipa_pronunciation="dɑ̃se",
            rhyme_key="e",
        ),
        DerivativeForm(
            lemma_id=103,
            language_code="es",
            derivative_form_text="canto",
            grammatical_form="present_1s",
            is_base_form=False,
            ipa_pronunciation="kanto",
            rhyme_key="o",
        ),
        DerivativeForm(
            lemma_id=104,
            language_code="es",
            derivative_form_text="manto",
            grammatical_form="singular",
            is_base_form=True,
            ipa_pronunciation="manto",
            rhyme_key="o",
        ),
        DerivativeForm(
            lemma_id=105,
            language_code="en",
            derivative_form_text="cat",
            grammatical_form="singular",
            is_base_form=True,
            ipa_pronunciation="kæt",
            rhyme_key="æt",
        ),
        DerivativeForm(
            lemma_id=106,
            language_code="en",
            derivative_form_text="bat",
            grammatical_form="singular",
            is_base_form=True,
            ipa_pronunciation="bæt",
            rhyme_key="æt",
        ),
    ]
    db_session.add_all(forms)
    db_session.commit()


def test_rhyme_index_renders_french_and_spanish_families(client: FlaskClient, db_engine) -> None:
    """`language=fr` and `language=es` should render their own rhyme families."""
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    _seed_rhyme_data(db_session)
    db_session.close()

    fr_response = client.get("/rhymes/?language=fr")
    assert fr_response.status_code == 200
    fr_html = fr_response.data.decode()
    assert "-e" in fr_html
    assert "chanter" in fr_html or "danser" in fr_html

    es_response = client.get("/rhymes/?language=es")
    assert es_response.status_code == 200
    es_html = es_response.data.decode()
    assert "-o" in es_html
    assert "canto" in es_html or "manto" in es_html


def test_rhyme_invalid_language_falls_back_to_english(client: FlaskClient, db_engine) -> None:
    """Invalid language values should default to English family listings."""
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    _seed_rhyme_data(db_session)
    db_session.close()

    response = client.get("/rhymes/?language=zz")
    assert response.status_code == 200
    html = response.data.decode()

    assert "-æt" in html
    assert "cat" in html or "bat" in html
    assert "chanter" not in html
    assert "canto" not in html
