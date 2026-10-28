"""CRUD helpers flush but leave the commit to their caller.

A helper that commits makes every caller's transaction end early: a preview
that rolls back afterwards has already written whatever the helper touched,
and a multi-step change can no longer fail as a whole.  The behavioural test
runs each write helper and rolls back; the scan fails on any ``commit()`` in
storage/crud outside the allowlist, so a new committing helper is caught when
it is written.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Set

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.derivative_form import (
    add_noun_derivative_form,
    delete_derivative_form,
    delete_derivative_forms_for_token,
    update_derivative_form,
)
from storage.crud.lemma import add_lemma, update_lemma
from storage.crud.lemma_fact import add_lemma_fact, delete_lemma_fact
from storage.crud.word_token import add_word_token
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Base, DerivativeForm, Lemma, WordToken

CRUD_DIR = Path(__file__).resolve().parents[2] / "storage" / "crud"

# Helpers that still commit, as "module.function".  They catch IntegrityError,
# roll back and return None, so converting one means a savepoint or a caller
# that handles the error -- and auditing every Barsukas and concept-pipeline
# caller.  Shrink this list; never grow it.
KNOWN_COMMITTING_HELPERS: Set[str] = {
    "concept.link_wikidata_concept",
    "concept.cache_wikidata_title",
    "concept.create_concept",
    "concept.update_concept",
    "concept.delete_concept",
    "concept.create_sub_concept",
    "concept.update_sub_concept",
    "concept.delete_sub_concept",
    "concept.link_wikidata_sub_concept",
    "concept.link_lemma_to_concept",
    "concept.unlink_lemma_from_concept",
}


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def _seed(session: Session) -> Lemma:
    """A committed noun with its English forms (add_lemma attaches them) and a fact."""
    lemma = add_lemma(
        session,
        lemma_text="dog",
        definition_text="a domesticated carnivore",
        pos_type="noun",
        auto_generate_guid=False,
    )
    session.add(LemmaFact(lemma_id=lemma.id, fact_type="concreteness", fact_value="concrete"))
    session.commit()
    return lemma


def _form(session: Session, lemma: Lemma) -> DerivativeForm:
    """The lemma's English base form."""
    return (
        session.query(DerivativeForm)
        .filter(DerivativeForm.lemma_id == lemma.id, DerivativeForm.is_base_form.is_(True))
        .one()
    )


def _snapshot(session: Session, lemma_id: int) -> Dict[str, object]:
    """Everything the helpers below could change, as plain values."""
    lemma = session.get(Lemma, lemma_id)
    assert lemma is not None
    forms = session.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma_id).all()
    facts = session.query(LemmaFact).filter(LemmaFact.lemma_id == lemma_id).all()
    return {
        "definition": lemma.definition_text,
        "forms": sorted((form.derivative_form_text, form.notes or "") for form in forms),
        "facts": {fact.fact_type: fact.fact_value for fact in facts},
        "tokens": sorted(token.token for token in session.query(WordToken).all()),
    }


# Each case: the write, then what the committed state must still look like
# after a rollback.
def _base_token_id(session: Session, lemma: Lemma) -> int:
    token_id = _form(session, lemma).word_token_id
    assert token_id is not None
    return token_id


CASES: Dict[str, Callable[[Session, Lemma], object]] = {
    "add_word_token": lambda s, lemma: add_word_token(s, "hound", "en"),
    "update_lemma": lambda s, lemma: update_lemma(s, lemma.id, definition_text="changed"),
    "update_derivative_form": lambda s, lemma: update_derivative_form(
        s, _form(s, lemma).id, notes="changed"
    ),
    "delete_derivative_form": lambda s, lemma: delete_derivative_form(s, _form(s, lemma).id),
    "delete_derivative_forms_for_token": lambda s, lemma: delete_derivative_forms_for_token(
        s, _base_token_id(s, lemma)
    ),
    "add_noun_derivative_form": lambda s, lemma: add_noun_derivative_form(
        s, lemma, "doggos", "noun/en_plural_informal", language_code="en"
    ),
    "add_lemma_fact": lambda s, lemma: add_lemma_fact(s, lemma.id, "individuation", "individual"),
    "delete_lemma_fact": lambda s, lemma: delete_lemma_fact(s, lemma.id, "concreteness"),
}


@pytest.mark.parametrize("helper_name", sorted(CASES))
def test_write_helpers_do_not_commit(session: Session, helper_name: str) -> None:
    lemma = _seed(session)
    lemma_id = lemma.id
    committed = _snapshot(session, lemma_id)

    CASES[helper_name](session, lemma)
    # The write is visible inside the transaction...
    assert _snapshot(session, lemma_id) != committed
    session.rollback()

    # ...and gone with it.
    assert _snapshot(session, lemma_id) == committed


def _committing_functions() -> List[str]:
    """Every ``module.function`` in storage/crud whose body calls ``.commit()``."""
    found: List[str] = []
    for path in sorted(CRUD_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "commit"
                ):
                    found.append(f"{path.stem}.{node.name}")
                    break
    return found


def test_no_new_crud_helper_commits() -> None:
    committing = set(_committing_functions())
    unexpected = sorted(committing - KNOWN_COMMITTING_HELPERS)
    assert not unexpected, (
        f"CRUD helpers that commit: {unexpected}. Flush instead and let the caller "
        "commit (see this module's docstring)."
    )
    # A helper converted to flush should leave the allowlist with it.
    stale = sorted(KNOWN_COMMITTING_HELPERS - committing)
    assert not stale, f"No longer commit; remove from KNOWN_COMMITTING_HELPERS: {stale}"
