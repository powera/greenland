"""Tests for rule-based Italian verb conjugation."""

import unittest

from langtools.it.conjugation import conjugate


class TestRegularAre(unittest.TestCase):
    """Test regular -are verb: parlare (to speak)."""

    def setUp(self) -> None:
        result = conjugate("parlare")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "parlo")
        self.assertEqual(self.forms["2s_present"], "parli")
        self.assertEqual(self.forms["3s_present"], "parla")
        self.assertEqual(self.forms["1p_present"], "parliamo")
        self.assertEqual(self.forms["2p_present"], "parlate")
        self.assertEqual(self.forms["3p_present"], "parlano")

    def test_imperfect(self) -> None:
        self.assertEqual(self.forms["1s_past"], "parlavo")
        self.assertEqual(self.forms["2s_past"], "parlavi")
        self.assertEqual(self.forms["3s_past"], "parlava")
        self.assertEqual(self.forms["1p_past"], "parlavamo")
        self.assertEqual(self.forms["2p_past"], "parlavate")
        self.assertEqual(self.forms["3p_past"], "parlavano")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "parlerò")
        self.assertEqual(self.forms["2s_future"], "parlerai")
        self.assertEqual(self.forms["3s_future"], "parlerà")
        self.assertEqual(self.forms["1p_future"], "parleremo")
        self.assertEqual(self.forms["2p_future"], "parlerete")
        self.assertEqual(self.forms["3p_future"], "parleranno")


class TestRegularEre(unittest.TestCase):
    """Test regular -ere verb: credere (to believe)."""

    def setUp(self) -> None:
        result = conjugate("credere")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "credo")
        self.assertEqual(self.forms["2s_present"], "credi")
        self.assertEqual(self.forms["3s_present"], "crede")
        self.assertEqual(self.forms["1p_present"], "crediamo")
        self.assertEqual(self.forms["2p_present"], "credete")
        self.assertEqual(self.forms["3p_present"], "credono")

    def test_imperfect(self) -> None:
        self.assertEqual(self.forms["1s_past"], "credevo")
        self.assertEqual(self.forms["2s_past"], "credevi")
        self.assertEqual(self.forms["3s_past"], "credeva")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "crederò")
        self.assertEqual(self.forms["2s_future"], "crederai")
        self.assertEqual(self.forms["3s_future"], "crederà")


class TestRegularIre(unittest.TestCase):
    """Test regular -ire verb: partire (to leave)."""

    def setUp(self) -> None:
        result = conjugate("partire")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "parto")
        self.assertEqual(self.forms["2s_present"], "parti")
        self.assertEqual(self.forms["3s_present"], "parte")
        self.assertEqual(self.forms["1p_present"], "partiamo")
        self.assertEqual(self.forms["2p_present"], "partite")
        self.assertEqual(self.forms["3p_present"], "partono")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "partirò")
        self.assertEqual(self.forms["2s_future"], "partirai")
        self.assertEqual(self.forms["3s_future"], "partirà")


class TestIrregularVerbsReturnNone(unittest.TestCase):
    """Irregular verbs must return None to trigger LLM fallback."""

    def test_essere(self) -> None:
        self.assertIsNone(conjugate("essere"))

    def test_avere(self) -> None:
        self.assertIsNone(conjugate("avere"))

    def test_andare(self) -> None:
        self.assertIsNone(conjugate("andare"))

    def test_fare(self) -> None:
        self.assertIsNone(conjugate("fare"))

    def test_dire(self) -> None:
        self.assertIsNone(conjugate("dire"))

    def test_potere(self) -> None:
        self.assertIsNone(conjugate("potere"))

    def test_volere(self) -> None:
        self.assertIsNone(conjugate("volere"))

    def test_venire(self) -> None:
        self.assertIsNone(conjugate("venire"))

    def test_isco_verbs(self) -> None:
        """The -isco subclass of -ire verbs must fall back to LLM."""
        self.assertIsNone(conjugate("capire"))
        self.assertIsNone(conjugate("finire"))
        self.assertIsNone(conjugate("preferire"))

    def test_non_verb(self) -> None:
        self.assertIsNone(conjugate("casa"))


class TestFormCompleteness(unittest.TestCase):
    """Ensure regular verbs produce all expected form keys."""

    def test_all_18_forms(self) -> None:
        result = conjugate("parlare")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result), 18)
        for person in ("1s", "2s", "3s", "1p", "2p", "3p"):
            for tense in ("present", "past", "future"):
                self.assertIn(f"{person}_{tense}", result)


if __name__ == "__main__":
    unittest.main()
