"""Tests for Portuguese noun/adjective inflection helpers."""

from langtools.pt.inflection import build_adjective_forms, build_noun_forms


def test_noun_forms_regular() -> None:
    forms = build_noun_forms("livro")
    assert forms is not None
    assert forms["singular"] == "livro"
    assert forms["plural"] == "livros"


def test_noun_forms_irregular() -> None:
    forms = build_noun_forms("cão")
    assert forms is not None
    assert forms["plural"] == "cães"


def test_adjective_forms_regular() -> None:
    forms = build_adjective_forms("bonito")
    assert forms is not None
    assert forms["singular_m"] == "bonito"
    assert forms["singular_f"] == "bonita"
    assert forms["plural_m"] == "bonitos"
    assert forms["plural_f"] == "bonitas"


def test_adjective_forms_irregular() -> None:
    forms = build_adjective_forms("bom")
    assert forms is not None
    assert forms["singular_f"] == "boa"
    assert forms["plural_m"] == "bons"
    assert forms["plural_f"] == "boas"
