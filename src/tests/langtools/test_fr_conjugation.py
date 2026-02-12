"""Tests for rule-based French verb conjugation."""

import unittest

from langtools.fr.conjugation import conjugate, is_known_irregular, list_irregular_verbs
from langtools.fr.types import VerbConjugation


class TestRegularErVerbs(unittest.TestCase):
    """Test first-group (-er) regular conjugation."""

    def test_parler_present(self) -> None:
        result, ok = conjugate("parler")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "parle")
        self.assertEqual(result.forms["2s_present"], "parles")
        self.assertEqual(result.forms["3s_present"], "parle")
        self.assertEqual(result.forms["1p_present"], "parlons")
        self.assertEqual(result.forms["2p_present"], "parlez")
        self.assertEqual(result.forms["3p_present"], "parlent")

    def test_parler_imperfect(self) -> None:
        result, ok = conjugate("parler")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_impf"], "parlais")
        self.assertEqual(result.forms["2s_impf"], "parlais")
        self.assertEqual(result.forms["3s_impf"], "parlait")
        self.assertEqual(result.forms["1p_impf"], "parlions")
        self.assertEqual(result.forms["2p_impf"], "parliez")
        self.assertEqual(result.forms["3p_impf"], "parlaient")

    def test_parler_future(self) -> None:
        result, ok = conjugate("parler")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_future"], "parlerai")
        self.assertEqual(result.forms["2s_future"], "parleras")
        self.assertEqual(result.forms["3s_future"], "parlera")
        self.assertEqual(result.forms["1p_future"], "parlerons")
        self.assertEqual(result.forms["2p_future"], "parlerez")
        self.assertEqual(result.forms["3p_future"], "parleront")

    def test_parler_past_participle(self) -> None:
        result, ok = conjugate("parler")
        self.assertTrue(ok)
        self.assertEqual(result.forms["pc_m"], "parlé")
        self.assertEqual(result.forms["pc_f"], "parlée")

    def test_parler_metadata(self) -> None:
        result, ok = conjugate("parler")
        self.assertTrue(ok)
        self.assertEqual(result.word, "parler")
        self.assertEqual(result.notes, "regular -er")
        self.assertEqual(result.confidence, 1.0)

    def test_all_20_forms_present(self) -> None:
        result, ok = conjugate("parler")
        self.assertTrue(ok)
        self.assertEqual(len(result.forms), 20)
        for form_name in VerbConjugation.ALL_FORMS:
            self.assertIn(form_name, result.forms)


class TestGerVerbs(unittest.TestCase):
    """Test -ger orthographic adjustment."""

    def test_manger_present(self) -> None:
        result, ok = conjugate("manger")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "mange")
        self.assertEqual(result.forms["1p_present"], "mangeons")
        self.assertEqual(result.forms["2p_present"], "mangez")
        self.assertEqual(result.forms["3p_present"], "mangent")

    def test_manger_imperfect(self) -> None:
        result, ok = conjugate("manger")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_impf"], "mangeais")
        self.assertEqual(result.forms["3s_impf"], "mangeait")
        self.assertEqual(result.forms["1p_impf"], "mangions")
        self.assertEqual(result.forms["2p_impf"], "mangiez")
        self.assertEqual(result.forms["3p_impf"], "mangeaient")


class TestCerVerbs(unittest.TestCase):
    """Test -cer orthographic adjustment."""

    def test_commencer_present(self) -> None:
        result, ok = conjugate("commencer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "commence")
        self.assertEqual(result.forms["1p_present"], "commençons")
        self.assertEqual(result.forms["2p_present"], "commencez")

    def test_commencer_imperfect(self) -> None:
        result, ok = conjugate("commencer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_impf"], "commençais")
        self.assertEqual(result.forms["3s_impf"], "commençait")
        self.assertEqual(result.forms["1p_impf"], "commencions")
        self.assertEqual(result.forms["2p_impf"], "commenciez")
        self.assertEqual(result.forms["3p_impf"], "commençaient")


class TestYerVerbs(unittest.TestCase):
    """Test -yer stem change (y -> i before silent endings)."""

    def test_payer_present(self) -> None:
        result, ok = conjugate("payer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "paie")
        self.assertEqual(result.forms["2s_present"], "paies")
        self.assertEqual(result.forms["3s_present"], "paie")
        self.assertEqual(result.forms["1p_present"], "payons")
        self.assertEqual(result.forms["2p_present"], "payez")
        self.assertEqual(result.forms["3p_present"], "paient")

    def test_nettoyer_present(self) -> None:
        result, ok = conjugate("nettoyer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "nettoie")
        self.assertEqual(result.forms["1p_present"], "nettoyons")
        self.assertEqual(result.forms["3p_present"], "nettoient")

    def test_payer_future(self) -> None:
        result, ok = conjugate("payer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_future"], "paierai")
        self.assertEqual(result.forms["3p_future"], "paieront")

    def test_payer_imperfect_keeps_y(self) -> None:
        result, ok = conjugate("payer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_impf"], "payais")
        self.assertEqual(result.forms["1p_impf"], "payions")

    def test_payer_past_participle(self) -> None:
        result, ok = conjugate("payer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["pc_m"], "payé")
        self.assertEqual(result.forms["pc_f"], "payée")


class TestRegularIrVerbs(unittest.TestCase):
    """Test second-group (-ir with -iss-) regular conjugation."""

    def test_finir_present(self) -> None:
        result, ok = conjugate("finir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "finis")
        self.assertEqual(result.forms["2s_present"], "finis")
        self.assertEqual(result.forms["3s_present"], "finit")
        self.assertEqual(result.forms["1p_present"], "finissons")
        self.assertEqual(result.forms["2p_present"], "finissez")
        self.assertEqual(result.forms["3p_present"], "finissent")

    def test_finir_imperfect(self) -> None:
        result, ok = conjugate("finir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_impf"], "finissais")
        self.assertEqual(result.forms["1p_impf"], "finissions")

    def test_finir_future(self) -> None:
        result, ok = conjugate("finir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_future"], "finirai")
        self.assertEqual(result.forms["3p_future"], "finiront")

    def test_finir_past_participle(self) -> None:
        result, ok = conjugate("finir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["pc_m"], "fini")
        self.assertEqual(result.forms["pc_f"], "finie")

    def test_choisir(self) -> None:
        result, ok = conjugate("choisir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "choisis")
        self.assertEqual(result.forms["1p_present"], "choisissons")
        self.assertEqual(result.forms["1s_impf"], "choisissais")

    def test_ir_confidence(self) -> None:
        result, ok = conjugate("choisir")
        self.assertTrue(ok)
        self.assertEqual(result.confidence, 0.8)
        self.assertIn("assumed second group", result.notes or "")


class TestRegularReVerbs(unittest.TestCase):
    """Test regular third-group (-re) conjugation."""

    def test_vendre_present(self) -> None:
        result, ok = conjugate("vendre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "vends")
        self.assertEqual(result.forms["2s_present"], "vends")
        self.assertEqual(result.forms["3s_present"], "vend")
        self.assertEqual(result.forms["1p_present"], "vendons")
        self.assertEqual(result.forms["2p_present"], "vendez")
        self.assertEqual(result.forms["3p_present"], "vendent")

    def test_vendre_imperfect(self) -> None:
        result, ok = conjugate("vendre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_impf"], "vendais")
        self.assertEqual(result.forms["1p_impf"], "vendions")

    def test_vendre_future(self) -> None:
        result, ok = conjugate("vendre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_future"], "vendrai")
        self.assertEqual(result.forms["3p_future"], "vendront")

    def test_vendre_past_participle(self) -> None:
        result, ok = conjugate("vendre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["pc_m"], "vendu")
        self.assertEqual(result.forms["pc_f"], "vendue")

    def test_attendre(self) -> None:
        result, ok = conjugate("attendre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "attends")
        self.assertEqual(result.forms["3s_present"], "attend")
        self.assertEqual(result.forms["1s_future"], "attendrai")
        self.assertEqual(result.forms["pc_m"], "attendu")


class TestIrregularVerbs(unittest.TestCase):
    """Test hard-coded irregular verbs."""

    def test_etre(self) -> None:
        result, ok = conjugate("être")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "suis")
        self.assertEqual(result.forms["2s_present"], "es")
        self.assertEqual(result.forms["3s_present"], "est")
        self.assertEqual(result.forms["1p_present"], "sommes")
        self.assertEqual(result.forms["2p_present"], "êtes")
        self.assertEqual(result.forms["3p_present"], "sont")
        # imperfect (special stem ét-)
        self.assertEqual(result.forms["1s_impf"], "étais")
        self.assertEqual(result.forms["1p_impf"], "étions")
        self.assertEqual(result.forms["3p_impf"], "étaient")
        # future
        self.assertEqual(result.forms["1s_future"], "serai")
        self.assertEqual(result.forms["3p_future"], "seront")
        # past participle
        self.assertEqual(result.forms["pc_m"], "été")
        self.assertEqual(result.forms["pc_f"], "été")

    def test_avoir(self) -> None:
        result, ok = conjugate("avoir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "ai")
        self.assertEqual(result.forms["3s_present"], "a")
        self.assertEqual(result.forms["3p_present"], "ont")
        self.assertEqual(result.forms["1s_impf"], "avais")
        self.assertEqual(result.forms["1s_future"], "aurai")
        self.assertEqual(result.forms["pc_m"], "eu")
        self.assertEqual(result.forms["pc_f"], "eue")

    def test_aller(self) -> None:
        result, ok = conjugate("aller")
        self.assertTrue(ok)
        # aller is irregular, NOT treated as regular -er
        self.assertEqual(result.forms["1s_present"], "vais")
        self.assertEqual(result.forms["3p_present"], "vont")
        self.assertEqual(result.forms["1s_future"], "irai")
        self.assertEqual(result.forms["pc_m"], "allé")

    def test_faire(self) -> None:
        result, ok = conjugate("faire")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "fais")
        self.assertEqual(result.forms["2p_present"], "faites")
        self.assertEqual(result.forms["3p_present"], "font")
        self.assertEqual(result.forms["1s_future"], "ferai")
        self.assertEqual(result.forms["pc_m"], "fait")

    def test_pouvoir(self) -> None:
        result, ok = conjugate("pouvoir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "peux")
        self.assertEqual(result.forms["3p_present"], "peuvent")
        self.assertEqual(result.forms["1s_future"], "pourrai")
        self.assertEqual(result.forms["pc_m"], "pu")

    def test_vouloir(self) -> None:
        result, ok = conjugate("vouloir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "veux")
        self.assertEqual(result.forms["3p_present"], "veulent")
        self.assertEqual(result.forms["1s_future"], "voudrai")

    def test_venir(self) -> None:
        result, ok = conjugate("venir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "viens")
        self.assertEqual(result.forms["1p_present"], "venons")
        self.assertEqual(result.forms["3p_present"], "viennent")
        self.assertEqual(result.forms["1s_impf"], "venais")
        self.assertEqual(result.forms["1s_future"], "viendrai")
        self.assertEqual(result.forms["pc_m"], "venu")

    def test_prendre(self) -> None:
        result, ok = conjugate("prendre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "prends")
        self.assertEqual(result.forms["3s_present"], "prend")
        self.assertEqual(result.forms["3p_present"], "prennent")
        self.assertEqual(result.forms["1s_future"], "prendrai")
        self.assertEqual(result.forms["pc_m"], "pris")
        self.assertEqual(result.forms["pc_f"], "prise")

    def test_voir(self) -> None:
        result, ok = conjugate("voir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "vois")
        self.assertEqual(result.forms["1s_impf"], "voyais")
        self.assertEqual(result.forms["1s_future"], "verrai")
        self.assertEqual(result.forms["pc_m"], "vu")

    def test_dire(self) -> None:
        result, ok = conjugate("dire")
        self.assertTrue(ok)
        self.assertEqual(result.forms["2p_present"], "dites")
        self.assertEqual(result.forms["pc_m"], "dit")

    def test_mettre(self) -> None:
        result, ok = conjugate("mettre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["3s_present"], "met")
        self.assertEqual(result.forms["1s_future"], "mettrai")
        self.assertEqual(result.forms["pc_m"], "mis")

    def test_partir(self) -> None:
        result, ok = conjugate("partir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "pars")
        self.assertEqual(result.forms["1p_present"], "partons")
        self.assertEqual(result.forms["1s_future"], "partirai")
        self.assertEqual(result.forms["pc_m"], "parti")

    def test_ouvrir(self) -> None:
        result, ok = conjugate("ouvrir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "ouvre")
        self.assertEqual(result.forms["1p_present"], "ouvrons")
        self.assertEqual(result.forms["pc_m"], "ouvert")

    def test_mourir(self) -> None:
        result, ok = conjugate("mourir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "meurs")
        self.assertEqual(result.forms["1p_present"], "mourons")
        self.assertEqual(result.forms["1s_future"], "mourrai")

    def test_envoyer(self) -> None:
        result, ok = conjugate("envoyer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "envoie")
        self.assertEqual(result.forms["1p_present"], "envoyons")
        self.assertEqual(result.forms["1s_future"], "enverrai")

    def test_irregular_notes(self) -> None:
        result, ok = conjugate("être")
        self.assertTrue(ok)
        self.assertEqual(result.notes, "irregular")

    def test_all_irregulars_have_20_forms(self) -> None:
        for verb in list_irregular_verbs():
            result, ok = conjugate(verb)
            self.assertTrue(ok, f"{verb} should conjugate successfully")
            self.assertEqual(
                len(result.forms),
                20,
                f"{verb} should have 20 forms, got {len(result.forms)}",
            )


class TestCompoundVerbs(unittest.TestCase):
    """Test compound verbs derived from irregular bases."""

    def test_comprendre(self) -> None:
        result, ok = conjugate("comprendre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "comprends")
        self.assertEqual(result.forms["3p_present"], "comprennent")
        self.assertEqual(result.forms["1s_impf"], "comprenais")
        self.assertEqual(result.forms["1s_future"], "comprendrai")
        self.assertEqual(result.forms["pc_m"], "compris")
        self.assertEqual(result.forms["pc_f"], "comprise")

    def test_revenir(self) -> None:
        result, ok = conjugate("revenir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "reviens")
        self.assertEqual(result.forms["1p_present"], "revenons")
        self.assertEqual(result.forms["3p_present"], "reviennent")
        self.assertEqual(result.forms["1s_future"], "reviendrai")
        self.assertEqual(result.forms["pc_m"], "revenu")

    def test_permettre(self) -> None:
        result, ok = conjugate("permettre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "permets")
        self.assertEqual(result.forms["3s_present"], "permet")
        self.assertEqual(result.forms["1s_future"], "permettrai")
        self.assertEqual(result.forms["pc_m"], "permis")

    def test_defaire(self) -> None:
        result, ok = conjugate("défaire")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "défais")
        self.assertEqual(result.forms["2p_present"], "défaites")
        self.assertEqual(result.forms["3p_present"], "défont")
        self.assertEqual(result.forms["1s_future"], "déferai")

    def test_decouvrir(self) -> None:
        result, ok = conjugate("découvrir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "découvre")
        self.assertEqual(result.forms["1p_present"], "découvrons")
        self.assertEqual(result.forms["pc_m"], "découvert")

    def test_obtenir(self) -> None:
        result, ok = conjugate("obtenir")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "obtiens")
        self.assertEqual(result.forms["3p_present"], "obtiennent")
        self.assertEqual(result.forms["1s_future"], "obtiendrai")
        self.assertEqual(result.forms["pc_m"], "obtenu")

    def test_apprendre(self) -> None:
        result, ok = conjugate("apprendre")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "apprends")
        self.assertEqual(result.forms["3p_present"], "apprennent")
        self.assertEqual(result.forms["pc_m"], "appris")

    def test_renvoyer(self) -> None:
        result, ok = conjugate("renvoyer")
        self.assertTrue(ok)
        self.assertEqual(result.forms["1s_present"], "renvoie")
        self.assertEqual(result.forms["1p_present"], "renvoyons")
        self.assertEqual(result.forms["1s_future"], "renverrai")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_empty_string(self) -> None:
        result, ok = conjugate("")
        self.assertFalse(ok)

    def test_whitespace_only(self) -> None:
        result, ok = conjugate("   ")
        self.assertFalse(ok)

    def test_unknown_ending(self) -> None:
        result, ok = conjugate("xyz")
        self.assertFalse(ok)
        self.assertEqual(result.word, "xyz")

    def test_whitespace_stripped(self) -> None:
        result, ok = conjugate("  parler  ")
        self.assertTrue(ok)
        self.assertEqual(result.word, "parler")
        self.assertEqual(result.forms["1s_present"], "parle")

    def test_two_char_er_not_conjugated(self) -> None:
        """A two-character 'er' is not a valid verb."""
        result, ok = conjugate("er")
        self.assertFalse(ok)


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
