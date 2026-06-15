"""Tests for rule-based French verb conjugation."""

import unittest
from typing import Dict

from langtools.fr.conjugation import (
    conjugate,
    conjugate_detailed,
    is_known_irregular,
    list_irregular_verbs,
)
from langtools.fr.types import VerbConjugation


class _ConjugationTestBase(unittest.TestCase):
    """Shared helper that returns the forms dict and asserts success."""

    def _forms(self, verb: str) -> Dict[str, str]:
        forms = conjugate(verb)
        self.assertIsNotNone(forms, f"{verb} should conjugate successfully")
        assert forms is not None  # narrow Optional for type-checkers
        return forms


class TestRegularErVerbs(_ConjugationTestBase):
    """Test first-group (-er) regular conjugation."""

    def test_parler_present(self) -> None:
        forms = self._forms("parler")
        self.assertEqual(forms["1s_present"], "parle")
        self.assertEqual(forms["2s_present"], "parles")
        self.assertEqual(forms["3s_present"], "parle")
        self.assertEqual(forms["1p_present"], "parlons")
        self.assertEqual(forms["2p_present"], "parlez")
        self.assertEqual(forms["3p_present"], "parlent")

    def test_parler_imperfect(self) -> None:
        forms = self._forms("parler")
        self.assertEqual(forms["1s_impf"], "parlais")
        self.assertEqual(forms["2s_impf"], "parlais")
        self.assertEqual(forms["3s_impf"], "parlait")
        self.assertEqual(forms["1p_impf"], "parlions")
        self.assertEqual(forms["2p_impf"], "parliez")
        self.assertEqual(forms["3p_impf"], "parlaient")

    def test_parler_future(self) -> None:
        forms = self._forms("parler")
        self.assertEqual(forms["1s_future"], "parlerai")
        self.assertEqual(forms["2s_future"], "parleras")
        self.assertEqual(forms["3s_future"], "parlera")
        self.assertEqual(forms["1p_future"], "parlerons")
        self.assertEqual(forms["2p_future"], "parlerez")
        self.assertEqual(forms["3p_future"], "parleront")

    def test_parler_past_participle(self) -> None:
        forms = self._forms("parler")
        self.assertEqual(forms["pc_m"], "parlé")
        self.assertEqual(forms["pc_f"], "parlée")

    def test_parler_metadata(self) -> None:
        conjugation, ok = conjugate_detailed("parler")
        self.assertTrue(ok)
        self.assertEqual(conjugation.word, "parler")
        self.assertEqual(conjugation.notes, "regular -er")
        self.assertEqual(conjugation.confidence, 1.0)

    def test_all_20_forms_present(self) -> None:
        forms = self._forms("parler")
        self.assertEqual(len(forms), 20)
        for form_name in VerbConjugation.ALL_FORMS:
            self.assertIn(form_name, forms)


class TestGerVerbs(_ConjugationTestBase):
    """Test -ger orthographic adjustment."""

    def test_manger_present(self) -> None:
        forms = self._forms("manger")
        self.assertEqual(forms["1s_present"], "mange")
        self.assertEqual(forms["1p_present"], "mangeons")
        self.assertEqual(forms["2p_present"], "mangez")
        self.assertEqual(forms["3p_present"], "mangent")

    def test_manger_imperfect(self) -> None:
        forms = self._forms("manger")
        self.assertEqual(forms["1s_impf"], "mangeais")
        self.assertEqual(forms["3s_impf"], "mangeait")
        self.assertEqual(forms["1p_impf"], "mangions")
        self.assertEqual(forms["2p_impf"], "mangiez")
        self.assertEqual(forms["3p_impf"], "mangeaient")


class TestCerVerbs(_ConjugationTestBase):
    """Test -cer orthographic adjustment."""

    def test_commencer_present(self) -> None:
        forms = self._forms("commencer")
        self.assertEqual(forms["1s_present"], "commence")
        self.assertEqual(forms["1p_present"], "commençons")
        self.assertEqual(forms["2p_present"], "commencez")

    def test_commencer_imperfect(self) -> None:
        forms = self._forms("commencer")
        self.assertEqual(forms["1s_impf"], "commençais")
        self.assertEqual(forms["3s_impf"], "commençait")
        self.assertEqual(forms["1p_impf"], "commencions")
        self.assertEqual(forms["2p_impf"], "commenciez")
        self.assertEqual(forms["3p_impf"], "commençaient")


class TestYerVerbs(_ConjugationTestBase):
    """Test -yer stem change (y -> i before silent endings)."""

    def test_payer_present(self) -> None:
        forms = self._forms("payer")
        self.assertEqual(forms["1s_present"], "paie")
        self.assertEqual(forms["2s_present"], "paies")
        self.assertEqual(forms["3s_present"], "paie")
        self.assertEqual(forms["1p_present"], "payons")
        self.assertEqual(forms["2p_present"], "payez")
        self.assertEqual(forms["3p_present"], "paient")

    def test_nettoyer_present(self) -> None:
        forms = self._forms("nettoyer")
        self.assertEqual(forms["1s_present"], "nettoie")
        self.assertEqual(forms["1p_present"], "nettoyons")
        self.assertEqual(forms["3p_present"], "nettoient")

    def test_payer_future(self) -> None:
        forms = self._forms("payer")
        self.assertEqual(forms["1s_future"], "paierai")
        self.assertEqual(forms["3p_future"], "paieront")

    def test_payer_imperfect_keeps_y(self) -> None:
        forms = self._forms("payer")
        self.assertEqual(forms["1s_impf"], "payais")
        self.assertEqual(forms["1p_impf"], "payions")

    def test_payer_past_participle(self) -> None:
        forms = self._forms("payer")
        self.assertEqual(forms["pc_m"], "payé")
        self.assertEqual(forms["pc_f"], "payée")


class TestRegularIrVerbs(_ConjugationTestBase):
    """Test second-group (-ir with -iss-) regular conjugation."""

    def test_finir_present(self) -> None:
        forms = self._forms("finir")
        self.assertEqual(forms["1s_present"], "finis")
        self.assertEqual(forms["2s_present"], "finis")
        self.assertEqual(forms["3s_present"], "finit")
        self.assertEqual(forms["1p_present"], "finissons")
        self.assertEqual(forms["2p_present"], "finissez")
        self.assertEqual(forms["3p_present"], "finissent")

    def test_finir_imperfect(self) -> None:
        forms = self._forms("finir")
        self.assertEqual(forms["1s_impf"], "finissais")
        self.assertEqual(forms["1p_impf"], "finissions")

    def test_finir_future(self) -> None:
        forms = self._forms("finir")
        self.assertEqual(forms["1s_future"], "finirai")
        self.assertEqual(forms["3p_future"], "finiront")

    def test_finir_past_participle(self) -> None:
        forms = self._forms("finir")
        self.assertEqual(forms["pc_m"], "fini")
        self.assertEqual(forms["pc_f"], "finie")

    def test_choisir(self) -> None:
        forms = self._forms("choisir")
        self.assertEqual(forms["1s_present"], "choisis")
        self.assertEqual(forms["1p_present"], "choisissons")
        self.assertEqual(forms["1s_impf"], "choisissais")

    def test_ir_confidence(self) -> None:
        conjugation, ok = conjugate_detailed("choisir")
        self.assertTrue(ok)
        self.assertEqual(conjugation.confidence, 0.8)
        self.assertIn("assumed second group", conjugation.notes or "")


class TestRegularReVerbs(_ConjugationTestBase):
    """Test regular third-group (-re) conjugation."""

    def test_vendre_present(self) -> None:
        forms = self._forms("vendre")
        self.assertEqual(forms["1s_present"], "vends")
        self.assertEqual(forms["2s_present"], "vends")
        self.assertEqual(forms["3s_present"], "vend")
        self.assertEqual(forms["1p_present"], "vendons")
        self.assertEqual(forms["2p_present"], "vendez")
        self.assertEqual(forms["3p_present"], "vendent")

    def test_vendre_imperfect(self) -> None:
        forms = self._forms("vendre")
        self.assertEqual(forms["1s_impf"], "vendais")
        self.assertEqual(forms["1p_impf"], "vendions")

    def test_vendre_future(self) -> None:
        forms = self._forms("vendre")
        self.assertEqual(forms["1s_future"], "vendrai")
        self.assertEqual(forms["3p_future"], "vendront")

    def test_vendre_past_participle(self) -> None:
        forms = self._forms("vendre")
        self.assertEqual(forms["pc_m"], "vendu")
        self.assertEqual(forms["pc_f"], "vendue")

    def test_attendre(self) -> None:
        forms = self._forms("attendre")
        self.assertEqual(forms["1s_present"], "attends")
        self.assertEqual(forms["3s_present"], "attend")
        self.assertEqual(forms["1s_future"], "attendrai")
        self.assertEqual(forms["pc_m"], "attendu")


class TestIrregularVerbs(_ConjugationTestBase):
    """Test hard-coded irregular verbs."""

    def test_etre(self) -> None:
        forms = self._forms("être")
        self.assertEqual(forms["1s_present"], "suis")
        self.assertEqual(forms["2s_present"], "es")
        self.assertEqual(forms["3s_present"], "est")
        self.assertEqual(forms["1p_present"], "sommes")
        self.assertEqual(forms["2p_present"], "êtes")
        self.assertEqual(forms["3p_present"], "sont")
        # imperfect (special stem ét-)
        self.assertEqual(forms["1s_impf"], "étais")
        self.assertEqual(forms["1p_impf"], "étions")
        self.assertEqual(forms["3p_impf"], "étaient")
        # future
        self.assertEqual(forms["1s_future"], "serai")
        self.assertEqual(forms["3p_future"], "seront")
        # past participle
        self.assertEqual(forms["pc_m"], "été")
        self.assertEqual(forms["pc_f"], "été")

    def test_avoir(self) -> None:
        forms = self._forms("avoir")
        self.assertEqual(forms["1s_present"], "ai")
        self.assertEqual(forms["3s_present"], "a")
        self.assertEqual(forms["3p_present"], "ont")
        self.assertEqual(forms["1s_impf"], "avais")
        self.assertEqual(forms["1s_future"], "aurai")
        self.assertEqual(forms["pc_m"], "eu")
        self.assertEqual(forms["pc_f"], "eue")

    def test_aller(self) -> None:
        forms = self._forms("aller")
        # aller is irregular, NOT treated as regular -er
        self.assertEqual(forms["1s_present"], "vais")
        self.assertEqual(forms["3p_present"], "vont")
        self.assertEqual(forms["1s_future"], "irai")
        self.assertEqual(forms["pc_m"], "allé")

    def test_faire(self) -> None:
        forms = self._forms("faire")
        self.assertEqual(forms["1s_present"], "fais")
        self.assertEqual(forms["2p_present"], "faites")
        self.assertEqual(forms["3p_present"], "font")
        self.assertEqual(forms["1s_future"], "ferai")
        self.assertEqual(forms["pc_m"], "fait")

    def test_pouvoir(self) -> None:
        forms = self._forms("pouvoir")
        self.assertEqual(forms["1s_present"], "peux")
        self.assertEqual(forms["3p_present"], "peuvent")
        self.assertEqual(forms["1s_future"], "pourrai")
        self.assertEqual(forms["pc_m"], "pu")

    def test_vouloir(self) -> None:
        forms = self._forms("vouloir")
        self.assertEqual(forms["1s_present"], "veux")
        self.assertEqual(forms["3p_present"], "veulent")
        self.assertEqual(forms["1s_future"], "voudrai")

    def test_venir(self) -> None:
        forms = self._forms("venir")
        self.assertEqual(forms["1s_present"], "viens")
        self.assertEqual(forms["1p_present"], "venons")
        self.assertEqual(forms["3p_present"], "viennent")
        self.assertEqual(forms["1s_impf"], "venais")
        self.assertEqual(forms["1s_future"], "viendrai")
        self.assertEqual(forms["pc_m"], "venu")

    def test_prendre(self) -> None:
        forms = self._forms("prendre")
        self.assertEqual(forms["1s_present"], "prends")
        self.assertEqual(forms["3s_present"], "prend")
        self.assertEqual(forms["3p_present"], "prennent")
        self.assertEqual(forms["1s_future"], "prendrai")
        self.assertEqual(forms["pc_m"], "pris")
        self.assertEqual(forms["pc_f"], "prise")

    def test_voir(self) -> None:
        forms = self._forms("voir")
        self.assertEqual(forms["1s_present"], "vois")
        self.assertEqual(forms["1s_impf"], "voyais")
        self.assertEqual(forms["1s_future"], "verrai")
        self.assertEqual(forms["pc_m"], "vu")

    def test_dire(self) -> None:
        forms = self._forms("dire")
        self.assertEqual(forms["2p_present"], "dites")
        self.assertEqual(forms["pc_m"], "dit")

    def test_mettre(self) -> None:
        forms = self._forms("mettre")
        self.assertEqual(forms["3s_present"], "met")
        self.assertEqual(forms["1s_future"], "mettrai")
        self.assertEqual(forms["pc_m"], "mis")

    def test_partir(self) -> None:
        forms = self._forms("partir")
        self.assertEqual(forms["1s_present"], "pars")
        self.assertEqual(forms["1p_present"], "partons")
        self.assertEqual(forms["1s_future"], "partirai")
        self.assertEqual(forms["pc_m"], "parti")

    def test_ouvrir(self) -> None:
        forms = self._forms("ouvrir")
        self.assertEqual(forms["1s_present"], "ouvre")
        self.assertEqual(forms["1p_present"], "ouvrons")
        self.assertEqual(forms["pc_m"], "ouvert")

    def test_mourir(self) -> None:
        forms = self._forms("mourir")
        self.assertEqual(forms["1s_present"], "meurs")
        self.assertEqual(forms["1p_present"], "mourons")
        self.assertEqual(forms["1s_future"], "mourrai")

    def test_envoyer(self) -> None:
        forms = self._forms("envoyer")
        self.assertEqual(forms["1s_present"], "envoie")
        self.assertEqual(forms["1p_present"], "envoyons")
        self.assertEqual(forms["1s_future"], "enverrai")

    def test_irregular_notes(self) -> None:
        conjugation, ok = conjugate_detailed("être")
        self.assertTrue(ok)
        self.assertEqual(conjugation.notes, "irregular")

    def test_all_irregulars_have_20_forms(self) -> None:
        for verb in list_irregular_verbs():
            forms = conjugate(verb)
            self.assertIsNotNone(forms, f"{verb} should conjugate successfully")
            assert forms is not None  # narrow Optional for type-checkers
            self.assertEqual(
                len(forms),
                20,
                f"{verb} should have 20 forms, got {len(forms)}",
            )


class TestCompoundVerbs(_ConjugationTestBase):
    """Test compound verbs derived from irregular bases."""

    def test_comprendre(self) -> None:
        forms = self._forms("comprendre")
        self.assertEqual(forms["1s_present"], "comprends")
        self.assertEqual(forms["3p_present"], "comprennent")
        self.assertEqual(forms["1s_impf"], "comprenais")
        self.assertEqual(forms["1s_future"], "comprendrai")
        self.assertEqual(forms["pc_m"], "compris")
        self.assertEqual(forms["pc_f"], "comprise")

    def test_revenir(self) -> None:
        forms = self._forms("revenir")
        self.assertEqual(forms["1s_present"], "reviens")
        self.assertEqual(forms["1p_present"], "revenons")
        self.assertEqual(forms["3p_present"], "reviennent")
        self.assertEqual(forms["1s_future"], "reviendrai")
        self.assertEqual(forms["pc_m"], "revenu")

    def test_permettre(self) -> None:
        forms = self._forms("permettre")
        self.assertEqual(forms["1s_present"], "permets")
        self.assertEqual(forms["3s_present"], "permet")
        self.assertEqual(forms["1s_future"], "permettrai")
        self.assertEqual(forms["pc_m"], "permis")

    def test_defaire(self) -> None:
        forms = self._forms("défaire")
        self.assertEqual(forms["1s_present"], "défais")
        self.assertEqual(forms["2p_present"], "défaites")
        self.assertEqual(forms["3p_present"], "défont")
        self.assertEqual(forms["1s_future"], "déferai")

    def test_decouvrir(self) -> None:
        forms = self._forms("découvrir")
        self.assertEqual(forms["1s_present"], "découvre")
        self.assertEqual(forms["1p_present"], "découvrons")
        self.assertEqual(forms["pc_m"], "découvert")

    def test_obtenir(self) -> None:
        forms = self._forms("obtenir")
        self.assertEqual(forms["1s_present"], "obtiens")
        self.assertEqual(forms["3p_present"], "obtiennent")
        self.assertEqual(forms["1s_future"], "obtiendrai")
        self.assertEqual(forms["pc_m"], "obtenu")

    def test_apprendre(self) -> None:
        forms = self._forms("apprendre")
        self.assertEqual(forms["1s_present"], "apprends")
        self.assertEqual(forms["3p_present"], "apprennent")
        self.assertEqual(forms["pc_m"], "appris")

    def test_renvoyer(self) -> None:
        forms = self._forms("renvoyer")
        self.assertEqual(forms["1s_present"], "renvoie")
        self.assertEqual(forms["1p_present"], "renvoyons")
        self.assertEqual(forms["1s_future"], "renverrai")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_empty_string(self) -> None:
        self.assertIsNone(conjugate(""))

    def test_whitespace_only(self) -> None:
        self.assertIsNone(conjugate("   "))

    def test_unknown_ending(self) -> None:
        self.assertIsNone(conjugate("xyz"))
        conjugation, ok = conjugate_detailed("xyz")
        self.assertFalse(ok)
        self.assertEqual(conjugation.word, "xyz")

    def test_whitespace_stripped(self) -> None:
        forms = conjugate("  parler  ")
        self.assertIsNotNone(forms)
        assert forms is not None  # narrow Optional for type-checkers
        self.assertEqual(forms["1s_present"], "parle")
        conjugation, ok = conjugate_detailed("  parler  ")
        self.assertTrue(ok)
        self.assertEqual(conjugation.word, "parler")

    def test_two_char_er_not_conjugated(self) -> None:
        """A two-character 'er' is not a valid verb."""
        self.assertIsNone(conjugate("er"))


class TestHelperFunctions(unittest.TestCase):
    """Test is_known_irregular and list_irregular_verbs."""

    def test_is_known_irregular_true(self) -> None:
        self.assertTrue(is_known_irregular("être"))
        self.assertTrue(is_known_irregular("comprendre"))

    def test_is_known_irregular_false(self) -> None:
        self.assertFalse(is_known_irregular("parler"))
        self.assertFalse(is_known_irregular("finir"))

    def test_list_irregular_verbs_sorted(self) -> None:
        verbs = list_irregular_verbs()
        self.assertEqual(verbs, sorted(verbs))
        self.assertIn("être", verbs)
        self.assertIn("comprendre", verbs)

    def test_list_irregular_verbs_includes_compounds(self) -> None:
        verbs = list_irregular_verbs()
        self.assertIn("revenir", verbs)
        self.assertIn("permettre", verbs)


if __name__ == "__main__":
    unittest.main()
