"""Tests for rule-based Swedish verb conjugation."""

import unittest

from langtools.sv.conjugation import conjugate


class TestRegularGroup1(unittest.TestCase):
    """Test Group 1 (-ar) verb: tala (to speak)."""

    def test_present(self) -> None:
        result = conjugate("tala")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["present"], "talar")

    def test_past(self) -> None:
        result = conjugate("tala")
        assert result is not None
        self.assertEqual(result["past"], "talade")

    def test_future(self) -> None:
        result = conjugate("tala")
        assert result is not None
        self.assertEqual(result["future"], "ska tala")

    def test_all_three_forms(self) -> None:
        result = conjugate("tala")
        assert result is not None
        self.assertEqual(len(result), 3)
        self.assertIn("present", result)
        self.assertIn("past", result)
        self.assertIn("future", result)


class TestOtherGroup1Verbs(unittest.TestCase):
    """Test various Group 1 verbs."""

    def test_arbeta(self) -> None:
        result = conjugate("arbeta")
        assert result is not None
        self.assertEqual(result["present"], "arbetar")
        self.assertEqual(result["past"], "arbetade")

    def test_spela(self) -> None:
        result = conjugate("spela")
        assert result is not None
        self.assertEqual(result["present"], "spelar")
        self.assertEqual(result["past"], "spelade")


class TestIrregularVerbsReturnNone(unittest.TestCase):
    """Irregular and non-Group-1 verbs must return None."""

    def test_vara(self) -> None:
        self.assertIsNone(conjugate("vara"))

    def test_ha(self) -> None:
        """'ha' doesn't end in -a... wait it does. But it's in the blocklist."""
        self.assertIsNone(conjugate("ha"))

    def test_gora(self) -> None:
        self.assertIsNone(conjugate("göra"))

    def test_bli(self) -> None:
        """Doesn't end in -a → returns None."""
        self.assertIsNone(conjugate("bli"))

    def test_group2_verbs(self) -> None:
        """Group 2 verbs ending in -a must NOT get Group 1 treatment."""
        self.assertIsNone(conjugate("ringa"))
        self.assertIsNone(conjugate("stänga"))
        self.assertIsNone(conjugate("bygga"))
        self.assertIsNone(conjugate("lägga"))
        self.assertIsNone(conjugate("köra"))

    def test_non_verb(self) -> None:
        self.assertIsNone(conjugate("bok"))


if __name__ == "__main__":
    unittest.main()
