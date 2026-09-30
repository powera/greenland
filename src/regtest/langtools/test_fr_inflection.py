"""Tests for rule-based French adjective and noun inflection."""

import unittest
from typing import List, Optional

from langtools.fr.inflection import build_adjective_forms, build_noun_forms


class TestFrenchAdjectiveForms(unittest.TestCase):
    def test_regular_consonant(self) -> None:
        self.assertEqual(
            build_adjective_forms("petit"),
            {
                "singular_m": "petit",
                "singular_f": "petite",
                "plural_m": "petits",
                "plural_f": "petites",
            },
        )

    def test_grand(self) -> None:
        forms = build_adjective_forms("grand")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "grande")
        self.assertEqual(forms["plural_f"], "grandes")

    def test_e_invariant_gender(self) -> None:
        self.assertEqual(
            build_adjective_forms("rouge"),
            {
                "singular_m": "rouge",
                "singular_f": "rouge",
                "plural_m": "rouges",
                "plural_f": "rouges",
            },
        )

    def test_eux_to_euse(self) -> None:
        forms = build_adjective_forms("heureux")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "heureuse")
        self.assertEqual(forms["plural_m"], "heureux")
        self.assertEqual(forms["plural_f"], "heureuses")

    def test_er_to_ere(self) -> None:
        forms = build_adjective_forms("cher")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "chère")
        self.assertEqual(forms["plural_f"], "chères")

    def test_f_to_ve(self) -> None:
        forms = build_adjective_forms("vif")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "vive")
        self.assertEqual(forms["plural_f"], "vives")

    def test_vowel_final(self) -> None:
        forms = build_adjective_forms("joli")
        assert forms is not None
        self.assertEqual(forms["singular_f"], "jolie")
        self.assertEqual(forms["plural_f"], "jolies")

    def test_irregular_table(self) -> None:
        self.assertEqual(
            build_adjective_forms("beau"),
            {
                "singular_m": "beau",
                "singular_f": "belle",
                "plural_m": "beaux",
                "plural_f": "belles",
                "singular_m_prevocalic": "bel",
            },
        )

    def test_uncertain_ending_returns_none(self) -> None:
        # -teur feminines vary (conservatrice / menteuse).
        self.assertIsNone(build_adjective_forms("conservateur"))
        self.assertIsNone(build_adjective_forms("fromage blanc"))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(build_adjective_forms(""))


def _fr_table(adjective: str) -> List[str]:
    forms = build_adjective_forms(adjective)
    assert forms is not None, adjective
    return [forms[key] for key in ("singular_m", "singular_f", "plural_m", "plural_f")]


class TestFrenchAdjectiveEndings(unittest.TestCase):
    def test_al(self) -> None:
        self.assertEqual(
            _fr_table("national"), ["national", "nationale", "nationaux", "nationales"]
        )
        self.assertEqual(_fr_table("naval"), ["naval", "navale", "navals", "navales"])

    def test_doubling_consonant(self) -> None:
        self.assertEqual(_fr_table("cruel")[1], "cruelle")
        self.assertEqual(_fr_table("pareil")[1], "pareille")
        self.assertEqual(_fr_table("ancien")[1], "ancienne")
        self.assertEqual(_fr_table("mignon")[1], "mignonne")
        self.assertEqual(_fr_table("muet")[1], "muette")
        self.assertEqual(_fr_table("sot")[1], "sotte")

    def test_single_consonant(self) -> None:
        self.assertEqual(_fr_table("complet")[1], "complète")
        self.assertEqual(_fr_table("idiot")[1], "idiote")
        self.assertEqual(_fr_table("fin")[1], "fine")
        self.assertEqual(_fr_table("brun")[1], "brune")
        self.assertEqual(_fr_table("noir")[1], "noire")
        self.assertEqual(_fr_table("civil")[1], "civile")

    def test_eur(self) -> None:
        self.assertEqual(_fr_table("travailleur")[1], "travailleuse")
        self.assertEqual(_fr_table("supérieur")[1], "supérieure")
        self.assertEqual(_fr_table("meilleur")[1], "meilleure")

    def test_s_endings(self) -> None:
        self.assertEqual(_fr_table("français"), ["français", "française", "français", "françaises"])
        self.assertEqual(_fr_table("gris")[1], "grise")
        self.assertEqual(_fr_table("gros")[1], "grosse")

    def test_prevocalic_slot(self) -> None:
        nouveau = build_adjective_forms("nouveau")
        assert nouveau is not None
        self.assertEqual(nouveau["singular_m_prevocalic"], "nouvel")
        petit = build_adjective_forms("petit")
        assert petit is not None
        self.assertNotIn("singular_m_prevocalic", petit)

    def test_prepositional_phrases_are_invariant(self) -> None:
        self.assertEqual(_fr_table("en bois"), ["en bois"] * 4)
        self.assertEqual(_fr_table("d'or"), ["d'or"] * 4)

    def test_feminine_form_fact_overrides_rule(self) -> None:
        forms = build_adjective_forms("conservateur", feminine_form="conservatrice")
        assert forms is not None
        self.assertEqual(forms["plural_f"], "conservatrices")


class TestFrenchNounForms(unittest.TestCase):
    def _plural(self, noun: str) -> Optional[str]:
        forms = build_noun_forms(noun)
        return forms["plural"] if forms else None

    def test_regular_and_invariant(self) -> None:
        self.assertEqual(self._plural("chat"), "chats")
        self.assertEqual(self._plural("prix"), "prix")
        self.assertEqual(self._plural("nez"), "nez")

    def test_closed_lists(self) -> None:
        self.assertEqual(self._plural("cheval"), "chevaux")
        self.assertEqual(self._plural("festival"), "festivals")
        self.assertEqual(self._plural("travail"), "travaux")
        self.assertEqual(self._plural("détail"), "détails")
        self.assertEqual(self._plural("bijou"), "bijoux")
        self.assertEqual(self._plural("trou"), "trous")
        self.assertEqual(self._plural("bateau"), "bateaux")
        self.assertEqual(self._plural("pneu"), "pneus")

    def test_suppletive(self) -> None:
        self.assertEqual(self._plural("œil"), "yeux")
        self.assertEqual(self._plural("monsieur"), "messieurs")

    def test_compounds(self) -> None:
        self.assertEqual(self._plural("pomme de terre"), "pommes de terre")
        self.assertEqual(self._plural("salle d’attente"), "salles d’attente")
        self.assertIsNone(self._plural("fromage blanc"))
        self.assertIsNone(self._plural("arc-en-ciel"))
        self.assertIsNone(self._plural("Paris"))

    def test_facts(self) -> None:
        self.assertEqual(
            build_noun_forms("ciel", irregular_plural="ciels"),
            {"singular": "ciel", "plural": "ciels"},
        )
        self.assertEqual(
            build_noun_forms("lunettes", number_type="plurale_tantum"),
            {"singular": "lunettes", "plural": "lunettes"},
        )
        self.assertEqual(build_noun_forms("lait", number_type="uncountable"), {"singular": "lait"})


if __name__ == "__main__":
    unittest.main()
