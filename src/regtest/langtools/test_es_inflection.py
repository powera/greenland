"""Tests for rule-based Spanish adjective and noun inflection."""

import unittest
from typing import Dict, List, Optional, Tuple

from langtools.es.inflection import build_adjective_forms, build_noun_forms

_ORDER = ("singular_m", "singular_f", "plural_m", "plural_f")


def _table(adjective: str) -> List[str]:
    """Return the four agreement forms in a fixed order."""
    forms: Optional[Dict[str, str]] = build_adjective_forms(adjective)
    assert forms is not None, adjective
    return [forms[key] for key in _ORDER]


class TestVowelEndings(unittest.TestCase):
    def test_o_adjective_four_forms(self) -> None:
        self.assertEqual(_table("rojo"), ["rojo", "roja", "rojos", "rojas"])
        self.assertEqual(_table("pequeño"), ["pequeño", "pequeña", "pequeños", "pequeñas"])

    def test_e_adjective_invariant_gender(self) -> None:
        self.assertEqual(_table("grande"), ["grande", "grande", "grandes", "grandes"])
        self.assertEqual(_table("verde"), ["verde", "verde", "verdes", "verdes"])

    def test_a_adjective_invariant_gender(self) -> None:
        self.assertEqual(_table("belga"), ["belga", "belga", "belgas", "belgas"])
        self.assertEqual(_table("idealista"), ["idealista"] * 2 + ["idealistas"] * 2)

    def test_stressed_i_and_u_take_es(self) -> None:
        self.assertEqual(_table("marroquí"), ["marroquí"] * 2 + ["marroquíes"] * 2)
        self.assertEqual(_table("iraquí"), ["iraquí"] * 2 + ["iraquíes"] * 2)
        self.assertEqual(_table("hindú"), ["hindú"] * 2 + ["hindúes"] * 2)


class TestGenderedConsonantEndings(unittest.TestCase):
    """-or, -ón, -án, -ín and -és mark gender."""

    def test_or_adjectives(self) -> None:
        for adjective, expected in [
            ("hablador", ["hablador", "habladora", "habladores", "habladoras"]),
            ("trabajador", ["trabajador", "trabajadora", "trabajadores", "trabajadoras"]),
            ("acogedor", ["acogedor", "acogedora", "acogedores", "acogedoras"]),
        ]:
            self.assertEqual(_table(adjective), expected, adjective)

    def test_comparatives_stay_invariant(self) -> None:
        for adjective in ("mejor", "peor", "mayor", "menor"):
            singular_m, singular_f, plural_m, plural_f = _table(adjective)
            self.assertEqual(singular_f, singular_m, adjective)
            self.assertEqual(plural_m, adjective + "es", adjective)
            self.assertEqual(plural_f, plural_m, adjective)

    def test_ior_adjectives_stay_invariant(self) -> None:
        self.assertEqual(_table("anterior"), ["anterior", "anterior", "anteriores", "anteriores"])
        self.assertEqual(_table("exterior"), ["exterior", "exterior", "exteriores", "exteriores"])

    def test_ar_adjectives_are_not_or_adjectives(self) -> None:
        for adjective in ("similar", "circular", "regular", "particular", "familiar"):
            self.assertEqual(
                _table(adjective),
                [adjective, adjective, adjective + "es", adjective + "es"],
                adjective,
            )

    def test_es_nationality_adjectives_drop_the_accent(self) -> None:
        self.assertEqual(_table("francés"), ["francés", "francesa", "franceses", "francesas"])
        self.assertEqual(_table("inglés"), ["inglés", "inglesa", "ingleses", "inglesas"])
        self.assertEqual(
            _table("portugués"),
            ["portugués", "portuguesa", "portugueses", "portuguesas"],
        )

    def test_cortes_is_invariant(self) -> None:
        self.assertEqual(_table("cortés"), ["cortés", "cortés", "corteses", "corteses"])
        self.assertEqual(
            _table("descortés"), ["descortés", "descortés", "descorteses", "descorteses"]
        )

    def test_an_and_in_and_on_adjectives(self) -> None:
        for adjective, expected in [
            ("alemán", ["alemán", "alemana", "alemanes", "alemanas"]),
            ("holgazán", ["holgazán", "holgazana", "holgazanes", "holgazanas"]),
            ("chiquitín", ["chiquitín", "chiquitina", "chiquitines", "chiquitinas"]),
            ("llorón", ["llorón", "llorona", "llorones", "lloronas"]),
            ("dormilón", ["dormilón", "dormilona", "dormilones", "dormilonas"]),
        ]:
            self.assertEqual(_table(adjective), expected, adjective)

    def test_marron_is_invariant(self) -> None:
        self.assertEqual(_table("marrón"), ["marrón", "marrón", "marrones", "marrones"])

    def test_listed_gendered_consonant_adjectives(self) -> None:
        self.assertEqual(_table("español"), ["español", "española", "españoles", "españolas"])
        self.assertEqual(_table("andaluz"), ["andaluz", "andaluza", "andaluces", "andaluzas"])
        self.assertEqual(_table("mongol"), ["mongol", "mongola", "mongoles", "mongolas"])


class TestInvariantConsonantEndings(unittest.TestCase):
    """Other consonant endings agree in number only."""

    def test_l_and_r_and_s_endings(self) -> None:
        cases: List[Tuple[str, str]] = [
            ("azul", "azules"),
            ("cruel", "crueles"),
            ("leal", "leales"),
            ("normal", "normales"),
            ("impar", "impares"),
            ("gris", "grises"),
        ]
        for adjective, plural in cases:
            self.assertEqual(_table(adjective), [adjective, adjective, plural, plural])

    def test_written_accent_is_kept_when_the_word_grows(self) -> None:
        self.assertEqual(_table("fácil")[2], "fáciles")
        self.assertEqual(_table("difícil")[2], "difíciles")
        self.assertEqual(_table("débil")[2], "débiles")
        self.assertEqual(_table("fértil")[2], "fértiles")

    def test_accent_is_dropped_when_the_plural_moves_the_word(self) -> None:
        self.assertEqual(_table("común")[2], "comunes")
        self.assertEqual(_table("ruin")[2], "ruines")

    def test_accent_is_added_when_the_plural_moves_the_word(self) -> None:
        self.assertEqual(_table("joven")[2], "jóvenes")
        self.assertEqual(_table("virgen")[2], "vírgenes")

    def test_z_adjectives_take_ces(self) -> None:
        for adjective, plural in [
            ("feliz", "felices"),
            ("capaz", "capaces"),
            ("veloz", "veloces"),
            ("audaz", "audaces"),
        ]:
            self.assertEqual(_table(adjective), [adjective, adjective, plural, plural])

    def test_unstressed_final_s_is_invariant(self) -> None:
        self.assertEqual(_table("gratis"), ["gratis"] * 4)
        self.assertEqual(_table("isósceles"), ["isósceles"] * 4)


class TestUninflectableInput(unittest.TestCase):
    def test_multiword_phrases_return_none(self) -> None:
        self.assertIsNone(build_adjective_forms("hecho a mano"))
        self.assertIsNone(build_adjective_forms("más oriental"))

    def test_prepositional_phrases_are_invariant(self) -> None:
        self.assertEqual(_table("de madera"), ["de madera"] * 4)
        self.assertEqual(_table("de mala calidad"), ["de mala calidad"] * 4)
        self.assertEqual(_table("con forma"), ["con forma"] * 4)

    def test_hyphenated_returns_none(self) -> None:
        self.assertIsNone(build_adjective_forms("teórico-práctico"))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(build_adjective_forms(""))
        self.assertIsNone(build_adjective_forms("   "))

    def test_vowelless_returns_none(self) -> None:
        self.assertIsNone(build_adjective_forms("xyz"))


class TestCaseAndWhitespace(unittest.TestCase):
    def test_input_is_normalised(self) -> None:
        self.assertEqual(_table("  Rojo  "), ["rojo", "roja", "rojos", "rojas"])


class TestApocope(unittest.TestCase):
    def test_masculine_only(self) -> None:
        forms = build_adjective_forms("bueno")
        assert forms is not None
        self.assertEqual(forms["singular_m_apocope"], "buen")
        self.assertNotIn("singular_f_apocope", forms)

    def test_gran_both_genders(self) -> None:
        forms = build_adjective_forms("grande")
        assert forms is not None
        self.assertEqual(forms["singular_m_apocope"], "gran")
        self.assertEqual(forms["singular_f_apocope"], "gran")

    def test_most_adjectives_have_none(self) -> None:
        forms = build_adjective_forms("rojo")
        assert forms is not None
        self.assertNotIn("singular_m_apocope", forms)


class TestNounPlurals(unittest.TestCase):
    def _plural(self, noun: str) -> Optional[str]:
        forms = build_noun_forms(noun)
        return forms["plural"] if forms else None

    def test_vowel_endings(self) -> None:
        self.assertEqual(self._plural("casa"), "casas")
        self.assertEqual(self._plural("sofá"), "sofás")
        self.assertIsNone(self._plural("rubí"))

    def test_consonant_endings_with_respelling(self) -> None:
        self.assertEqual(self._plural("camión"), "camiones")
        self.assertEqual(self._plural("joven"), "jóvenes")
        self.assertEqual(self._plural("examen"), "exámenes")
        self.assertEqual(self._plural("lápiz"), "lápices")
        self.assertEqual(self._plural("ciudad"), "ciudades")
        self.assertEqual(self._plural("régimen"), "regímenes")

    def test_s_endings(self) -> None:
        self.assertEqual(self._plural("autobús"), "autobuses")
        self.assertEqual(self._plural("país"), "países")
        self.assertEqual(self._plural("mes"), "meses")
        self.assertEqual(self._plural("crisis"), "crisis")
        self.assertEqual(self._plural("lunes"), "lunes")

    def test_loanword_endings_are_undecided(self) -> None:
        self.assertIsNone(self._plural("club"))
        self.assertIsNone(self._plural("jersey"))
        self.assertEqual(self._plural("rey"), "reyes")

    def test_compounds_and_names(self) -> None:
        self.assertEqual(self._plural("tarjeta de crédito"), "tarjetas de crédito")
        self.assertIsNone(self._plural("polo sur"))
        self.assertIsNone(self._plural("Madrid"))

    def test_facts(self) -> None:
        self.assertEqual(
            build_noun_forms("gafas", number_type="plurale_tantum"),
            {"singular": "gafas", "plural": "gafas"},
        )
        self.assertEqual(
            build_noun_forms("leche", number_type="uncountable"), {"singular": "leche"}
        )
        self.assertEqual(
            build_noun_forms("carácter", irregular_plural="caracteres")["plural"],  # type: ignore[index]
            "caracteres",
        )


if __name__ == "__main__":
    unittest.main()
