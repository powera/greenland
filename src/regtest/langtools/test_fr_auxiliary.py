"""Tests for the French passé composé auxiliary rule."""

import unittest

from langtools.fr.auxiliary import AVOIR, ETRE, pc_auxiliary


class TestPcAuxiliary(unittest.TestCase):
    def test_avoir_verbs(self) -> None:
        for verb in ("parler", "manger", "finir", "prendre", "avoir", "être", "faire du vélo"):
            self.assertEqual(pc_auxiliary(verb), AVOIR, verb)

    def test_etre_verbs(self) -> None:
        for verb in ("aller", "venir", "naître", "mourir", "devenir", "aller chercher"):
            self.assertEqual(pc_auxiliary(verb), ETRE, verb)

    def test_reflexive_verbs_take_etre(self) -> None:
        for verb in ("se laver", "s'asseoir", "s’habiller", "s'en aller", "se souvenir"):
            self.assertEqual(pc_auxiliary(verb), ETRE, verb)

    def test_sense_dependent_verbs_are_undecided(self) -> None:
        for verb in ("sortir", "passer", "monter", "descendre", "rentrer", "retourner"):
            self.assertIsNone(pc_auxiliary(verb), verb)

    def test_non_infinitive_is_undecided(self) -> None:
        self.assertIsNone(pc_auxiliary(""))
        self.assertIsNone(pc_auxiliary("bonjour"))


if __name__ == "__main__":
    unittest.main()
