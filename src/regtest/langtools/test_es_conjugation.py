"""Tests for rule-based Spanish verb conjugation."""

import unittest

from langtools.es.conjugation import conjugate, conjugate_safe, get_verb_class, get_stem


class TestVerbClassification(unittest.TestCase):
    def test_ar_verbs(self) -> None:
        self.assertEqual(get_verb_class("hablar"), "ar")
        self.assertEqual(get_verb_class("pensar"), "ar")

    def test_er_verbs(self) -> None:
        self.assertEqual(get_verb_class("comer"), "er")
        self.assertEqual(get_verb_class("tener"), "er")

    def test_ir_verbs(self) -> None:
        self.assertEqual(get_verb_class("vivir"), "ir")
        self.assertEqual(get_verb_class("reír"), "ir")

    def test_invalid(self) -> None:
        self.assertIsNone(get_verb_class("casa"))
        self.assertIsNone(get_verb_class(""))

    def test_stem(self) -> None:
        self.assertEqual(get_stem("hablar"), "habl")
        self.assertEqual(get_stem("comer"), "com")
        self.assertEqual(get_stem("vivir"), "viv")


class TestRegularAR(unittest.TestCase):
    """Test regular -ar verb: hablar."""

    def setUp(self) -> None:
        result = conjugate("hablar")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "hablo")
        self.assertEqual(self.forms["2s_present"], "hablas")
        self.assertEqual(self.forms["3s_present"], "habla")
        self.assertEqual(self.forms["1p_present"], "hablamos")
        self.assertEqual(self.forms["2p_present"], "habláis")
        self.assertEqual(self.forms["3p_present"], "hablan")

    def test_preterite(self) -> None:
        self.assertEqual(self.forms["1s_preterite"], "hablé")
        self.assertEqual(self.forms["2s_preterite"], "hablaste")
        self.assertEqual(self.forms["3s_preterite"], "habló")
        self.assertEqual(self.forms["1p_preterite"], "hablamos")
        self.assertEqual(self.forms["2p_preterite"], "hablasteis")
        self.assertEqual(self.forms["3p_preterite"], "hablaron")

    def test_imperfect(self) -> None:
        self.assertEqual(self.forms["1s_imperfect"], "hablaba")
        self.assertEqual(self.forms["2s_imperfect"], "hablabas")
        self.assertEqual(self.forms["3s_imperfect"], "hablaba")
        self.assertEqual(self.forms["1p_imperfect"], "hablábamos")
        self.assertEqual(self.forms["2p_imperfect"], "hablabais")
        self.assertEqual(self.forms["3p_imperfect"], "hablaban")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "hablaré")
        self.assertEqual(self.forms["2s_future"], "hablarás")
        self.assertEqual(self.forms["3s_future"], "hablará")
        self.assertEqual(self.forms["1p_future"], "hablaremos")
        self.assertEqual(self.forms["2p_future"], "hablaréis")
        self.assertEqual(self.forms["3p_future"], "hablarán")

    def test_conditional(self) -> None:
        self.assertEqual(self.forms["1s_conditional"], "hablaría")
        self.assertEqual(self.forms["2s_conditional"], "hablarías")
        self.assertEqual(self.forms["3s_conditional"], "hablaría")
        self.assertEqual(self.forms["1p_conditional"], "hablaríamos")
        self.assertEqual(self.forms["2p_conditional"], "hablaríais")
        self.assertEqual(self.forms["3p_conditional"], "hablarían")

    def test_subjunctive_present(self) -> None:
        self.assertEqual(self.forms["1s_subjunctive_present"], "hable")
        self.assertEqual(self.forms["2s_subjunctive_present"], "hables")
        self.assertEqual(self.forms["3s_subjunctive_present"], "hable")
        self.assertEqual(self.forms["1p_subjunctive_present"], "hablemos")
        self.assertEqual(self.forms["2p_subjunctive_present"], "habléis")
        self.assertEqual(self.forms["3p_subjunctive_present"], "hablen")

    def test_imperative(self) -> None:
        self.assertEqual(self.forms["2s_imperative"], "habla")
        self.assertEqual(self.forms["3s_imperative"], "hable")
        self.assertEqual(self.forms["1p_imperative"], "hablemos")
        self.assertEqual(self.forms["2p_imperative"], "hablad")
        self.assertEqual(self.forms["3p_imperative"], "hablen")

    def test_nonfinite(self) -> None:
        self.assertEqual(self.forms["infinitive"], "hablar")
        self.assertEqual(self.forms["gerund"], "hablando")
        self.assertEqual(self.forms["past_participle"], "hablado")


class TestRegularER(unittest.TestCase):
    """Test regular -er verb: comer."""

    def setUp(self) -> None:
        result = conjugate("comer")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "como")
        self.assertEqual(self.forms["2s_present"], "comes")
        self.assertEqual(self.forms["3s_present"], "come")
        self.assertEqual(self.forms["1p_present"], "comemos")
        self.assertEqual(self.forms["2p_present"], "coméis")
        self.assertEqual(self.forms["3p_present"], "comen")

    def test_preterite(self) -> None:
        self.assertEqual(self.forms["1s_preterite"], "comí")
        self.assertEqual(self.forms["3s_preterite"], "comió")

    def test_nonfinite(self) -> None:
        self.assertEqual(self.forms["gerund"], "comiendo")
        self.assertEqual(self.forms["past_participle"], "comido")


class TestRegularIR(unittest.TestCase):
    """Test regular -ir verb: vivir."""

    def setUp(self) -> None:
        result = conjugate("vivir")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "vivo")
        self.assertEqual(self.forms["2s_present"], "vives")
        self.assertEqual(self.forms["3s_present"], "vive")
        self.assertEqual(self.forms["1p_present"], "vivimos")
        self.assertEqual(self.forms["2p_present"], "vivís")
        self.assertEqual(self.forms["3p_present"], "viven")

    def test_nonfinite(self) -> None:
        self.assertEqual(self.forms["gerund"], "viviendo")
        self.assertEqual(self.forms["past_participle"], "vivido")


class TestStemChanging(unittest.TestCase):
    """Test stem-changing verbs."""

    def test_e_to_ie_ar(self) -> None:
        forms = conjugate("pensar")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "pienso")
        self.assertEqual(forms["2s_present"], "piensas")
        self.assertEqual(forms["3s_present"], "piensa")
        self.assertEqual(forms["1p_present"], "pensamos")  # no change
        self.assertEqual(forms["2p_present"], "pensáis")  # no change
        self.assertEqual(forms["3p_present"], "piensan")

    def test_o_to_ue(self) -> None:
        forms = conjugate("contar")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "cuento")
        self.assertEqual(forms["2s_present"], "cuentas")
        self.assertEqual(forms["1p_present"], "contamos")  # no change
        self.assertEqual(forms["3p_present"], "cuentan")

    def test_e_to_i(self) -> None:
        forms = conjugate("pedir")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "pido")
        self.assertEqual(forms["2s_present"], "pides")
        self.assertEqual(forms["1p_present"], "pedimos")  # no change
        self.assertEqual(forms["3p_present"], "piden")

    def test_u_to_ue(self) -> None:
        forms = conjugate("jugar")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "juego")
        self.assertEqual(forms["3s_present"], "juega")
        self.assertEqual(forms["1p_present"], "jugamos")

    def test_ir_preterite_stem_change(self) -> None:
        """For -ir stem-changers, 3s and 3p preterite get e→i or o→u."""
        forms = conjugate("dormir")
        assert forms is not None
        self.assertEqual(forms["3s_preterite"], "durmió")
        self.assertEqual(forms["3p_preterite"], "durmieron")
        self.assertEqual(forms["1s_preterite"], "dormí")  # no change

        forms2 = conjugate("pedir")
        assert forms2 is not None
        self.assertEqual(forms2["3s_preterite"], "pidió")
        self.assertEqual(forms2["3p_preterite"], "pidieron")

    def test_ir_gerund_stem_change(self) -> None:
        forms = conjugate("dormir")
        assert forms is not None
        self.assertEqual(forms["gerund"], "durmiendo")

        forms2 = conjugate("pedir")
        assert forms2 is not None
        self.assertEqual(forms2["gerund"], "pidiendo")


class TestIrregularFutureStem(unittest.TestCase):
    def test_tener(self) -> None:
        forms = conjugate("tener")
        assert forms is not None
        self.assertEqual(forms["1s_future"], "tendré")
        self.assertEqual(forms["2s_future"], "tendrás")
        self.assertEqual(forms["1s_conditional"], "tendría")

    def test_hacer(self) -> None:
        forms = conjugate("hacer")
        assert forms is not None
        self.assertEqual(forms["1s_future"], "haré")
        self.assertEqual(forms["3s_future"], "hará")

    def test_decir(self) -> None:
        forms = conjugate("decir")
        assert forms is not None
        self.assertEqual(forms["1s_future"], "diré")

    def test_salir(self) -> None:
        forms = conjugate("salir")
        assert forms is not None
        self.assertEqual(forms["1s_future"], "saldré")
        self.assertEqual(forms["1s_conditional"], "saldría")


class TestIrregularPreterite(unittest.TestCase):
    def test_tener(self) -> None:
        forms = conjugate("tener")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "tuve")
        self.assertEqual(forms["3s_preterite"], "tuvo")
        self.assertEqual(forms["3p_preterite"], "tuvieron")

    def test_hacer(self) -> None:
        forms = conjugate("hacer")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "hice")
        self.assertEqual(forms["3s_preterite"], "hizo")

    def test_decir(self) -> None:
        forms = conjugate("decir")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "dije")
        self.assertEqual(forms["3p_preterite"], "dijeron")  # -eron not -ieron

    def test_conducir(self) -> None:
        forms = conjugate("conducir")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "conduje")
        self.assertEqual(forms["3p_preterite"], "condujeron")


class TestIrregular1sPresent(unittest.TestCase):
    def test_conocer(self) -> None:
        forms = conjugate("conocer")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "conozco")
        self.assertEqual(forms["2s_present"], "conoces")  # regular otherwise

    def test_hacer(self) -> None:
        forms = conjugate("hacer")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "hago")

    def test_poner(self) -> None:
        forms = conjugate("poner")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "pongo")

    def test_saber(self) -> None:
        forms = conjugate("saber")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "sé")


class TestIrregularPastParticiple(unittest.TestCase):
    def test_escribir(self) -> None:
        forms = conjugate("escribir")
        assert forms is not None
        self.assertEqual(forms["past_participle"], "escrito")

    def test_hacer(self) -> None:
        forms = conjugate("hacer")
        assert forms is not None
        self.assertEqual(forms["past_participle"], "hecho")

    def test_volver(self) -> None:
        forms = conjugate("volver")
        assert forms is not None
        self.assertEqual(forms["past_participle"], "vuelto")


class TestFullyIrregular(unittest.TestCase):
    def test_ser_present(self) -> None:
        forms = conjugate("ser")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "soy")
        self.assertEqual(forms["2s_present"], "eres")
        self.assertEqual(forms["3s_present"], "es")
        self.assertEqual(forms["1p_present"], "somos")
        self.assertEqual(forms["3p_present"], "son")

    def test_ser_preterite(self) -> None:
        forms = conjugate("ser")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "fui")
        self.assertEqual(forms["3s_preterite"], "fue")

    def test_ser_imperfect(self) -> None:
        forms = conjugate("ser")
        assert forms is not None
        self.assertEqual(forms["1s_imperfect"], "era")
        self.assertEqual(forms["1p_imperfect"], "éramos")

    def test_ir_present(self) -> None:
        forms = conjugate("ir")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "voy")
        self.assertEqual(forms["3s_present"], "va")
        self.assertEqual(forms["1p_present"], "vamos")

    def test_ir_imperfect(self) -> None:
        forms = conjugate("ir")
        assert forms is not None
        self.assertEqual(forms["1s_imperfect"], "iba")

    def test_haber(self) -> None:
        forms = conjugate("haber")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "he")
        self.assertEqual(forms["3s_present"], "ha")

    def test_estar(self) -> None:
        forms = conjugate("estar")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "estoy")
        self.assertEqual(forms["3s_present"], "está")

    def test_dar(self) -> None:
        forms = conjugate("dar")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "doy")
        self.assertEqual(forms["1s_preterite"], "di")
        self.assertEqual(forms["3s_preterite"], "dio")


class TestImperative(unittest.TestCase):
    def test_regular_ar(self) -> None:
        forms = conjugate("hablar")
        assert forms is not None
        self.assertEqual(forms["2s_imperative"], "habla")
        self.assertEqual(forms["2p_imperative"], "hablad")

    def test_irregular_tu(self) -> None:
        forms = conjugate("hacer")
        assert forms is not None
        self.assertEqual(forms["2s_imperative"], "haz")

        forms2 = conjugate("decir")
        assert forms2 is not None
        self.assertEqual(forms2["2s_imperative"], "di")

        forms3 = conjugate("poner")
        assert forms3 is not None
        self.assertEqual(forms3["2s_imperative"], "pon")

    def test_usted_from_subjunctive(self) -> None:
        forms = conjugate("hablar")
        assert forms is not None
        self.assertEqual(forms["3s_imperative"], forms["3s_subjunctive_present"])


class TestSubjunctiveFromIrregular1s(unittest.TestCase):
    """Subjunctive should derive from irregular 1s present stem."""

    def test_hacer_subjunctive(self) -> None:
        forms = conjugate("hacer")
        assert forms is not None
        self.assertEqual(forms["1s_subjunctive_present"], "haga")
        self.assertEqual(forms["2s_subjunctive_present"], "hagas")
        self.assertEqual(forms["3p_subjunctive_present"], "hagan")

    def test_tener_subjunctive(self) -> None:
        forms = conjugate("tener")
        assert forms is not None
        self.assertEqual(forms["1s_subjunctive_present"], "tenga")
        self.assertEqual(forms["3s_subjunctive_present"], "tenga")

    def test_conocer_subjunctive(self) -> None:
        forms = conjugate("conocer")
        assert forms is not None
        self.assertEqual(forms["1s_subjunctive_present"], "conozca")
        self.assertEqual(forms["3p_subjunctive_present"], "conozcan")


class TestVer(unittest.TestCase):
    """Test 'ver' which has multiple irregularities."""

    def test_present(self) -> None:
        forms = conjugate("ver")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "veo")

    def test_imperfect(self) -> None:
        forms = conjugate("ver")
        assert forms is not None
        self.assertEqual(forms["1s_imperfect"], "veía")
        self.assertEqual(forms["3s_imperfect"], "veía")

    def test_past_participle(self) -> None:
        forms = conjugate("ver")
        assert forms is not None
        self.assertEqual(forms["past_participle"], "visto")


class TestGerundSpecialCases(unittest.TestCase):
    def test_leer(self) -> None:
        """Stem ends in vowel → -yendo."""
        forms = conjugate("leer")
        assert forms is not None
        self.assertEqual(forms["gerund"], "leyendo")

    def test_caer(self) -> None:
        forms = conjugate("caer")
        assert forms is not None
        self.assertEqual(forms["gerund"], "cayendo")


class TestSpellingChanges(unittest.TestCase):
    def test_buscar_preterite_yo(self) -> None:
        """buscar: c → qu before é in 1s preterite."""
        forms = conjugate("buscar")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "busqué")
        self.assertEqual(forms["2s_preterite"], "buscaste")  # no change

    def test_llegar_preterite_yo(self) -> None:
        """llegar: g → gu before é in 1s preterite."""
        forms = conjugate("llegar")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "llegué")

    def test_empezar_preterite_yo(self) -> None:
        """empezar: z → c before é in 1s preterite."""
        forms = conjugate("empezar")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "empecé")

    def test_buscar_subjunctive(self) -> None:
        """buscar: c → qu before e in subjunctive."""
        forms = conjugate("buscar")
        assert forms is not None
        self.assertEqual(forms["1s_subjunctive_present"], "busque")
        self.assertEqual(forms["3p_subjunctive_present"], "busquen")

    def test_llegar_subjunctive(self) -> None:
        """llegar: g → gu before e in subjunctive."""
        forms = conjugate("llegar")
        assert forms is not None
        self.assertEqual(forms["1s_subjunctive_present"], "llegue")


class TestFormCompleteness(unittest.TestCase):
    """Ensure all expected form keys are present."""

    def test_all_keys_present(self) -> None:
        from langtools.es.types import VerbConjugation

        forms = conjugate("hablar")
        assert forms is not None
        for key in VerbConjugation.ALL_FORMS:
            self.assertIn(key, forms, f"Missing form key: {key}")

    def test_all_keys_nonempty(self) -> None:
        forms = conjugate("hablar")
        assert forms is not None
        for key, val in forms.items():
            self.assertTrue(val, f"Empty value for form key: {key}")


class TestConjugateSafe(unittest.TestCase):
    def test_invalid_returns_warning(self) -> None:
        forms, warnings = conjugate_safe("casa")
        self.assertEqual(forms, {})
        self.assertEqual(len(warnings), 1)

    def test_valid_no_warnings_for_known(self) -> None:
        forms, warnings = conjugate_safe("hablar")
        self.assertIn("1s_present", forms)
        self.assertEqual(warnings, [])

    def test_warning_for_potential_irregular(self) -> None:
        """Verbs ending in -cer not in our table get a warning."""
        forms, warnings = conjugate_safe("vencer")
        self.assertIn("1s_present", forms)
        self.assertTrue(len(warnings) > 0)


class TestUirVerbs(unittest.TestCase):
    """-uir verbs insert a consonantal y (construir, huir)."""

    def test_construir_present(self) -> None:
        forms = conjugate("construir")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "construyo")
        self.assertEqual(forms["2s_present"], "construyes")
        self.assertEqual(forms["3s_present"], "construye")
        self.assertEqual(forms["1p_present"], "construimos")
        self.assertEqual(forms["2p_present"], "construís")
        self.assertEqual(forms["3p_present"], "construyen")

    def test_construir_preterite(self) -> None:
        forms = conjugate("construir")
        assert forms is not None
        self.assertEqual(forms["1s_preterite"], "construí")
        self.assertEqual(forms["3s_preterite"], "construyó")
        self.assertEqual(forms["3p_preterite"], "construyeron")

    def test_construir_subjunctive_and_nonfinite(self) -> None:
        forms = conjugate("construir")
        assert forms is not None
        self.assertEqual(forms["1s_subjunctive_present"], "construya")
        self.assertEqual(forms["1p_subjunctive_present"], "construyamos")
        self.assertEqual(forms["gerund"], "construyendo")
        self.assertEqual(forms["past_participle"], "construido")

    def test_huir(self) -> None:
        forms = conjugate("huir")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "huyo")
        self.assertEqual(forms["3p_present"], "huyen")
        self.assertEqual(forms["3s_preterite"], "huyó")

    def test_guir_verbs_get_no_y(self) -> None:
        """-guir verbs are NOT -uir y-verbs; the u is a silent digraph."""
        forms = conjugate("seguir")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "sigo")
        self.assertEqual(forms["2s_present"], "sigues")
        self.assertEqual(forms["3p_present"], "siguen")

    def test_distinguir_drops_u_before_o(self) -> None:
        forms = conjugate("distinguir")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "distingo")
        self.assertEqual(forms["2s_present"], "distingues")


class TestUcirVerbs(unittest.TestCase):
    def test_conducir_present(self) -> None:
        forms = conjugate("conducir")
        assert forms is not None
        self.assertEqual(forms["1s_present"], "conduzco")
        self.assertEqual(forms["2s_present"], "conduces")

    def test_traducir_subjunctive(self) -> None:
        forms = conjugate("traducir")
        assert forms is not None
        self.assertEqual(forms["1s_subjunctive_present"], "traduzca")
        self.assertEqual(forms["3p_subjunctive_present"], "traduzcan")


if __name__ == "__main__":
    unittest.main()
