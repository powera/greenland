"""German Wiktionary parsing for grammatical forms."""

import logging
import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from clients.wiktionary import WiktionaryClient, extract_primary_form
from clients.wiktionary.types import NounNumberType
from langtools.de.types import (
    AdjectiveDeclension,
    AdverbForms,
    GermanGender,
    NounDeclension,
    VerbConjugation,
)
from langtools.de.utils import clean_form, detect_gender_from_article, extract_article

logger = logging.getLogger(__name__)


class GermanParser:
    """Parser for German grammatical forms from Wiktionary."""

    LANGUAGE = "German"
    LANGUAGE_CODE = "de"

    # Template patterns for different parts of speech
    NOUN_TEMPLATE_PATTERNS = [
        r"de-ndecl[^}]*",  # Modern noun declension template
        r"de-noun[^}]*",  # Noun template
        r"de-decl-noun[^}]*",  # Alternative declension template
    ]

    VERB_TEMPLATE_PATTERNS = [
        r"de-conj[^}]*",  # Conjugation templates
        r"de-verb[^}]*",  # Verb templates
    ]

    ADJECTIVE_TEMPLATE_PATTERNS = [
        r"de-adj[^}]*",  # Adjective templates
        r"de-decl-adj[^}]*",  # Adjective declension templates
    ]

    ADVERB_TEMPLATE_PATTERNS = [
        r"de-adv[^}]*",  # Adverb templates
    ]

    # Case name mapping from Wiktionary to our internal format
    CASE_NAME_MAP = {
        "nominative": "nominative",
        "nominativ": "nominative",
        "genitive": "genitive",
        "genitiv": "genitive",
        "dative": "dative",
        "dativ": "dative",
        "accusative": "accusative",
        "akkusativ": "accusative",
    }

    # Person/number mapping for verbs
    PERSON_MAP = {
        "ich": "1s",
        "du": "2s",
        "er": "3s",
        "sie": "3s",  # Could be 3s or 3p
        "es": "3s",
        "er/sie/es": "3s",
        "wir": "1p",
        "ihr": "2p",
        "sie/sie": "3p",
        "1st singular": "1s",
        "2nd singular": "2s",
        "3rd singular": "3s",
        "1st plural": "1p",
        "2nd plural": "2p",
        "3rd plural": "3p",
    }

    def __init__(self, client: Optional[WiktionaryClient] = None, debug: bool = False):
        """
        Initialize the German parser.

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
        Get all declension forms for a German noun.

        Args:
            word: German noun in nominative singular (lemma form)

        Returns:
            Tuple of (NounDeclension, success flag)
        """
        logger.info(f"Fetching noun declensions for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return NounDeclension(word=word), False

        de_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not de_section:
            return NounDeclension(word=word), False

        # Try to detect gender from headword template
        gender = self._extract_gender(de_section)

        templates = self.client.find_templates(de_section, self.NOUN_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No noun declension template found for '{word}'")
            return NounDeclension(word=word, gender=gender), False

        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        html = self.client.parse_to_html(template_text)
        if not html:
            return NounDeclension(word=word, gender=gender, raw_template=template_text), False

        forms, alternatives, number_type = self._parse_noun_table(html)

        result = NounDeclension(
            word=word,
            gender=gender,
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

    def _extract_gender(self, wikitext: str) -> Optional[GermanGender]:
        """Extract gender from wikitext."""
        # Look for gender indicators in templates
        gender_patterns = [
            (r"\|g=m\b", GermanGender.MASCULINE),
            (r"\|g=f\b", GermanGender.FEMININE),
            (r"\|g=n\b", GermanGender.NEUTER),
            (r"\{\{de-noun\|m\b", GermanGender.MASCULINE),
            (r"\{\{de-noun\|f\b", GermanGender.FEMININE),
            (r"\{\{de-noun\|n\b", GermanGender.NEUTER),
            (r"'''der'''", GermanGender.MASCULINE),
            (r"'''die'''", GermanGender.FEMININE),
            (r"'''das'''", GermanGender.NEUTER),
        ]

        for pattern, gender in gender_patterns:
            if re.search(pattern, wikitext, re.IGNORECASE):
                return gender

        return None

    def _parse_noun_table(
        self, html: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]], NounNumberType]:
        """Parse a German noun declension HTML table."""
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        # Find the inflection table
        table = soup.find("table", class_="inflection-table")
        if not table or not isinstance(table, Tag):
            # Try without class
            table = soup.find("table")
            if not table or not isinstance(table, Tag):
                logger.warning("No inflection table found in HTML")
                return forms, alternatives, NounNumberType.REGULAR

        rows = table.find_all("tr")
        if not rows:
            return forms, alternatives, NounNumberType.REGULAR

        # Detect column structure
        singular_col = -1
        plural_col = -1

        header_row = rows[0] if rows else None
        if header_row:
            header_cells = header_row.find_all(["th", "td"])
            for i, cell in enumerate(header_cells):
                text = cell.get_text(strip=True).lower()
                if "singular" in text or "einzahl" in text:
                    singular_col = i
                elif "plural" in text or "mehrzahl" in text:
                    plural_col = i

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            # First cell is usually the case name
            case_cell_text = cells[0].get_text(strip=True).lower()
            matched_case = None

            for known_case, internal_name in self.CASE_NAME_MAP.items():
                if known_case in case_cell_text:
                    matched_case = internal_name
                    break

            if not matched_case:
                continue

            # Extract forms based on column positions
            for i, cell in enumerate(cells[1:], start=1):
                form_text = cell.get_text(strip=True)
                # Extract just the noun (remove article if present)
                _, noun_form = extract_article(form_text)
                cleaned = clean_form(noun_form)

                if cleaned:
                    # Determine if this is singular or plural
                    if singular_col >= 0 and i == singular_col:
                        form_key = f"{matched_case}_singular"
                    elif plural_col >= 0 and i == plural_col:
                        form_key = f"{matched_case}_plural"
                    elif i == 1:
                        form_key = f"{matched_case}_singular"
                    elif i == 2:
                        form_key = f"{matched_case}_plural"
                    else:
                        continue

                    forms[form_key] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives[form_key] = cleaned[1:]

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
        Get all conjugation forms for a German verb.

        Args:
            word: German verb in infinitive form

        Returns:
            Tuple of (VerbConjugation, success flag)
        """
        logger.info(f"Fetching verb conjugations for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return VerbConjugation(word=word), False

        de_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not de_section:
            return VerbConjugation(word=word), False

        templates = self.client.find_templates(de_section, self.VERB_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No verb conjugation template found for '{word}'")
            return VerbConjugation(word=word), False

        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        html = self.client.parse_to_html(template_text)
        if not html:
            return VerbConjugation(word=word, raw_template=template_text), False

        forms, alternatives = self._parse_verb_table(html)

        # Add infinitive
        forms["infinitive"] = word

        result = VerbConjugation(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=template_text,
        )

        success = len(forms) > 1  # More than just infinitive
        if success:
            logger.info(f"Successfully extracted {len(forms)} conjugation forms for '{word}'")
        else:
            logger.warning(f"No conjugation forms extracted for '{word}'")

        return result, success

    def _parse_verb_table(self, html: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Parse a German verb conjugation HTML table."""
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        tables = soup.find_all("table", class_="inflection-table")
        if not tables:
            tables = soup.find_all("table")

        for table in tables:
            if not isinstance(table, Tag):
                continue
            self._parse_single_verb_table(table, forms, alternatives)

        # Also look for participles and other forms
        self._extract_participles(soup, forms)

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
            if "present" in text or "präsens" in text:
                tense_columns[i] = "present"
            elif "preterite" in text or "präteritum" in text or "past" in text:
                tense_columns[i] = "past"
            elif "subjunctive" in text or "konjunktiv" in text:
                tense_columns[i] = "subjunctive"

        # Parse data rows
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            person_cell = cells[0].get_text(strip=True).lower()
            person = None

            for pattern, person_code in self.PERSON_MAP.items():
                if pattern.lower() in person_cell:
                    person = person_code
                    break

            if not person:
                continue

            for i, cell in enumerate(cells[1:], start=1):
                tense = tense_columns.get(i, "present")
                form_text = cell.get_text(strip=True)
                cleaned = clean_form(form_text)

                if cleaned:
                    form_key = f"{person}_{tense}"
                    if form_key not in forms:
                        forms[form_key] = extract_primary_form(cleaned)
                        if len(cleaned) > 1:
                            alternatives[form_key] = cleaned[1:]

    def _extract_participles(self, soup: BeautifulSoup, forms: Dict[str, str]) -> None:
        """Extract participle forms from the page."""
        # Look for past participle (Partizip II)
        text = soup.get_text()

        past_part_patterns = [
            r"past participle[:\s]+(\w+)",
            r"Partizip II[:\s]+(\w+)",
            r"perfect participle[:\s]+(\w+)",
        ]
        for pattern in past_part_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                forms["past_participle"] = match.group(1)
                break

        # Look for auxiliary verb
        if "sein" in text.lower() and "auxiliary" not in forms:
            forms["auxiliary"] = "sein"
        elif "haben" in text.lower() and "auxiliary" not in forms:
            forms["auxiliary"] = "haben"

    def get_adjective_declensions(self, word: str) -> Tuple[AdjectiveDeclension, bool]:
        """
        Get all declension forms for a German adjective.

        Args:
            word: German adjective in base form

        Returns:
            Tuple of (AdjectiveDeclension, success flag)
        """
        logger.info(f"Fetching adjective declensions for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return AdjectiveDeclension(word=word), False

        de_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not de_section:
            return AdjectiveDeclension(word=word), False

        templates = self.client.find_templates(de_section, self.ADJECTIVE_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No adjective declension template found for '{word}'")
            return AdjectiveDeclension(word=word), False

        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        html = self.client.parse_to_html(template_text)
        if not html:
            return AdjectiveDeclension(word=word, raw_template=template_text), False

        forms, alternatives = self._parse_adjective_table(html)

        # Extract comparison forms from wikitext
        self._extract_comparison_forms(de_section, forms, word)

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
        """Parse a German adjective declension HTML table.

        Form names align with GrammaticalForm enum (singular_m, singular_f, etc.)
        """
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        table = soup.find("table", class_="inflection-table")
        if not table or not isinstance(table, Tag):
            return forms, alternatives

        rows = table.find_all("tr")
        if not rows:
            return forms, alternatives

        # German adjective tables are complex; extract simplified forms
        # for alignment with GrammaticalForm enum
        for row in rows:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            case_text = cells[0].get_text(strip=True).lower()

            # Only extract nominative forms for simplified gender/number forms
            if "nominativ" not in case_text and "nominative" not in case_text:
                continue

            for i, cell in enumerate(cells[1:], start=1):
                form_text = cell.get_text(strip=True)
                cleaned = clean_form(form_text)
                if cleaned:
                    # Map column index to gender/number
                    # Typical order: masculine, feminine, neuter, plural
                    if i == 1:
                        form_key = "singular_m"
                    elif i == 2:
                        form_key = "singular_f"
                    elif i == 4:
                        form_key = "plural_m"  # plural is gender-neutral in German
                        if "plural_f" not in forms:
                            forms["plural_f"] = extract_primary_form(cleaned)
                    else:
                        continue  # Skip neuter for now (not in enum)

                    if form_key not in forms:
                        forms[form_key] = extract_primary_form(cleaned)
                        if len(cleaned) > 1:
                            alternatives[form_key] = cleaned[1:]

        return forms, alternatives

    def _extract_comparison_forms(self, wikitext: str, forms: Dict[str, str], word: str) -> None:
        """Extract comparative and superlative forms from wikitext."""
        forms["positive"] = word

        # Look for comparative
        comp_patterns = [
            r"comparative[:\s]+(\w+)",
            r"Komparativ[:\s]+(\w+)",
            r"\|comp=(\w+)",
        ]
        for pattern in comp_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match:
                forms["comparative"] = match.group(1)
                break

        # Look for superlative
        sup_patterns = [
            r"superlative[:\s]+(\w+)",
            r"Superlativ[:\s]+(\w+)",
            r"\|sup=(\w+)",
        ]
        for pattern in sup_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match:
                forms["superlative"] = match.group(1)
                break

    def get_adverb_forms(self, word: str) -> Tuple[AdverbForms, bool]:
        """
        Get comparative forms for a German adverb.

        Args:
            word: German adverb in positive form

        Returns:
            Tuple of (AdverbForms, success flag)
        """
        logger.info(f"Fetching adverb forms for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return AdverbForms(word=word, forms={"positive": word}), True

        de_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not de_section:
            return AdverbForms(word=word, forms={"positive": word}), True

        forms: Dict[str, str] = {"positive": word}
        alternatives: Dict[str, List[str]] = {}

        templates = self.client.find_templates(de_section, self.ADVERB_TEMPLATE_PATTERNS)
        raw_template: Optional[str] = None

        if templates:
            template_name, template_text = templates[0]
            raw_template = template_text
            logger.debug(f"Found adverb template: {template_name}")

            html = self.client.parse_to_html(template_text)
            if html:
                parsed_forms, parsed_alts = self._parse_adverb_data(html, de_section, word)
                forms.update(parsed_forms)
                alternatives.update(parsed_alts)

        # Try to extract from wikitext
        self._extract_adverb_comparison(de_section, forms)

        result = AdverbForms(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=raw_template,
        )

        logger.info(f"Successfully extracted {len(forms)} adverb forms for '{word}'")
        return result, True

    def _parse_adverb_data(
        self, html: str, wikitext: str, word: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Parse adverb data from HTML and wikitext."""
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        soup = BeautifulSoup(html, "html.parser")

        # Look for comparative forms in various formats
        degree_keywords = {
            "positive": ["positive", "positiv"],
            "comparative": ["comparative", "komparativ"],
            "superlative": ["superlative", "superlativ"],
        }

        for degree, keywords in degree_keywords.items():
            for keyword in keywords:
                elements = soup.find_all(
                    string=lambda text: text and keyword.lower() in text.lower() if text else False
                )
                for elem in elements:
                    parent = elem.parent
                    if parent:
                        text = parent.get_text(strip=True)
                        parts = text.split(":")
                        if len(parts) > 1:
                            form_text = parts[1].strip()
                            cleaned = clean_form(form_text)
                            if cleaned and degree not in forms:
                                forms[degree] = extract_primary_form(cleaned)
                                if len(cleaned) > 1:
                                    alternatives[degree] = cleaned[1:]

        return forms, alternatives

    def _extract_adverb_comparison(self, wikitext: str, forms: Dict[str, str]) -> None:
        """Extract comparative and superlative forms from wikitext."""
        comp_patterns = [
            r"comparative[:\s]+(\w+)",
            r"Komparativ[:\s]+(\w+)",
        ]
        for pattern in comp_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match and "comparative" not in forms:
                forms["comparative"] = match.group(1)
                break

        sup_patterns = [
            r"superlative[:\s]+(\w+)",
            r"Superlativ[:\s]+(\w+)",
        ]
        for pattern in sup_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match and "superlative" not in forms:
                forms["superlative"] = match.group(1)
                break


# Convenience functions for direct use


def get_german_noun_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get German noun declensions from Wiktionary.

    Args:
        word: German noun to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = GermanParser(debug=debug)
    result, success = parser.get_noun_declensions(word)
    return result.forms, success


def get_german_verb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get German verb conjugations from Wiktionary.

    Args:
        word: German verb (infinitive) to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = GermanParser(debug=debug)
    result, success = parser.get_verb_conjugations(word)
    return result.forms, success


def get_german_adjective_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get German adjective declensions from Wiktionary.

    Args:
        word: German adjective to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = GermanParser(debug=debug)
    result, success = parser.get_adjective_declensions(word)
    return result.forms, success


def get_german_adverb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get German adverb forms from Wiktionary.

    Args:
        word: German adverb to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = GermanParser(debug=debug)
    result, success = parser.get_adverb_forms(word)
    return result.forms, success
