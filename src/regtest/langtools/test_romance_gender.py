"""Tests for the Spanish and French ending-based gender cross-checks."""

import unittest

from langtools.es.gender import predict_gender as es_gender
from langtools.fr.gender import predict_gender as fr_gender


class TestSpanishGender(unittest.TestCase):
    def test_feminine_suffixes(self) -> None:
        for noun in ("canción", "ciudad", "libertad", "actitud", "costumbre", "casa"):
            self.assertEqual(es_gender(noun), "feminine", noun)

    def test_masculine_suffixes(self) -> None:
        for noun in ("viaje", "color", "libro", "día", "mapa"):
            self.assertEqual(es_gender(noun), "masculine", noun)

    def test_exceptions(self) -> None:
        self.assertEqual(es_gender("mano"), "feminine")
        self.assertEqual(es_gender("foto"), "feminine")
        self.assertEqual(es_gender("flor"), "feminine")

    def test_no_prediction(self) -> None:
        # -ma (el problema / la cama), -ista (el/la artista), -e, consonants
        for noun in ("problema", "cama", "artista", "leche", "papel", "Keytruda"):
            self.assertIsNone(es_gender(noun), noun)

    def test_multiword_uses_head(self) -> None:
        self.assertEqual(es_gender("polo sur"), "masculine")
        self.assertEqual(es_gender("tarjeta de crédito"), "feminine")


class TestFrenchGender(unittest.TestCase):
    def test_feminine_suffixes(self) -> None:
        for noun in (
            "nation",
            "télévision",
            "qualité",
            "fourchette",
            "chance",
            "sagesse",
            "voiture",
        ):
            self.assertEqual(fr_gender(noun), "feminine", noun)

    def test_masculine_suffixes(self) -> None:
        for noun in ("moment", "fromage", "bateau", "miroir", "cahier", "travail", "sommeil"):
            self.assertEqual(fr_gender(noun), "masculine", noun)

    def test_exceptions(self) -> None:
        self.assertEqual(fr_gender("plage"), "feminine")
        self.assertEqual(fr_gender("eau"), "feminine")
        self.assertEqual(fr_gender("silence"), "masculine")
        self.assertEqual(fr_gender("comité"), "masculine")

    def test_no_prediction(self) -> None:
        for noun in ("livre", "table", "main", "Paris"):
            self.assertIsNone(fr_gender(noun), noun)

    def test_multiword_uses_head(self) -> None:
        self.assertEqual(fr_gender("pomme de terre"), None)
        self.assertEqual(fr_gender("salle à manger"), None)
        self.assertEqual(fr_gender("machine à laver"), None)
        self.assertEqual(fr_gender("fromage blanc"), "masculine")


if __name__ == "__main__":
    unittest.main()
