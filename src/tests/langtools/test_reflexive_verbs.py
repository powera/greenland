"""Reflexive paradigms retain clitics and Lithuanian reflexive morphology."""

import pytest

from langtools.fr.conjugation import conjugate as conjugate_fr
from langtools.fr.mechanical import is_safe_translation
from langtools.lt.conjugation import conjugate as conjugate_lt
from langtools.es.conjugation import conjugate_for_dialect


@pytest.mark.parametrize(
    "infinitive,first,plural",
    [
        ("se laver", "me lave", "nous lavons"),
        ("s'habiller", "m'habille", "nous habillons"),
        ("s’habiller", "m'habille", "nous habillons"),
        ("se souvenir", "me souviens", "nous souvenons"),
        ("s'asseoir", "m'assieds", "nous asseyons"),
        ("se hâter", "me hâte", "nous hâtons"),
        ("se lever", "me lève", "nous levons"),
    ],
)
def test_french_reflexive(infinitive: str, first: str, plural: str) -> None:
    forms = conjugate_fr(infinitive)
    assert forms is not None
    assert forms["1s_present"] == first
    assert forms["1p_present"] == plural
    assert is_safe_translation(infinitive, "verb")


def test_french_nonfinite_forms() -> None:
    forms = conjugate_fr("se laver")
    assert forms is not None
    assert forms["infinitive"] == "se laver"
    assert forms["present_participle"] == "se lavant"
    assert forms["pc_m"] == "lavé"
    assert forms["pc_fp"] == "lavées"
    assert conjugate_fr("se laver les mains") is None
    assert not is_safe_translation("se laver les mains", "verb")


def test_lithuanian_suffix_reflexive() -> None:
    forms = conjugate_lt("mokytis", "mokosi", "mokėsi")
    assert forms is not None
    expected = {
        "1s_present": "mokausi",
        "2s_present": "mokaisi",
        "3s_present": "mokosi",
        "1p_present": "mokomės",
        "2p_present": "mokotės",
        "1s_past": "mokiausi",
        "2s_past": "mokeisi",
        "1p_past": "mokėmės",
        "1s_future": "mokysiuosi",
        "2s_future": "mokysiesi",
        "3s_future": "mokysis",
        "1p_future": "mokysimės",
        "2p_future": "mokysitės",
        "1s_conditional": "mokyčiausi",
        "2s_conditional": "mokytumeisi",
        "1p_conditional": "mokytumės",
        "2p_conditional": "mokytumėtės",
        "2s_imperative": "mokykis",
        "2p_imperative": "mokykitės",
        "habitual_past": "mokydavosi",
    }
    for slot, expected_form in expected.items():
        assert forms[slot] == expected_form
    assert conjugate_lt("mokytis", "moko", "mokė") is None


def test_lithuanian_internal_reflexive() -> None:
    forms = conjugate_lt("pasimokyti", "pasimoko", "pasimokė")
    assert forms is not None
    assert forms["1s_present"] == "pasimokau"
    assert forms["1p_future"] == "pasimokysime"
    assert forms["2s_imperative"] == "pasimokyk"


@pytest.mark.parametrize("language,second_plural", [("es", "os laváis"), ("es-419", "se lavan")])
def test_spanish_reflexive_dialects(language: str, second_plural: str) -> None:
    forms = conjugate_for_dialect("lavarse", language)
    assert forms is not None
    assert forms["1s_present"] == "me lavo"
    assert forms["2p_present"] == second_plural
    assert forms["gerund"] == "lavándose"


@pytest.mark.parametrize(
    "infinitive,present,past,first,second",
    [
        ("praustis", "prausiasi", "prausėsi", "prausiuosi", "prausiesi"),
        ("rūpintis", "rūpinasi", "rūpinosi", "rūpinuosi", "rūpiniesi"),
    ],
)
def test_lithuanian_a_conjugation(
    infinitive: str, present: str, past: str, first: str, second: str
) -> None:
    forms = conjugate_lt(infinitive, present, past)
    assert forms is not None
    assert forms["1s_present"] == first
    assert forms["2s_present"] == second


@pytest.mark.parametrize(
    "language,surface,lemma",
    [
        ("fr", "me lave", "se laver"),
        ("fr", "nous lavons", "se laver"),
        ("fr", "me hâte", "se hâter"),
        ("fr", "m'habille", "s'habiller"),
        ("fr", "m'assieds", "s'asseoir"),
        ("es", "me lavo", "lavarse"),
        ("lt", "mokausi", "mokytis"),
    ],
)
def test_reflexive_surface_matches(language: str, surface: str, lemma: str) -> None:
    from langtools.tokenizer import surface_matches_lemma

    assert surface_matches_lemma(language, surface, lemma)


@pytest.mark.parametrize(
    "infinitive,first,plural,participle",
    [
        ("se battre", "me bats", "nous battons", "battu"),
        ("se plaindre", "me plains", "nous plaignons", "plaint"),
        ("se produire", "me produis", "nous produisons", "produit"),
        ("se reproduire", "me reproduis", "nous reproduisons", "reproduit"),
        ("s'inscrire", "m'inscris", "nous inscrivons", "inscrit"),
    ],
)
def test_french_irregular_reflexive_bases(
    infinitive: str, first: str, plural: str, participle: str
) -> None:
    forms = conjugate_fr(infinitive)
    assert forms is not None
    assert forms["1s_present"] == first
    assert forms["1p_present"] == plural
    assert forms["pc_m"] == participle


def test_french_defective_reflexive_declines() -> None:
    assert conjugate_fr("s'ensuivre") is None
