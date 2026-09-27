"""Tests for rule-based surface-token -> lemma matching (langtools.tokenizer)."""

import unittest
from typing import List, Tuple

from langtools.tokenizer import lemma_lookup_keys, split_contractions, surface_matches_lemma

# (language, surface, lemma) pairs that must match.
MATCHES: List[Tuple[str, str, str]] = [
    # Spanish: plurals, gender, stem changes, spelling changes, enclitics.
    ("es", "canciones", "canción"),
    ("es", "jóvenes", "joven"),
    ("es", "luces", "luz"),
    ("es", "bonitas", "bonito"),
    ("es", "rápidamente", "rápido"),
    ("es", "quiero", "querer"),
    ("es", "puedes", "poder"),
    ("es", "pide", "pedir"),
    ("es", "busqué", "buscar"),
    ("es", "conozco", "conocer"),
    ("es", "hablaré", "hablar"),
    ("es", "levantándose", "levantarse"),
    ("es", "se quedó", "quedarse"),
    ("es", "fue", "ir"),
    ("es-419", "comimos", "comer"),
    # Portuguese.
    ("pt", "canções", "canção"),
    ("pt", "animais", "animal"),
    ("pt", "homens", "homem"),
    ("pt", "levantou-se", "levantar-se"),
    ("pt", "falarei", "falar"),
    ("pt", "comemos", "comer"),
    ("pt", "busquei", "buscar"),
    ("pt", "fiz", "fazer"),
    # Italian.
    ("it", "libri", "libro"),
    ("it", "amiche", "amica"),
    ("it", "facilmente", "facile"),
    ("it", "cercherò", "cercare"),
    ("it", "mangi", "mangiare"),
    ("it", "parlavano", "parlare"),
    ("it", "finisco", "finire"),
    ("it", "alzarmi", "alzarsi"),
    ("it", "svegliato", "svegliarsi"),
    # French.
    ("fr", "chevaux", "cheval"),
    ("fr", "heureuse", "heureux"),
    ("fr", "lentement", "lent"),
    ("fr", "achète", "acheter"),
    ("fr", "mangeons", "manger"),
    ("fr", "finissons", "finir"),
    ("fr", "vendu", "vendre"),
    ("fr", "parlerai", "parler"),
    ("fr", "vendrai", "vendre"),
    ("fr", "lève", "se lever"),
    ("fr", "assis", "s'asseoir"),
    # German: umlaut plurals, comparison, participles, vowel changes.
    ("de", "Häuser", "Haus"),
    ("de", "Mütter", "Mutter"),
    ("de", "Kindern", "Kind"),
    ("de", "Freundinnen", "Freundin"),
    ("de", "größer", "groß"),
    ("de", "gemacht", "machen"),
    ("de", "arbeitete", "arbeiten"),
    ("de", "angerufen", "anrufen"),
    ("de", "liest", "lesen"),
    ("de", "fährt", "fahren"),
    ("de", "erinnere", "sich erinnern"),
    # Dutch: vowel/consonant doubling, v/z devoicing, participles.
    ("nl", "bomen", "boom"),
    ("nl", "katten", "kat"),
    ("nl", "brieven", "brief"),
    ("nl", "huizen", "huis"),
    ("nl", "huisje", "huis"),
    ("nl", "grote", "groot"),
    ("nl", "loopt", "lopen"),
    ("nl", "leeft", "leven"),
    ("nl", "gewerkt", "werken"),
    ("nl", "opgebeld", "opbellen"),
    # Swedish: definite/plural suffixes, verb groups, s-forms.
    ("sv", "bilarna", "bil"),
    ("sv", "flickor", "flicka"),
    ("sv", "pojkar", "pojke"),
    ("sv", "huset", "hus"),
    ("sv", "stort", "stor"),
    ("sv", "läser", "läsa"),
    ("sv", "hörde", "höra"),
    ("sv", "kände", "känna"),
    ("sv", "bott", "bo"),
    ("sv", "skrivit", "skriva"),
    ("sv", "finns", "finnas"),
    # Lithuanian: declension classes, palatalization, verbs, reflexives, prefixes.
    ("lt", "namuose", "namas"),
    ("lt", "knygos", "knyga"),
    ("lt", "upėje", "upė"),
    ("lt", "brolio", "brolis"),
    ("lt", "žodžio", "žodis"),
    ("lt", "kačių", "katė"),
    ("lt", "naktį", "naktis"),
    ("lt", "sūnaus", "sūnus"),
    ("lt", "akmens", "akmuo"),
    ("lt", "geresnis", "geras"),
    ("lt", "gerai", "geras"),
    ("lt", "gražiai", "gražus"),
    ("lt", "dirba", "dirbti"),
    ("lt", "nedirba", "dirbti"),
    ("lt", "rašo", "rašyti"),
    ("lt", "rašys", "rašyti"),
    ("lt", "kalbėjo", "kalbėti"),
    ("lt", "myli", "mylėti"),
    ("lt", "dainuoja", "dainuoti"),
    ("lt", "mokausi", "mokytis"),
    ("lt", "juokiasi", "juoktis"),
    ("lt", "jautėsi", "jaustis"),
    ("lt", "pamatė", "pamatyti"),
    ("lt", "nupirko", "pirkti"),
    ("lt", "nupirko", "nupirkti"),
    ("lt", "nusipirko", "nusipirkti"),
    ("lt", "susižeidė", "susižeisti"),
    # Chinese: attached particles, 的-adjectives, compounds, reduplication.
    ("zh", "吃了", "吃"),
    ("zh", "朋友们", "朋友"),
    ("zh", "正确", "正确的"),
    ("zh", "好朋友", "朋友"),
    ("zh", "看看", "看"),
    ("zh", "不好", "好"),
    ("zh-tw", "朋友們", "朋友"),
    # Multi-word lemmas match word by word.
    ("es", "tomé una decisión", "tomar una decisión"),
]

# (language, surface, lemma) pairs that must not match.
NON_MATCHES: List[Tuple[str, str, str]] = [
    ("es", "perro", "gato"),
    ("fr", "chat", "chien"),
    ("lt", "namas", "knyga"),
    ("de", "Hund", "Katze"),
    ("es", "tomé", "tomar una decisión"),
]

# (language, token, expected parts).
CONTRACTIONS: List[Tuple[str, str, List[str]]] = [
    ("fr", "l'homme", ["le", "homme"]),
    ("fr", "l’eau", ["le", "eau"]),
    ("fr", "l'", ["le"]),
    ("fr", "du", ["de", "le"]),
    ("fr", "a-t-il", ["a", "il"]),
    ("fr", "peut-être", ["peut-être"]),
    ("it", "dell'anno", ["di", "lo", "anno"]),
    ("it", "nella", ["in", "la"]),
    ("pt", "pelo", ["por", "o"]),
    ("pt", "chama-se", ["chama", "se"]),
    ("pt", "guarda-chuva", ["guarda-chuva"]),
    ("de", "zum", ["zu", "dem"]),
    ("es", "del", ["de", "el"]),
    ("nl", "z'n", ["zijn"]),
    ("en", "don't", ["don't"]),
]


class TestSurfaceMatchesLemma(unittest.TestCase):
    def test_matches(self) -> None:
        for language, surface, lemma in MATCHES:
            with self.subTest(language=language, surface=surface, lemma=lemma):
                self.assertTrue(
                    surface_matches_lemma(language, surface, lemma),
                    f"keys: {lemma_lookup_keys(language, surface)}",
                )

    def test_non_matches(self) -> None:
        for language, surface, lemma in NON_MATCHES:
            with self.subTest(language=language, surface=surface, lemma=lemma):
                self.assertFalse(surface_matches_lemma(language, surface, lemma))


class TestSplitContractions(unittest.TestCase):
    def test_contractions(self) -> None:
        for language, token, expected in CONTRACTIONS:
            with self.subTest(language=language, token=token):
                self.assertEqual(split_contractions(language, token), expected)


class TestLemmaLookupKeys(unittest.TestCase):
    def test_token_comes_first_and_normalized(self) -> None:
        keys = lemma_lookup_keys("es", "¡Canciones!")
        self.assertEqual(keys[0], "canciones")
        self.assertIn("canción", keys)

    def test_contraction_parts_are_keys(self) -> None:
        self.assertIn("homme", lemma_lookup_keys("fr", "l'homme"))

    def test_language_without_rules_is_exact_only(self) -> None:
        self.assertEqual(lemma_lookup_keys("en", "Tomatoes,"), ["tomatoes"])

    def test_empty_token(self) -> None:
        self.assertEqual(lemma_lookup_keys("es", "..."), [])


if __name__ == "__main__":
    unittest.main()
