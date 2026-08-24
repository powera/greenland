"""Tests for rule-based Dutch verb conjugation."""

import unittest

from langtools.nl.conjugation import conjugate, _normalize_stem


class TestNormalizeStem(unittest.TestCase):
    """Test stem normalization including vowel doubling and devoicing."""

    def test_open_syllable_doubling(self) -> None:
        """CVC stems get vowel doubled: mak → maak."""
        stem, _ = _normalize_stem("maken")
        self.assertEqual(stem, "maak")

    def test_no_doubling_closed_syllable(self) -> None:
        """CVCC stems keep single vowel: werk → werk."""
        stem, _ = _normalize_stem("werken")
        self.assertEqual(stem, "werk")

    def test_v_to_f_devoicing(self) -> None:
        """Stem-final v becomes f: lev → leef."""
        stem, raw = _normalize_stem("leven")
        self.assertEqual(stem, "leef")
        self.assertEqual(raw, "lev")

    def test_z_to_s_devoicing(self) -> None:
        """Stem-final z becomes s: lez → lees."""
        stem, raw = _normalize_stem("lezen")
        self.assertEqual(stem, "lees")
        self.assertEqual(raw, "lez")

    def test_v_devoicing_without_doubling(self) -> None:
        """Verbs like 'geloven': gelov → geloof."""
        stem, _ = _normalize_stem("geloven")
        self.assertEqual(stem, "geloof")


class TestRegularMaken(unittest.TestCase):
    """Test regular verb: maken (to make)."""

    def setUp(self) -> None:
        result = conjugate("maken")
        self.assertIsNotNone(result)
        assert result is not None
        self.forms = result

    def test_present(self) -> None:
        self.assertEqual(self.forms["1s_present"], "maak")
        self.assertEqual(self.forms["2s_present"], "maakt")
        self.assertEqual(self.forms["3s_present"], "maakt")
        self.assertEqual(self.forms["1p_present"], "maken")
        self.assertEqual(self.forms["2p_present"], "maken")
        self.assertEqual(self.forms["3p_present"], "maken")

    def test_past(self) -> None:
        """'maak' ends in k → 't kofschip → -te suffix."""
        self.assertEqual(self.forms["1s_past"], "maakte")
        self.assertEqual(self.forms["2s_past"], "maakte")
        self.assertEqual(self.forms["3s_past"], "maakte")
        self.assertEqual(self.forms["1p_past"], "maakten")
        self.assertEqual(self.forms["2p_past"], "maakten")
        self.assertEqual(self.forms["3p_past"], "maakten")

    def test_future(self) -> None:
        self.assertEqual(self.forms["1s_future"], "zal maken")
        self.assertEqual(self.forms["2s_future"], "zult maken")
        self.assertEqual(self.forms["3s_future"], "zal maken")
        self.assertEqual(self.forms["1p_future"], "zullen maken")


class TestRegularWerken(unittest.TestCase):
    """Test regular verb: werken (to work)."""

    def test_present(self) -> None:
        result = conjugate("werken")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["1s_present"], "werk")
        self.assertEqual(result["2s_present"], "werkt")
        self.assertEqual(result["3s_present"], "werkt")

    def test_past_t_kofschip(self) -> None:
        """'werk' ends in k → -te."""
        result = conjugate("werken")
        assert result is not None
        self.assertEqual(result["1s_past"], "werkte")


class TestDevoicingVerbs(unittest.TestCase):
    """Test verbs requiring v→f / z→s devoicing."""

    def test_leven_present(self) -> None:
        """leven: stem 'leef' (v→f, with vowel doubling)."""
        result = conjugate("leven")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["1s_present"], "leef")
        self.assertEqual(result["2s_present"], "leeft")
        self.assertEqual(result["3s_present"], "leeft")

    def test_leven_past(self) -> None:
        """'t kofschip uses raw stem 'lev' (voiced) → -de suffix → leefde."""
        result = conjugate("leven")
        assert result is not None
        self.assertEqual(result["1s_past"], "leefde")
        self.assertEqual(result["1p_past"], "leefden")


class TestRegularWithDeSuffix(unittest.TestCase):
    """Test regular verbs that take -de past suffix."""

    def test_spelen(self) -> None:
        """spelen: stem 'speel' → ends in l → NOT in 't kofschip → -de."""
        result = conjugate("spelen")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["1s_present"], "speel")
        self.assertEqual(result["2s_present"], "speelt")
        self.assertEqual(result["1s_past"], "speelde")
        self.assertEqual(result["1p_past"], "speelden")


class TestDoubledConsonantStems(unittest.TestCase):
    """Verbs with a doubled consonant degeminate the stem (pakken → pak)."""

    def test_pakken(self) -> None:
        stem, raw = _normalize_stem("pakken")
        self.assertEqual(stem, "pak")
        self.assertEqual(raw, "pakk")
        result = conjugate("pakken")
        assert result is not None
        self.assertEqual(result["1s_present"], "pak")
        self.assertEqual(result["2s_present"], "pakt")
        self.assertEqual(result["1s_past"], "pakte")  # 't kofschip → -te

    def test_stoppen(self) -> None:
        result = conjugate("stoppen")
        assert result is not None
        self.assertEqual(result["1s_present"], "stop")
        self.assertEqual(result["3s_present"], "stopt")
        self.assertEqual(result["1s_past"], "stopte")

    def test_stellen_takes_de(self) -> None:
        """stellen: degeminate to 'stel', ends in l → -de past."""
        result = conjugate("stellen")
        assert result is not None
        self.assertEqual(result["1s_present"], "stel")
        self.assertEqual(result["1s_past"], "stelde")


class TestStemEndingInT(unittest.TestCase):
    """A stem ending in -t does not double the t in the present."""

    def test_zetten(self) -> None:
        """zetten: degeminate to 'zet'; 2s/3s stay 'zet'."""
        result = conjugate("zetten")
        assert result is not None
        self.assertEqual(result["1s_present"], "zet")
        self.assertEqual(result["2s_present"], "zet")
        self.assertEqual(result["3s_present"], "zet")
        self.assertEqual(result["1s_past"], "zette")

    def test_praten(self) -> None:
        """praten: vowel-doubled to 'praat'; no extra t."""
        result = conjugate("praten")
        assert result is not None
        self.assertEqual(result["1s_present"], "praat")
        self.assertEqual(result["3s_present"], "praat")
        self.assertEqual(result["1s_past"], "praatte")


class TestIrregularVerbsReturnNone(unittest.TestCase):
    """Irregular/strong verbs must return None to trigger LLM fallback."""

    def test_zijn(self) -> None:
        self.assertIsNone(conjugate("zijn"))

    def test_hebben(self) -> None:
        self.assertIsNone(conjugate("hebben"))

    def test_worden(self) -> None:
        self.assertIsNone(conjugate("worden"))

    def test_modals(self) -> None:
        self.assertIsNone(conjugate("kunnen"))
        self.assertIsNone(conjugate("moeten"))
        self.assertIsNone(conjugate("willen"))
        self.assertIsNone(conjugate("zullen"))

    def test_strong_verbs(self) -> None:
        self.assertIsNone(conjugate("gaan"))
        self.assertIsNone(conjugate("komen"))
        self.assertIsNone(conjugate("geven"))
        self.assertIsNone(conjugate("lezen"))
        self.assertIsNone(conjugate("schrijven"))

    def test_non_verb(self) -> None:
        """Words not ending in -en return None."""
        self.assertIsNone(conjugate("huis"))


class TestFormCompleteness(unittest.TestCase):
    """Ensure regular verbs produce all expected form keys."""

    def test_all_18_forms(self) -> None:
        result = conjugate("maken")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(len(result), 18)
        for person in ("1s", "2s", "3s", "1p", "2p", "3p"):
            for tense in ("present", "past", "future"):
                self.assertIn(f"{person}_{tense}", result)


if __name__ == "__main__":
    unittest.main()
