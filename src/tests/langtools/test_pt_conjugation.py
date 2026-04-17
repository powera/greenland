"""Tests for rule-based Portuguese verb conjugation."""

import unittest

from langtools.pt.conjugation import conjugate


class TestRegularAr(unittest.TestCase):
    """Test regular -ar verb: falar (to speak)."""

    def setUp(self) -> None:
        result = conjugate("falar")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "falo")
        self.assertEqual(self.forms["2s_present"], "falas")
        self.assertEqual(self.forms["3s_present"], "fala")
        self.assertEqual(self.forms["1p_present"], "falamos")
        self.assertEqual(self.forms["2p_present"], "falais")
        self.assertEqual(self.forms["3p_present"], "falam")

    def test_preterite(self) -> None:
        self.assertEqual(self.forms["1s_past"], "falei")
        self.assertEqual(self.forms["2s_past"], "falaste")
        self.assertEqual(self.forms["3s_past"], "falou")
        self.assertEqual(self.forms["1p_past"], "falamos")
        self.assertEqual(self.forms["2p_past"], "falastes")
        self.assertEqual(self.forms["3p_past"], "falaram")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "falarei")
        self.assertEqual(self.forms["2s_future"], "falarás")
        self.assertEqual(self.forms["3s_future"], "falará")
        self.assertEqual(self.forms["1p_future"], "falaremos")
        self.assertEqual(self.forms["2p_future"], "falareis")
        self.assertEqual(self.forms["3p_future"], "falarão")


class TestRegularEr(unittest.TestCase):
    """Test regular -er verb: comer (to eat)."""

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
        self.assertEqual(self.forms["2p_present"], "comeis")
        self.assertEqual(self.forms["3p_present"], "comem")

    def test_preterite(self) -> None:
        self.assertEqual(self.forms["1s_past"], "comi")
        self.assertEqual(self.forms["3s_past"], "comeu")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "comerei")
        self.assertEqual(self.forms["3s_future"], "comerá")


class TestRegularIr(unittest.TestCase):
    """Test regular -ir verb: partir (to leave)."""

    def setUp(self) -> None:
        result = conjugate("partir")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "parto")
        self.assertEqual(self.forms["2s_present"], "partes")
        self.assertEqual(self.forms["3s_present"], "parte")
        self.assertEqual(self.forms["1p_present"], "partimos")
        self.assertEqual(self.forms["2p_present"], "partis")
        self.assertEqual(self.forms["3p_present"], "partem")

    def test_preterite(self) -> None:
        self.assertEqual(self.forms["1s_past"], "parti")
        self.assertEqual(self.forms["3s_past"], "partiu")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "partirei")
        self.assertEqual(self.forms["3s_future"], "partirá")


class TestHardcodedIrregularVerbs(unittest.TestCase):
    """Common irregular verbs should be hard-coded for deterministic output."""

    def test_ser(self) -> None:
        result = conjugate("ser")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["1s_present"], "sou")
        self.assertEqual(result["3s_past"], "foi")
        self.assertEqual(result["3p_future"], "serão")

    def test_estar(self) -> None:
        result = conjugate("estar")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["1s_present"], "estou")
        self.assertEqual(result["3s_past"], "esteve")
        self.assertEqual(result["2p_future"], "estareis")


class TestIrregularVerbsFallback(unittest.TestCase):
    """Non-hardcoded irregular verbs should return None to trigger LLM fallback."""

    def test_ir(self) -> None:
        self.assertIsNone(conjugate("ir"))

    def test_ter(self) -> None:
        self.assertIsNone(conjugate("ter"))

    def test_fazer(self) -> None:
        self.assertIsNone(conjugate("fazer"))

    def test_dizer(self) -> None:
        self.assertIsNone(conjugate("dizer"))

    def test_poder(self) -> None:
        self.assertIsNone(conjugate("poder"))

    def test_querer(self) -> None:
        self.assertIsNone(conjugate("querer"))

    def test_vir(self) -> None:
        self.assertIsNone(conjugate("vir"))

    def test_non_verb(self) -> None:
        self.assertIsNone(conjugate("mesa"))


class TestFormCompleteness(unittest.TestCase):
    """Ensure regular verbs produce all expected form keys."""

    def test_all_18_forms(self) -> None:
        result = conjugate("falar")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result), 18)
        for person in ("1s", "2s", "3s", "1p", "2p", "3p"):
            for tense in ("present", "past", "future"):
                self.assertIn(f"{person}_{tense}", result)


if __name__ == "__main__":
    unittest.main()
