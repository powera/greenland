#!/usr/bin/env python3
"""Tests for the Wiktionary client module."""

import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from clients.wiktionary.client import WiktionaryClient
from clients.wiktionary.lithuanian import LithuanianParser
from clients.wiktionary.types import NounNumberType
from clients.wiktionary.utils import (
    clean_form,
    extract_alternative_forms,
    extract_primary_form,
    is_placeholder_text,
    normalize_lithuanian_text,
    remove_stress_marks,
)


class TestRemoveStressMarks(unittest.TestCase):
    """Tests for the remove_stress_marks function."""

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
        # u with ogonek + tilde should become just u with ogonek
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


class TestCleanForm(unittest.TestCase):
    """Tests for the clean_form function."""

    def test_single_form_with_stress(self) -> None:
        """Test cleaning a single form with stress marks."""
        result = clean_form("šuõ")
        self.assertEqual(result, ["šuo"])

    def test_alternative_forms(self) -> None:
        """Test cleaning forms with alternatives."""
        result = clean_form("šuniù/šunimì")
        self.assertEqual(result, ["šuniu", "šunimi"])

    def test_lithuanian_letter_preserved(self) -> None:
        """Test that Lithuanian letters are preserved."""
        result = clean_form("svogūnas")
        self.assertEqual(result, ["svogūnas"])

    def test_em_dash_returns_empty(self) -> None:
        """Test that em dash returns empty list."""
        result = clean_form("—")
        self.assertEqual(result, [])

    def test_hyphen_returns_empty(self) -> None:
        """Test that hyphen returns empty list."""
        result = clean_form("-")
        self.assertEqual(result, [])

    def test_empty_string_returns_empty(self) -> None:
        """Test that empty string returns empty list."""
        result = clean_form("")
        self.assertEqual(result, [])

    def test_none_returns_empty(self) -> None:
        """Test that None-like values return empty list."""
        result = clean_form("")
        self.assertEqual(result, [])

    def test_whitespace_stripped(self) -> None:
        """Test that whitespace is stripped."""
        result = clean_form("  vilkas  ")
        self.assertEqual(result, ["vilkas"])

    def test_multiple_alternatives(self) -> None:
        """Test multiple alternative forms."""
        result = clean_form("form1/form2/form3")
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
        self.assertFalse(is_placeholder_text("šuo"))


class TestNormalizeLithuanianText(unittest.TestCase):
    """Tests for normalize_lithuanian_text function."""

    def test_nfc_normalization(self) -> None:
        """Test that text is normalized to NFC."""
        # NFD representation of ą (a + combining ogonek)
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
        self.assertEqual(len(forms), 14)  # 7 cases x 2 numbers

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

        # Should detect plurale tantum from header
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


class TestNounDeclensionType(unittest.TestCase):
    """Tests for NounDeclension type."""

    def test_has_singular_true(self) -> None:
        """Test has_singular returns True when singular forms exist."""
        from clients.wiktionary.types import NounDeclension

        decl = NounDeclension(
            word="vilkas",
            number_type=NounNumberType.REGULAR,
            forms={"nominative_singular": "vilkas", "genitive_singular": "vilko"},
        )
        self.assertTrue(decl.has_singular())

    def test_has_singular_false(self) -> None:
        """Test has_singular returns False when no singular forms."""
        from clients.wiktionary.types import NounDeclension

        decl = NounDeclension(
            word="durys",
            number_type=NounNumberType.PLURALE_TANTUM,
            forms={"nominative_plural": "durys", "genitive_plural": "durų"},
        )
        self.assertFalse(decl.has_singular())

    def test_has_plural_true(self) -> None:
        """Test has_plural returns True when plural forms exist."""
        from clients.wiktionary.types import NounDeclension

        decl = NounDeclension(
            word="vilkas",
            number_type=NounNumberType.REGULAR,
            forms={"nominative_plural": "vilkai", "genitive_plural": "vilkų"},
        )
        self.assertTrue(decl.has_plural())

    def test_has_plural_false(self) -> None:
        """Test has_plural returns False when no plural forms."""
        from clients.wiktionary.types import NounDeclension

        decl = NounDeclension(
            word="pienas",
            number_type=NounNumberType.SINGULARE_TANTUM,
            forms={"nominative_singular": "pienas", "genitive_singular": "pieno"},
        )
        self.assertFalse(decl.has_plural())


if __name__ == "__main__":
    unittest.main()
