"""Lithuanian-specific Wiktionary parsing for grammatical forms."""

import logging
import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from clients.wiktionary.client import WiktionaryClient
from clients.wiktionary.types import (
    AdjectiveDeclension,
    AdverbForms,
    NounDeclension,
    NounNumberType,
    VerbConjugation,
)
from clients.wiktionary.utils import clean_form, extract_primary_form

logger = logging.getLogger(__name__)


class LithuanianParser:
    """Parser for Lithuanian grammatical forms from Wiktionary."""

    # Template patterns for different parts of speech
    NOUN_TEMPLATE_PATTERNS = [
        r"lt-noun-[mf]-[a-zA-Z]+-?\d*",  # e.g., lt-noun-m-as-2, lt-noun-f-a
        r"lt-decl-noun[^}]*",  # Generic declension template
        r"lt-ndecl[^}]*",  # Alternative declension template
    ]

    VERB_TEMPLATE_PATTERNS = [
        r"lt-conj[^}]*",  # Conjugation templates
        r"lt-verb[^}]*",  # Verb templates
    ]

    ADJECTIVE_TEMPLATE_PATTERNS = [
        r"lt-adj[^}]*",  # Adjective templates
        r"lt-decl-adj[^}]*",  # Adjective declension templates
    ]

    ADVERB_TEMPLATE_PATTERNS = [
        r"lt-adv[^}]*",  # Adverb templates
    ]

    # Case name mapping from Wiktionary to our internal format
    CASE_NAME_MAP = {
        "nominative": "nominative",
        "genitive": "genitive",
        "dative": "dative",
        "accusative": "accusative",
        "instrumental": "instrumental",
        "locative": "locative",
        "vocative": "vocative",
    }

    # Person/number mapping for verbs
    PERSON_MAP = {
        "1st singular": "1s",
        "2nd singular": "2s",
        "3rd singular": "3s",
        "1st plural": "1p",
        "2nd plural": "2p",
        "3rd plural": "3p",
        "1st sing.": "1s",
        "2nd sing.": "2s",
        "3rd sing.": "3s",
        "1st pl.": "1p",
        "2nd pl.": "2p",
        "3rd pl.": "3p",
        "aš": "1s",  # Lithuanian pronouns
        "tu": "2s",
        "jis/ji": "3s",
        "mes": "1p",
        "jūs": "2p",
        "jie/jos": "3p",
    }

    def __init__(self, client: Optional[WiktionaryClient] = None, debug: bool = False):
        """
        Initialize the Lithuanian parser.

        Args:
            client: WiktionaryClient instance (creates new one if not provided)
            debug: Enable debug logging
        """
        self.client = client or WiktionaryClient(debug=debug)
        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_noun_declensions(self, word: str) -> Tuple[NounDeclension, bool]:
        """
        Get all declension forms for a Lithuanian noun.

        Args:
            word: Lithuanian noun in nominative singular (lemma form)

        Returns:
            Tuple of (NounDeclension, success flag)
        """
        logger.info(f"Fetching noun declensions for '{word}'")

        # Fetch the page wikitext
        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return NounDeclension(word=word, number_type=NounNumberType.REGULAR, forms={}), False

        # Extract Lithuanian section
        lt_section = self.client.extract_language_section(wikitext, "Lithuanian")
        if not lt_section:
            return NounDeclension(word=word, number_type=NounNumberType.REGULAR, forms={}), False

        # Find declension template
        templates = self.client.find_templates(lt_section, self.NOUN_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No noun declension template found for '{word}'")
            return NounDeclension(word=word, number_type=NounNumberType.REGULAR, forms={}), False

        # Use the first matching template
        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        # Parse the template to HTML
        html = self.client.parse_to_html(template_text)
        if not html:
            return (
                NounDeclension(
                    word=word,
                    number_type=NounNumberType.REGULAR,
                    forms={},
                    raw_template=template_text,
                ),
                False,
            )

        # Extract forms from HTML table
        forms, alternatives, number_type = self._parse_noun_table(html)

        result = NounDeclension(
            word=word,
            number_type=number_type,
            forms=forms,
            alternatives=alternatives,
            raw_template=template_text,
        )

        success = len(forms) > 0
        if success:
            logger.info(f"Successfully extracted {len(forms)} declension forms for '{word}'")
        else:
            logger.warning(f"No declension forms extracted for '{word}'")

        return result, success

    def _parse_noun_table(
        self, html: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]], NounNumberType]:
        """
        Parse a noun declension HTML table.

        Args:
            html: HTML containing the declension table

        Returns:
            Tuple of (forms dict, alternatives dict, number type)
        """
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        # Find the inflection table
        table = soup.find("table", class_="inflection-table")
        if not table or not isinstance(table, Tag):
            logger.warning("No inflection table found in HTML")
            return forms, alternatives, NounNumberType.REGULAR

        rows = table.find_all("tr")
        if not rows:
            return forms, alternatives, NounNumberType.REGULAR

        # Detect table structure
        has_singular = False
        has_plural = False
        start_row = 0

        # Check header row
        if rows:
            first_row_cells = rows[0].find_all(["th", "td"])
            first_row_text = " ".join(cell.get_text(strip=True).lower() for cell in first_row_cells)
            if "singular" in first_row_text:
                has_singular = True
                start_row = 1
            if "plural" in first_row_text:
                has_plural = True
                start_row = 1

        # If we couldn't determine from header, assume regular
        if not has_singular and not has_plural:
            # Default to regular (both singular and plural)
            has_singular = True
            has_plural = True

        # Parse each data row
        for row in rows[start_row:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            # First cell is the case name
            case_cell_text = cells[0].get_text(strip=True).lower()

            # Match case name
            matched_case = None
            for known_case, internal_name in self.CASE_NAME_MAP.items():
                if known_case in case_cell_text:
                    matched_case = internal_name
                    break

            if not matched_case:
                continue

            # Handle different table structures
            if len(cells) == 3:
                # Regular table: case | singular | plural
                singular_form = cells[1].get_text(strip=True)
                plural_form = cells[2].get_text(strip=True)

                cleaned_singular = clean_form(singular_form)
                if cleaned_singular:
                    forms[f"{matched_case}_singular"] = extract_primary_form(cleaned_singular)
                    if len(cleaned_singular) > 1:
                        alternatives[f"{matched_case}_singular"] = cleaned_singular[1:]

                cleaned_plural = clean_form(plural_form)
                if cleaned_plural:
                    forms[f"{matched_case}_plural"] = extract_primary_form(cleaned_plural)
                    if len(cleaned_plural) > 1:
                        alternatives[f"{matched_case}_plural"] = cleaned_plural[1:]

            elif len(cells) == 2:
                # Single column table (plurale tantum or singulare tantum)
                form_text = cells[1].get_text(strip=True)
                cleaned = clean_form(form_text)

                if cleaned:
                    # Determine if this is singular or plural based on headers/context
                    if has_plural and not has_singular:
                        # Plurale tantum
                        forms[f"{matched_case}_plural"] = extract_primary_form(cleaned)
                        if len(cleaned) > 1:
                            alternatives[f"{matched_case}_plural"] = cleaned[1:]
                    else:
                        # Singulare tantum or default to singular
                        forms[f"{matched_case}_singular"] = extract_primary_form(cleaned)
                        if len(cleaned) > 1:
                            alternatives[f"{matched_case}_singular"] = cleaned[1:]

        # Determine number type
        has_sg_forms = any(k.endswith("_singular") for k in forms)
        has_pl_forms = any(k.endswith("_plural") for k in forms)

        if has_sg_forms and has_pl_forms:
            number_type = NounNumberType.REGULAR
        elif has_pl_forms:
            number_type = NounNumberType.PLURALE_TANTUM
        else:
            number_type = NounNumberType.SINGULARE_TANTUM

        return forms, alternatives, number_type

    def get_verb_conjugations(self, word: str) -> Tuple[VerbConjugation, bool]:
        """
        Get all conjugation forms for a Lithuanian verb.

        Args:
            word: Lithuanian verb in infinitive form

        Returns:
            Tuple of (VerbConjugation, success flag)
        """
        logger.info(f"Fetching verb conjugations for '{word}'")

        # Fetch the page wikitext
        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return VerbConjugation(word=word, forms={}), False

        # Extract Lithuanian section
        lt_section = self.client.extract_language_section(wikitext, "Lithuanian")
        if not lt_section:
            return VerbConjugation(word=word, forms={}), False

        # Find conjugation template
        templates = self.client.find_templates(lt_section, self.VERB_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No verb conjugation template found for '{word}'")
            return VerbConjugation(word=word, forms={}), False

        # Use the first matching template
        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        # Parse the template to HTML
        html = self.client.parse_to_html(template_text)
        if not html:
            return VerbConjugation(word=word, forms={}, raw_template=template_text), False

        # Extract forms from HTML table
        forms, alternatives = self._parse_verb_table(html)

        result = VerbConjugation(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=template_text,
        )

        success = len(forms) > 0
        if success:
            logger.info(f"Successfully extracted {len(forms)} conjugation forms for '{word}'")
        else:
            logger.warning(f"No conjugation forms extracted for '{word}'")

        return result, success

    def _parse_verb_table(self, html: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """
        Parse a verb conjugation HTML table.

        Lithuanian verb tables typically show:
        - Rows: persons (1st/2nd/3rd singular/plural)
        - Columns: tenses (present, past, future)

        Args:
            html: HTML containing the conjugation table

        Returns:
            Tuple of (forms dict, alternatives dict)
        """
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        # Find conjugation table(s)
        tables = soup.find_all("table", class_="inflection-table")
        if not tables:
            # Try without class
            tables = soup.find_all("table")

        for table in tables:
            if not isinstance(table, Tag):
                continue
            self._parse_single_verb_table(table, forms, alternatives)

        return forms, alternatives

    def _parse_single_verb_table(
        self,
        table: Tag,
        forms: Dict[str, str],
        alternatives: Dict[str, List[str]],
    ) -> None:
        """Parse a single verb table and add forms to the dict."""
        rows = table.find_all("tr")
        if not rows:
            return

        # Try to detect column headers for tenses
        tense_columns: Dict[int, str] = {}
        header_row = rows[0]
        header_cells = header_row.find_all(["th", "td"])

        for i, cell in enumerate(header_cells):
            text = cell.get_text(strip=True).lower()
            if "present" in text or "esamasis" in text:
                tense_columns[i] = "present"
            elif "past" in text or "būtasis" in text:
                tense_columns[i] = "past"
            elif "future" in text or "būsimasis" in text:
                tense_columns[i] = "future"

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            # First cell should be person indicator
            person_cell = cells[0].get_text(strip=True).lower()
            person = None

            for pattern, person_code in self.PERSON_MAP.items():
                if pattern.lower() in person_cell:
                    person = person_code
                    break

            if not person:
                continue

            # Parse form cells
            for i, cell in enumerate(cells[1:], start=1):
                if i not in tense_columns:
                    continue

                tense = tense_columns[i]
                form_text = cell.get_text(strip=True)
                cleaned = clean_form(form_text)

                if cleaned:
                    form_key = f"{person}_{tense}"
                    forms[form_key] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives[form_key] = cleaned[1:]

    def get_adjective_declensions(self, word: str) -> Tuple[AdjectiveDeclension, bool]:
        """
        Get all declension forms for a Lithuanian adjective.

        Args:
            word: Lithuanian adjective in nominative singular masculine form

        Returns:
            Tuple of (AdjectiveDeclension, success flag)
        """
        logger.info(f"Fetching adjective declensions for '{word}'")

        # Fetch the page wikitext
        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return AdjectiveDeclension(word=word, forms={}), False

        # Extract Lithuanian section
        lt_section = self.client.extract_language_section(wikitext, "Lithuanian")
        if not lt_section:
            return AdjectiveDeclension(word=word, forms={}), False

        # Find adjective template
        templates = self.client.find_templates(lt_section, self.ADJECTIVE_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No adjective declension template found for '{word}'")
            return AdjectiveDeclension(word=word, forms={}), False

        # Use the first matching template
        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        # Parse the template to HTML
        html = self.client.parse_to_html(template_text)
        if not html:
            return AdjectiveDeclension(word=word, forms={}, raw_template=template_text), False

        # Extract forms from HTML table
        forms, alternatives = self._parse_adjective_table(html)

        result = AdjectiveDeclension(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=template_text,
        )

        success = len(forms) > 0
        if success:
            logger.info(f"Successfully extracted {len(forms)} adjective forms for '{word}'")
        else:
            logger.warning(f"No adjective forms extracted for '{word}'")

        return result, success

    def _parse_adjective_table(self, html: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """
        Parse an adjective declension HTML table.

        Lithuanian adjective tables show:
        - Rows: cases (7)
        - Columns: number/gender combinations (singular m/f, plural m/f)

        Args:
            html: HTML containing the declension table

        Returns:
            Tuple of (forms dict, alternatives dict)
        """
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        # Find the inflection table
        table = soup.find("table", class_="inflection-table")
        if not table or not isinstance(table, Tag):
            return forms, alternatives

        rows = table.find_all("tr")
        if not rows:
            return forms, alternatives

        # Detect column structure from header
        # Typical: case | singular m | singular f | plural m | plural f
        column_map: Dict[int, Tuple[str, str]] = {}  # index -> (number, gender)

        header_row = rows[0]
        header_cells = header_row.find_all(["th", "td"])

        for i, cell in enumerate(header_cells):
            text = cell.get_text(strip=True).lower()
            if "singular" in text and "masc" in text:
                column_map[i] = ("singular", "m")
            elif "singular" in text and "fem" in text:
                column_map[i] = ("singular", "f")
            elif "plural" in text and "masc" in text:
                column_map[i] = ("plural", "m")
            elif "plural" in text and "fem" in text:
                column_map[i] = ("plural", "f")
            elif "masculine" in text:
                column_map[i] = ("singular", "m")  # Default to singular
            elif "feminine" in text:
                column_map[i] = ("singular", "f")

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            # First cell is the case name
            case_cell_text = cells[0].get_text(strip=True).lower()
            matched_case = None

            for known_case, internal_name in self.CASE_NAME_MAP.items():
                if known_case in case_cell_text:
                    matched_case = internal_name
                    break

            if not matched_case:
                continue

            # Parse form cells
            for i, cell in enumerate(cells[1:], start=1):
                if i not in column_map:
                    continue

                number, gender = column_map[i]
                form_text = cell.get_text(strip=True)
                cleaned = clean_form(form_text)

                if cleaned:
                    form_key = f"{matched_case}_{number}_{gender}"
                    forms[form_key] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives[form_key] = cleaned[1:]

        return forms, alternatives

    def get_adverb_forms(self, word: str) -> Tuple[AdverbForms, bool]:
        """
        Get comparative forms for a Lithuanian adverb.

        Args:
            word: Lithuanian adverb in positive form

        Returns:
            Tuple of (AdverbForms, success flag)
        """
        logger.info(f"Fetching adverb forms for '{word}'")

        # Fetch the page wikitext
        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return AdverbForms(word=word, forms={}), False

        # Extract Lithuanian section
        lt_section = self.client.extract_language_section(wikitext, "Lithuanian")
        if not lt_section:
            return AdverbForms(word=word, forms={}), False

        # Try to find adverb template
        templates = self.client.find_templates(lt_section, self.ADVERB_TEMPLATE_PATTERNS)

        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}
        raw_template: Optional[str] = None

        if templates:
            template_name, template_text = templates[0]
            raw_template = template_text
            logger.debug(f"Found adverb template: {template_name}")

            # Parse the template to HTML
            html = self.client.parse_to_html(template_text)
            if html:
                forms, alternatives = self._parse_adverb_table(html)

        # If no forms found from template, try to parse from section text
        if not forms:
            forms, alternatives = self._extract_adverb_forms_from_text(lt_section, word)

        result = AdverbForms(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=raw_template,
        )

        success = len(forms) > 0
        if success:
            logger.info(f"Successfully extracted {len(forms)} adverb forms for '{word}'")
        else:
            # Adverbs often don't have explicit templates; the positive form is the word itself
            forms["positive"] = word
            result = AdverbForms(word=word, forms=forms)
            success = True
            logger.info(f"Using word as positive form for adverb '{word}'")

        return result, success

    def _parse_adverb_table(self, html: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """
        Parse an adverb HTML table or template output.

        Args:
            html: HTML containing adverb information

        Returns:
            Tuple of (forms dict, alternatives dict)
        """
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        # Look for comparative forms in various formats
        degree_keywords = {
            "positive": ["positive", "pos", "basic"],
            "comparative": ["comparative", "comp", "more"],
            "superlative": ["superlative", "sup", "most"],
        }

        # Try to find forms in table cells or spans
        for degree, keywords in degree_keywords.items():
            for keyword in keywords:
                # Look for labeled elements
                elements = soup.find_all(
                    string=lambda text: text and keyword.lower() in text.lower() if text else False
                )
                for elem in elements:
                    # Get the next sibling or parent's content
                    parent = elem.parent
                    if parent:
                        text = parent.get_text(strip=True)
                        # Extract the form after the keyword
                        parts = text.split(":")
                        if len(parts) > 1:
                            form_text = parts[1].strip()
                            cleaned = clean_form(form_text)
                            if cleaned and degree not in forms:
                                forms[degree] = extract_primary_form(cleaned)
                                if len(cleaned) > 1:
                                    alternatives[degree] = cleaned[1:]

        return forms, alternatives

    def _extract_adverb_forms_from_text(
        self, lt_section: str, word: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """
        Try to extract adverb forms from section text.

        Args:
            lt_section: Lithuanian section wikitext
            word: The word being looked up

        Returns:
            Tuple of (forms dict, alternatives dict)
        """
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        # Common patterns for comparative forms in wikitext
        # Pattern: comparative form {{lt-adv|comp=...}}
        comp_match = re.search(r"comp(?:arative)?[=:]\s*([^\s|}\]]+)", lt_section)
        if comp_match:
            cleaned = clean_form(comp_match.group(1))
            if cleaned:
                forms["comparative"] = extract_primary_form(cleaned)

        # Pattern: superlative form
        sup_match = re.search(r"sup(?:erlative)?[=:]\s*([^\s|}\]]+)", lt_section)
        if sup_match:
            cleaned = clean_form(sup_match.group(1))
            if cleaned:
                forms["superlative"] = extract_primary_form(cleaned)

        # The positive form is typically the word itself
        if word:
            forms["positive"] = word

        return forms, alternatives


# Convenience functions for direct use


def get_lithuanian_noun_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get Lithuanian noun declensions from Wiktionary.

    Args:
        word: Lithuanian noun to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = LithuanianParser(debug=debug)
    result, success = parser.get_noun_declensions(word)
    return result.forms, success


def get_lithuanian_verb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get Lithuanian verb conjugations from Wiktionary.

    Args:
        word: Lithuanian verb (infinitive) to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = LithuanianParser(debug=debug)
    result, success = parser.get_verb_conjugations(word)
    return result.forms, success


def get_lithuanian_adjective_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get Lithuanian adjective declensions from Wiktionary.

    Args:
        word: Lithuanian adjective to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = LithuanianParser(debug=debug)
    result, success = parser.get_adjective_declensions(word)
    return result.forms, success


def get_lithuanian_adverb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get Lithuanian adverb forms from Wiktionary.

    Args:
        word: Lithuanian adverb to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = LithuanianParser(debug=debug)
    result, success = parser.get_adverb_forms(word)
    return result.forms, success
