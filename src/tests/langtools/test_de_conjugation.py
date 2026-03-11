"""Tests for rule-based German verb conjugation."""

import unittest

from langtools.de.conjugation import conjugate


class TestRegularWeak(unittest.TestCase):
    """Test regular weak verb: machen (to make)."""

    def setUp(self) -> None:
        result = conjugate("machen")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "mache")
        self.assertEqual(self.forms["2s_present"], "machst")
        self.assertEqual(self.forms["3s_present"], "macht")
        self.assertEqual(self.forms["1p_present"], "machen")
        self.assertEqual(self.forms["2p_present"], "macht")
        self.assertEqual(self.forms["3p_present"], "machen")

    def test_past(self) -> None:
        self.assertEqual(self.forms["1s_past"], "machte")
        self.assertEqual(self.forms["2s_past"], "machtest")
        self.assertEqual(self.forms["3s_past"], "machte")
        self.assertEqual(self.forms["1p_past"], "machten")
        self.assertEqual(self.forms["2p_past"], "machtet")
        self.assertEqual(self.forms["3p_past"], "machten")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "werde machen")
        self.assertEqual(self.forms["2s_future"], "wirst machen")
        self.assertEqual(self.forms["3s_future"], "wird machen")
        self.assertEqual(self.forms["1p_future"], "werden machen")
        self.assertEqual(self.forms["2p_future"], "werdet machen")
        self.assertEqual(self.forms["3p_future"], "werden machen")


class TestStemEndingInT(unittest.TestCase):
    """Test -t/-d stem epenthesis: arbeiten (to work)."""

    def setUp(self) -> None:
        result = conjugate("arbeiten")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present_epenthesis(self) -> None:
        """2s and 3s/2p get linking -e- before -st/-t endings."""
        self.assertEqual(self.forms["1s_present"], "arbeite")
        self.assertEqual(self.forms["2s_present"], "arbeitest")
        self.assertEqual(self.forms["3s_present"], "arbeitet")
        self.assertEqual(self.forms["1p_present"], "arbeiten")
        self.assertEqual(self.forms["2p_present"], "arbeitet")
        self.assertEqual(self.forms["3p_present"], "arbeiten")

    def test_past_epenthesis(self) -> None:
        self.assertEqual(self.forms["1s_past"], "arbeitete")
        self.assertEqual(self.forms["2s_past"], "arbeitetest")
        self.assertEqual(self.forms["3s_past"], "arbeitete")
        self.assertEqual(self.forms["2p_past"], "arbeitetet")


class TestStemEndingInD(unittest.TestCase):
    """Test -d stem epenthesis: reden (to talk)."""

    def setUp(self) -> None:
        result = conjugate("reden")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present_epenthesis(self) -> None:
        self.assertEqual(self.forms["2s_present"], "redest")
        self.assertEqual(self.forms["3s_present"], "redet")
        self.assertEqual(self.forms["2p_present"], "redet")


class TestRegularLernen(unittest.TestCase):
    """Test another regular verb: lernen (to learn)."""

    def test_present(self) -> None:
        result = conjugate("lernen")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["1s_present"], "lerne")
        self.assertEqual(result["2s_present"], "lernst")
        self.assertEqual(result["3s_present"], "lernt")


class TestIrregularVerbsReturnNone(unittest.TestCase):
    """Irregular/strong/modal verbs must return None to trigger LLM fallback."""

    def test_sein(self) -> None:
        self.assertIsNone(conjugate("sein"))

    def test_haben(self) -> None:
        self.assertIsNone(conjugate("haben"))

    def test_werden(self) -> None:
        self.assertIsNone(conjugate("werden"))

    def test_modals(self) -> None:
        self.assertIsNone(conjugate("können"))
        self.assertIsNone(conjugate("müssen"))
        self.assertIsNone(conjugate("wollen"))
        self.assertIsNone(conjugate("dürfen"))

    def test_strong_verbs(self) -> None:
        self.assertIsNone(conjugate("gehen"))
        self.assertIsNone(conjugate("kommen"))
        self.assertIsNone(conjugate("geben"))
        self.assertIsNone(conjugate("nehmen"))
        self.assertIsNone(conjugate("sprechen"))
        self.assertIsNone(conjugate("sehen"))
        self.assertIsNone(conjugate("fahren"))

    def test_non_verb(self) -> None:
        self.assertIsNone(conjugate("Haus"))


class TestFormCompleteness(unittest.TestCase):
    """Ensure regular verbs produce all expected form keys."""

    def test_all_18_forms(self) -> None:
        result = conjugate("machen")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result), 18)
        for person in ("1s", "2s", "3s", "1p", "2p", "3p"):
            for tense in ("present", "past", "future"):
                self.assertIn(f"{person}_{tense}", result)


if __name__ == "__main__":
    unittest.main()
