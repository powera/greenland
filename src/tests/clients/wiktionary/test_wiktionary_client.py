#!/usr/bin/env python3
"""Tests for the Wiktionary client module and language-specific parsers."""

import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from clients.wiktionary.client import WiktionaryClient
from clients.wiktionary.types import NounNumberType
from clients.wiktionary.utils import (
    clean_form_generic,
    extract_alternative_forms,
    extract_primary_form,
    is_placeholder_text,
    normalize_text,
)

# Lithuanian imports
from langtools.lt.types import NounDeclension as LithuanianNounDeclension
from langtools.lt.utils import clean_form as lt_clean_form
from langtools.lt.utils import normalize_lithuanian_text, remove_stress_marks
from langtools.lt.wiktionary import LithuanianParser

# German imports
from langtools.de.types import GermanGender
from langtools.de.types import NounDeclension as GermanNounDeclension
from langtools.de.utils import clean_form as de_clean_form
from langtools.de.utils import detect_gender_from_article, extract_article
from langtools.de.wiktionary import GermanParser


class TestRemoveStressMarks(unittest.TestCase):
    """Tests for the remove_stress_marks function (Lithuanian)."""

    def test_remove_acute_accent(self) -> None:
        """Test removal of acute accent stress mark."""
        result = remove_stress_marks("šuńs")
        self.assertEqual(result, "šuns")

    def test_remove_grave_accent(self) -> None:
        """Test removal of grave accent stress mark."""
        result = remove_stress_marks("šùnį")
        self.assertEqual(result, "šunį")

    def test_remove_tilde(self) -> None:
        """Test removal of tilde stress mark."""
        result = remove_stress_marks("šuõ")
        self.assertEqual(result, "šuo")

    def test_preserve_lithuanian_u_macron(self) -> None:
        """Test that Lithuanian u with macron is preserved."""
        result = remove_stress_marks("svogūnas")
        self.assertEqual(result, "svogūnas")

    def test_preserve_lithuanian_a_ogonek(self) -> None:
        """Test that Lithuanian a with ogonek is preserved."""
        result = remove_stress_marks("ąčiū")
        self.assertEqual(result, "ąčiū")

    def test_preserve_lithuanian_e_dot(self) -> None:
        """Test that Lithuanian e with dot above is preserved."""
        result = remove_stress_marks("ė")
        self.assertEqual(result, "ė")

    def test_preserve_lithuanian_e_ogonek(self) -> None:
        """Test that Lithuanian e with ogonek is preserved."""
        result = remove_stress_marks("ę")
        self.assertEqual(result, "ę")

    def test_preserve_lithuanian_i_ogonek(self) -> None:
        """Test that Lithuanian i with ogonek is preserved."""
        result = remove_stress_marks("į")
        self.assertEqual(result, "į")

    def test_preserve_lithuanian_u_ogonek(self) -> None:
        """Test that Lithuanian u with ogonek is preserved."""
        result = remove_stress_marks("ų")
        self.assertEqual(result, "ų")

    def test_preserve_caron_letters(self) -> None:
        """Test that letters with caron (š, č, ž) are preserved."""
        result = remove_stress_marks("šūdas")
        self.assertEqual(result, "šūdas")
        result = remove_stress_marks("čia")
        self.assertEqual(result, "čia")
        result = remove_stress_marks("žmogus")
        self.assertEqual(result, "žmogus")

    def test_stress_on_lithuanian_letter(self) -> None:
        """Test removal of stress mark on top of Lithuanian letter."""
        result = remove_stress_marks("ų̃")
        self.assertEqual(result, "ų")

    def test_stress_on_u_macron(self) -> None:
        """Test removal of acute from u with macron."""
        result = remove_stress_marks("ū́")
        self.assertEqual(result, "ū")

    def test_stress_on_e_dot(self) -> None:
        """Test removal of tilde from e with dot."""
        result = remove_stress_marks("ė̃")
        self.assertEqual(result, "ė")

    def test_complex_word(self) -> None:
        """Test a complex word with multiple stress marks."""
        result = remove_stress_marks("ženklų̃")
        self.assertEqual(result, "ženklų")

    def test_empty_string(self) -> None:
        """Test with empty string."""
        result = remove_stress_marks("")
        self.assertEqual(result, "")

    def test_no_stress_marks(self) -> None:
        """Test word with no stress marks."""
        result = remove_stress_marks("vilkas")
        self.assertEqual(result, "vilkas")


class TestLithuanianCleanForm(unittest.TestCase):
    """Tests for the Lithuanian clean_form function."""

    def test_single_form_with_stress(self) -> None:
        """Test cleaning a single form with stress marks."""
        result = lt_clean_form("šuõ")
        self.assertEqual(result, ["šuo"])

    def test_alternative_forms(self) -> None:
        """Test cleaning forms with alternatives."""
        result = lt_clean_form("šuniù/šunimì")
        self.assertEqual(result, ["šuniu", "šunimi"])

    def test_lithuanian_letter_preserved(self) -> None:
        """Test that Lithuanian letters are preserved."""
        result = lt_clean_form("svogūnas")
        self.assertEqual(result, ["svogūnas"])

    def test_em_dash_returns_empty(self) -> None:
        """Test that em dash returns empty list."""
        result = lt_clean_form("—")
        self.assertEqual(result, [])

    def test_hyphen_returns_empty(self) -> None:
        """Test that hyphen returns empty list."""
        result = lt_clean_form("-")
        self.assertEqual(result, [])

    def test_empty_string_returns_empty(self) -> None:
        """Test that empty string returns empty list."""
        result = lt_clean_form("")
        self.assertEqual(result, [])

    def test_whitespace_stripped(self) -> None:
        """Test that whitespace is stripped."""
        result = lt_clean_form("  vilkas  ")
        self.assertEqual(result, ["vilkas"])

    def test_multiple_alternatives(self) -> None:
        """Test multiple alternative forms."""
        result = lt_clean_form("form1/form2/form3")
        self.assertEqual(result, ["form1", "form2", "form3"])


class TestExtractForms(unittest.TestCase):
    """Tests for extract_primary_form and extract_alternative_forms."""

    def test_extract_primary_single_form(self) -> None:
        """Test extracting primary form from single form list."""
        result = extract_primary_form(["vilkas"])
        self.assertEqual(result, "vilkas")

    def test_extract_primary_multiple_forms(self) -> None:
        """Test extracting primary form from multiple forms."""
        result = extract_primary_form(["vilkas", "vilkų"])
        self.assertEqual(result, "vilkas")

    def test_extract_primary_empty(self) -> None:
        """Test extracting primary form from empty list."""
        result = extract_primary_form([])
        self.assertEqual(result, "")

    def test_extract_alternatives_single(self) -> None:
        """Test extracting alternatives from single form."""
        result = extract_alternative_forms(["vilkas"])
        self.assertEqual(result, [])

    def test_extract_alternatives_multiple(self) -> None:
        """Test extracting alternatives from multiple forms."""
        result = extract_alternative_forms(["vilkas", "vilkų", "vilkai"])
        self.assertEqual(result, ["vilkų", "vilkai"])

    def test_extract_alternatives_empty(self) -> None:
        """Test extracting alternatives from empty list."""
        result = extract_alternative_forms([])
        self.assertEqual(result, [])


class TestIsPlaceholderText(unittest.TestCase):
    """Tests for is_placeholder_text function."""

    def test_empty_is_placeholder(self) -> None:
        """Test that empty string is a placeholder."""
        self.assertTrue(is_placeholder_text(""))

    def test_hyphen_is_placeholder(self) -> None:
        """Test that hyphen is a placeholder."""
        self.assertTrue(is_placeholder_text("-"))

    def test_em_dash_is_placeholder(self) -> None:
        """Test that em dash is a placeholder."""
        self.assertTrue(is_placeholder_text("\u2014"))

    def test_en_dash_is_placeholder(self) -> None:
        """Test that en dash is a placeholder."""
        self.assertTrue(is_placeholder_text("\u2013"))

    def test_na_is_placeholder(self) -> None:
        """Test that N/A is a placeholder."""
        self.assertTrue(is_placeholder_text("N/A"))
        self.assertTrue(is_placeholder_text("n/a"))

    def test_none_is_placeholder(self) -> None:
        """Test that 'none' is a placeholder."""
        self.assertTrue(is_placeholder_text("none"))
        self.assertTrue(is_placeholder_text("None"))

    def test_word_is_not_placeholder(self) -> None:
        """Test that actual words are not placeholders."""
        self.assertFalse(is_placeholder_text("vilkas"))
        self.assertFalse(is_placeholder_text("Hund"))


class TestNormalizeLithuanianText(unittest.TestCase):
    """Tests for normalize_lithuanian_text function."""

    def test_nfc_normalization(self) -> None:
        """Test that text is normalized to NFC."""
        nfd_text = "a\u0328"
        result = normalize_lithuanian_text(nfd_text)
        self.assertEqual(result, "ą")

    def test_already_nfc(self) -> None:
        """Test that already NFC text is unchanged."""
        result = normalize_lithuanian_text("ąčėęįšūųž")
        self.assertEqual(result, "ąčėęįšūųž")


class TestWiktionaryClient(unittest.TestCase):
    """Tests for WiktionaryClient class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.client = WiktionaryClient(debug=False)

    @patch("clients.wiktionary.client.requests.get")
    def test_fetch_page_wikitext_success(self, mock_get: MagicMock) -> None:
        """Test successful page wikitext fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "query": {
                "pages": {
                    "12345": {
                        "revisions": [{"slots": {"main": {"*": "==Lithuanian==\nSome content"}}}]
                    }
                }
            }
        }
        mock_get.return_value = mock_response

        result = self.client.fetch_page_wikitext("vilkas")

        self.assertEqual(result, "==Lithuanian==\nSome content")
        mock_get.assert_called_once()

    @patch("clients.wiktionary.client.requests.get")
    def test_fetch_page_wikitext_not_found(self, mock_get: MagicMock) -> None:
        """Test page not found returns None."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"query": {"pages": {"-1": {"missing": True}}}}
        mock_get.return_value = mock_response

        result = self.client.fetch_page_wikitext("nonexistentword12345")

        self.assertIsNone(result)

    def test_extract_language_section_found(self) -> None:
        """Test extracting language section when present."""
        wikitext = """
==English==
English content

==Lithuanian==
Lithuanian content

==German==
German content
"""
        result = self.client.extract_language_section(wikitext, "Lithuanian")

        self.assertIsNotNone(result)
        self.assertIn("Lithuanian content", result)
        self.assertNotIn("German content", result)
        self.assertNotIn("English content", result)

    def test_extract_language_section_not_found(self) -> None:
        """Test extracting language section when not present."""
        wikitext = """
==English==
English content
"""
        result = self.client.extract_language_section(wikitext, "Lithuanian")

        self.assertIsNone(result)

    def test_extract_language_section_at_end(self) -> None:
        """Test extracting language section at end of document."""
        wikitext = """
==English==
English content

==Lithuanian==
Lithuanian content to the end
"""
        result = self.client.extract_language_section(wikitext, "Lithuanian")

        self.assertIsNotNone(result)
        self.assertIn("Lithuanian content to the end", result)

    def test_find_templates(self) -> None:
        """Test finding templates in wikitext."""
        wikitext = """
===Declension===
{{lt-noun-m-as-2|vilk}}

Some other text

{{lt-noun-f-a|kat}}
"""
        patterns = [r"lt-noun-[mf]-[a-zA-Z]+-?\d*"]
        results = self.client.find_templates(wikitext, patterns)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0][0], "lt-noun-m-as-2")
        self.assertEqual(results[1][0], "lt-noun-f-a")

    @patch("clients.wiktionary.client.requests.get")
    def test_parse_to_html_success(self, mock_get: MagicMock) -> None:
        """Test successful wikitext to HTML parsing."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "parse": {"text": {"*": "<table class='inflection-table'></table>"}}
        }
        mock_get.return_value = mock_response

        result = self.client.parse_to_html("{{lt-noun-m-as-2|vilk}}")

        self.assertIsNotNone(result)
        self.assertIn("inflection-table", result)


class TestLithuanianParser(unittest.TestCase):
    """Tests for LithuanianParser class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_client = Mock(spec=WiktionaryClient)
        self.parser = LithuanianParser(client=self.mock_client, debug=False)

    def test_get_noun_declensions_no_page(self) -> None:
        """Test noun declension when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_noun_declensions("nonexistent")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_noun_declensions_no_lithuanian_section(self) -> None:
        """Test noun declension when no Lithuanian section."""
        self.mock_client.fetch_page_wikitext.return_value = "==English==\nContent"
        self.mock_client.extract_language_section.return_value = None

        result, success = self.parser.get_noun_declensions("word")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_noun_declensions_no_template(self) -> None:
        """Test noun declension when no template found."""
        self.mock_client.fetch_page_wikitext.return_value = "==Lithuanian==\nContent"
        self.mock_client.extract_language_section.return_value = "===Noun===\nA word"
        self.mock_client.find_templates.return_value = []

        result, success = self.parser.get_noun_declensions("word")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_parse_noun_table_regular(self) -> None:
        """Test parsing a regular noun declension table."""
        html = """
        <table class="inflection-table">
            <tr><th></th><th>Singular</th><th>Plural</th></tr>
            <tr><td>nominative</td><td>vilkas</td><td>vilkai</td></tr>
            <tr><td>genitive</td><td>vilko</td><td>vilkų</td></tr>
            <tr><td>dative</td><td>vilkui</td><td>vilkams</td></tr>
            <tr><td>accusative</td><td>vilką</td><td>vilkus</td></tr>
            <tr><td>instrumental</td><td>vilku</td><td>vilkais</td></tr>
            <tr><td>locative</td><td>vilke</td><td>vilkuose</td></tr>
            <tr><td>vocative</td><td>vilke</td><td>vilkai</td></tr>
        </table>
        """
        forms, alternatives, number_type = self.parser._parse_noun_table(html)

        self.assertEqual(number_type, NounNumberType.REGULAR)
        self.assertEqual(forms["nominative_singular"], "vilkas")
        self.assertEqual(forms["nominative_plural"], "vilkai")
        self.assertEqual(forms["genitive_singular"], "vilko")
        self.assertEqual(forms["genitive_plural"], "vilkų")
        self.assertEqual(len(forms), 14)

    def test_parse_noun_table_plurale_tantum(self) -> None:
        """Test parsing a plurale tantum noun table."""
        html = """
        <table class="inflection-table">
            <tr><th></th><th>Plural</th></tr>
            <tr><td>nominative</td><td>durys</td></tr>
            <tr><td>genitive</td><td>durų</td></tr>
        </table>
        """
        forms, alternatives, number_type = self.parser._parse_noun_table(html)

        self.assertIn("nominative_plural", forms)
        self.assertEqual(forms["nominative_plural"], "durys")

    def test_get_verb_conjugations_no_page(self) -> None:
        """Test verb conjugation when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_verb_conjugations("nonexistent")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_adjective_declensions_no_page(self) -> None:
        """Test adjective declension when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_adjective_declensions("nonexistent")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_adverb_forms_fallback(self) -> None:
        """Test adverb forms fallback to word as positive form."""
        self.mock_client.fetch_page_wikitext.return_value = "==Lithuanian==\n===Adverb==="
        self.mock_client.extract_language_section.return_value = "===Adverb===\nAn adverb"
        self.mock_client.find_templates.return_value = []

        result, success = self.parser.get_adverb_forms("greitai")

        self.assertTrue(success)
        self.assertEqual(result.forms["positive"], "greitai")


class TestLithuanianNounDeclensionType(unittest.TestCase):
    """Tests for Lithuanian NounDeclension type."""

    def test_has_singular_true(self) -> None:
        """Test has_singular returns True when singular forms exist."""
        decl = LithuanianNounDeclension(
            word="vilkas",
            number_type=NounNumberType.REGULAR,
            forms={"nominative_singular": "vilkas", "genitive_singular": "vilko"},
        )
        self.assertTrue(decl.has_singular())

    def test_has_singular_false(self) -> None:
        """Test has_singular returns False when no singular forms."""
        decl = LithuanianNounDeclension(
            word="durys",
            number_type=NounNumberType.PLURALE_TANTUM,
            forms={"nominative_plural": "durys", "genitive_plural": "durų"},
        )
        self.assertFalse(decl.has_singular())

    def test_has_plural_true(self) -> None:
        """Test has_plural returns True when plural forms exist."""
        decl = LithuanianNounDeclension(
            word="vilkas",
            number_type=NounNumberType.REGULAR,
            forms={"nominative_plural": "vilkai", "genitive_plural": "vilkų"},
        )
        self.assertTrue(decl.has_plural())

    def test_has_plural_false(self) -> None:
        """Test has_plural returns False when no plural forms."""
        decl = LithuanianNounDeclension(
            word="pienas",
            number_type=NounNumberType.SINGULARE_TANTUM,
            forms={"nominative_singular": "pienas", "genitive_singular": "pieno"},
        )
        self.assertFalse(decl.has_plural())


# German parser tests


class TestGermanUtils(unittest.TestCase):
    """Tests for German utility functions."""

    def test_extract_article_der(self) -> None:
        """Test extracting 'der' article."""
        article, noun = extract_article("der Hund")
        self.assertEqual(article, "der")
        self.assertEqual(noun, "Hund")

    def test_extract_article_die(self) -> None:
        """Test extracting 'die' article."""
        article, noun = extract_article("die Katze")
        self.assertEqual(article, "die")
        self.assertEqual(noun, "Katze")

    def test_extract_article_das(self) -> None:
        """Test extracting 'das' article."""
        article, noun = extract_article("das Kind")
        self.assertEqual(article, "das")
        self.assertEqual(noun, "Kind")

    def test_extract_no_article(self) -> None:
        """Test when no article present."""
        article, noun = extract_article("Hund")
        self.assertEqual(article, "")
        self.assertEqual(noun, "Hund")

    def test_detect_gender_masculine(self) -> None:
        """Test detecting masculine gender."""
        self.assertEqual(detect_gender_from_article("der"), "m")

    def test_detect_gender_feminine(self) -> None:
        """Test detecting feminine gender."""
        self.assertEqual(detect_gender_from_article("die"), "f")

    def test_detect_gender_neuter(self) -> None:
        """Test detecting neuter gender."""
        self.assertEqual(detect_gender_from_article("das"), "n")

    def test_german_clean_form(self) -> None:
        """Test German form cleaning."""
        result = de_clean_form("Hunde")
        self.assertEqual(result, ["Hunde"])

    def test_german_clean_form_with_umlaut(self) -> None:
        """Test German form cleaning preserves umlauts."""
        result = de_clean_form("Häuser")
        self.assertEqual(result, ["Häuser"])

    def test_german_clean_form_alternatives(self) -> None:
        """Test German form cleaning with alternatives."""
        result = de_clean_form("Form1/Form2")
        self.assertEqual(result, ["Form1", "Form2"])


class TestGermanParser(unittest.TestCase):
    """Tests for GermanParser class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_client = Mock(spec=WiktionaryClient)
        self.parser = GermanParser(client=self.mock_client, debug=False)

    def test_get_noun_declensions_no_page(self) -> None:
        """Test noun declension when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_noun_declensions("nonexistent")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_noun_declensions_no_german_section(self) -> None:
        """Test noun declension when no German section."""
        self.mock_client.fetch_page_wikitext.return_value = "==English==\nContent"
        self.mock_client.extract_language_section.return_value = None

        result, success = self.parser.get_noun_declensions("Hund")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_verb_conjugations_no_page(self) -> None:
        """Test verb conjugation when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_verb_conjugations("nonexistent")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_adjective_declensions_no_page(self) -> None:
        """Test adjective declension when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_adjective_declensions("nonexistent")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_adverb_forms_success(self) -> None:
        """Test adverb forms always returns at least positive form."""
        self.mock_client.fetch_page_wikitext.return_value = "==German==\n===Adverb==="
        self.mock_client.extract_language_section.return_value = "===Adverb===\nAn adverb"
        self.mock_client.find_templates.return_value = []

        result, success = self.parser.get_adverb_forms("schnell")

        self.assertTrue(success)
        self.assertEqual(result.forms["positive"], "schnell")

    def test_extract_gender_masculine(self) -> None:
        """Test gender extraction for masculine."""
        wikitext = "{{de-noun|m}}"
        gender = self.parser._extract_gender(wikitext)
        self.assertEqual(gender, GermanGender.MASCULINE)

    def test_extract_gender_feminine(self) -> None:
        """Test gender extraction for feminine."""
        wikitext = "{{de-noun|f}}"
        gender = self.parser._extract_gender(wikitext)
        self.assertEqual(gender, GermanGender.FEMININE)

    def test_extract_gender_neuter(self) -> None:
        """Test gender extraction for neuter."""
        wikitext = "{{de-noun|n}}"
        gender = self.parser._extract_gender(wikitext)
        self.assertEqual(gender, GermanGender.NEUTER)

    def test_parse_noun_table(self) -> None:
        """Test parsing a German noun declension table."""
        html = """
        <table class="inflection-table">
            <tr><th></th><th>Singular</th><th>Plural</th></tr>
            <tr><td>Nominative</td><td>der Hund</td><td>die Hunde</td></tr>
            <tr><td>Genitive</td><td>des Hundes</td><td>der Hunde</td></tr>
            <tr><td>Dative</td><td>dem Hund</td><td>den Hunden</td></tr>
            <tr><td>Accusative</td><td>den Hund</td><td>die Hunde</td></tr>
        </table>
        """
        forms, alternatives, number_type = self.parser._parse_noun_table(html)

        self.assertEqual(number_type, NounNumberType.REGULAR)
        # Forms should have article stripped
        self.assertIn("nominative_singular", forms)
        self.assertIn("nominative_plural", forms)


class TestGermanNounDeclensionType(unittest.TestCase):
    """Tests for German NounDeclension type."""

    def test_has_singular_true(self) -> None:
        """Test has_singular returns True when singular forms exist."""
        decl = GermanNounDeclension(
            word="Hund",
            gender=GermanGender.MASCULINE,
            forms={"nominative_singular": "Hund", "genitive_singular": "Hundes"},
        )
        self.assertTrue(decl.has_singular())

    def test_has_singular_false(self) -> None:
        """Test has_singular returns False when no singular forms."""
        decl = GermanNounDeclension(
            word="Leute",
            number_type=NounNumberType.PLURALE_TANTUM,
            forms={"nominative_plural": "Leute", "genitive_plural": "Leute"},
        )
        self.assertFalse(decl.has_singular())

    def test_has_plural_true(self) -> None:
        """Test has_plural returns True when plural forms exist."""
        decl = GermanNounDeclension(
            word="Hund",
            forms={"nominative_plural": "Hunde", "genitive_plural": "Hunde"},
        )
        self.assertTrue(decl.has_plural())


# French parser tests

# Import French modules
from langtools.fr.types import FrenchGender
from langtools.fr.types import NounDeclension as FrenchNounDeclension
from langtools.fr.utils import clean_form as fr_clean_form
from langtools.fr.utils import detect_gender_from_article as fr_detect_gender
from langtools.fr.utils import extract_article as fr_extract_article
from langtools.fr.utils import is_elided_form
from langtools.fr.wiktionary import FrenchParser


class TestFrenchUtils(unittest.TestCase):
    """Tests for French utility functions."""

    def test_extract_article_le(self) -> None:
        """Test extracting 'le' article."""
        article, noun = fr_extract_article("le chien")
        self.assertEqual(article, "le")
        self.assertEqual(noun, "chien")

    def test_extract_article_la(self) -> None:
        """Test extracting 'la' article."""
        article, noun = fr_extract_article("la maison")
        self.assertEqual(article, "la")
        self.assertEqual(noun, "maison")

    def test_extract_article_elided(self) -> None:
        """Test extracting elided article l'."""
        article, noun = fr_extract_article("l'homme")
        self.assertEqual(article, "l'")
        self.assertEqual(noun, "homme")

    def test_extract_no_article(self) -> None:
        """Test when no article present."""
        article, noun = fr_extract_article("chien")
        self.assertEqual(article, "")
        self.assertEqual(noun, "chien")

    def test_detect_gender_masculine(self) -> None:
        """Test detecting masculine gender."""
        self.assertEqual(fr_detect_gender("le"), "m")
        self.assertEqual(fr_detect_gender("un"), "m")

    def test_detect_gender_feminine(self) -> None:
        """Test detecting feminine gender."""
        self.assertEqual(fr_detect_gender("la"), "f")
        self.assertEqual(fr_detect_gender("une"), "f")

    def test_detect_gender_ambiguous(self) -> None:
        """Test ambiguous articles."""
        self.assertEqual(fr_detect_gender("l'"), "")
        self.assertEqual(fr_detect_gender("les"), "")

    def test_french_clean_form(self) -> None:
        """Test French form cleaning."""
        result = fr_clean_form("chiens")
        self.assertEqual(result, ["chiens"])

    def test_french_clean_form_with_accents(self) -> None:
        """Test French form cleaning preserves accents."""
        result = fr_clean_form("élève")
        self.assertEqual(result, ["élève"])

    def test_french_clean_form_alternatives(self) -> None:
        """Test French form cleaning with alternatives."""
        result = fr_clean_form("form1/form2")
        self.assertEqual(result, ["form1", "form2"])

    def test_is_elided_form_vowel(self) -> None:
        """Test elision detection for vowels."""
        self.assertTrue(is_elided_form("ami"))
        self.assertTrue(is_elided_form("école"))

    def test_is_elided_form_consonant(self) -> None:
        """Test elision detection for consonants."""
        self.assertFalse(is_elided_form("chien"))
        self.assertFalse(is_elided_form("maison"))


class TestFrenchParser(unittest.TestCase):
    """Tests for FrenchParser class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_client = Mock(spec=WiktionaryClient)
        self.parser = FrenchParser(client=self.mock_client, debug=False)

    def test_get_noun_declensions_no_page(self) -> None:
        """Test noun forms when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_noun_declensions("nonexistent")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_noun_declensions_no_french_section(self) -> None:
        """Test noun forms when no French section."""
        self.mock_client.fetch_page_wikitext.return_value = "==English==\nContent"
        self.mock_client.extract_language_section.return_value = None

        result, success = self.parser.get_noun_declensions("chien")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_verb_conjugations_no_page(self) -> None:
        """Test verb conjugation when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_verb_conjugations("nonexistent")

        self.assertFalse(success)
        self.assertEqual(result.forms, {})

    def test_get_adjective_declensions_no_page(self) -> None:
        """Test adjective forms when page not found."""
        self.mock_client.fetch_page_wikitext.return_value = None

        result, success = self.parser.get_adjective_declensions("nonexistent")

        self.assertFalse(success)

    def test_get_adverb_forms_success(self) -> None:
        """Test adverb forms always returns at least positive form."""
        self.mock_client.fetch_page_wikitext.return_value = "==French==\n===Adverb==="
        self.mock_client.extract_language_section.return_value = "===Adverb===\nAn adverb"
        self.mock_client.find_templates.return_value = []

        result, success = self.parser.get_adverb_forms("rapidement")

        self.assertTrue(success)
        self.assertEqual(result.forms["positive"], "rapidement")

    def test_extract_gender_masculine(self) -> None:
        """Test gender extraction for masculine."""
        wikitext = "{{fr-noun|m}}"
        gender = self.parser._extract_gender(wikitext)
        self.assertEqual(gender, FrenchGender.MASCULINE)

    def test_extract_gender_feminine(self) -> None:
        """Test gender extraction for feminine."""
        wikitext = "{{fr-noun|f}}"
        gender = self.parser._extract_gender(wikitext)
        self.assertEqual(gender, FrenchGender.FEMININE)

    def test_generate_regular_plural(self) -> None:
        """Test regular plural generation."""
        self.assertEqual(self.parser._generate_regular_plural("chien"), "chiens")
        self.assertEqual(self.parser._generate_regular_plural("chat"), "chats")

    def test_generate_plural_ending_s(self) -> None:
        """Test plural for words ending in -s."""
        self.assertEqual(self.parser._generate_regular_plural("souris"), "souris")

    def test_generate_plural_ending_eau(self) -> None:
        """Test plural for words ending in -eau."""
        self.assertEqual(self.parser._generate_regular_plural("bateau"), "bateaux")

    def test_generate_plural_ending_al(self) -> None:
        """Test plural for words ending in -al."""
        self.assertEqual(self.parser._generate_regular_plural("journal"), "journaux")

    def test_generate_feminine_regular(self) -> None:
        """Test regular feminine generation."""
        self.assertEqual(self.parser._generate_feminine("petit"), "petite")
        self.assertEqual(self.parser._generate_feminine("grand"), "grande")

    def test_generate_feminine_already_e(self) -> None:
        """Test feminine for adjectives already ending in -e."""
        self.assertEqual(self.parser._generate_feminine("rouge"), "rouge")

    def test_generate_feminine_eux(self) -> None:
        """Test feminine for -eux adjectives."""
        self.assertEqual(self.parser._generate_feminine("heureux"), "heureuse")


class TestFrenchNounDeclensionType(unittest.TestCase):
    """Tests for French NounDeclension type."""

    def test_has_singular_true(self) -> None:
        """Test has_singular returns True when singular forms exist."""
        decl = FrenchNounDeclension(
            word="chien",
            gender=FrenchGender.MASCULINE,
            forms={"singular": "chien"},
        )
        self.assertTrue(decl.has_singular())

    def test_has_plural_true(self) -> None:
        """Test has_plural returns True when plural forms exist."""
        decl = FrenchNounDeclension(
            word="chien",
            forms={"singular": "chien", "plural": "chiens"},
        )
        self.assertTrue(decl.has_plural())

    def test_has_plural_false(self) -> None:
        """Test has_plural returns False when no plural forms."""
        decl = FrenchNounDeclension(
            word="eau",
            number_type=NounNumberType.SINGULARE_TANTUM,
            forms={"singular": "eau"},
        )
        self.assertFalse(decl.has_plural())


if __name__ == "__main__":
    unittest.main()
