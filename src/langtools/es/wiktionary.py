"""Spanish Wiktionary parsing for grammatical forms."""

import logging
import re
from typing import Dict, List, Optional, Tuple

try:
    from bs4 import BeautifulSoup, Tag  # type: ignore[import-not-found]

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None  # type: ignore[assignment, misc]
    Tag = None  # type: ignore[assignment, misc]

from clients.wiktionary import WiktionaryClient, extract_primary_form
from clients.wiktionary.types import NounNumberType
from langtools.es.types import (
    AdjectiveDeclension,
    AdverbForms,
    NounDeclension,
    SpanishGender,
    VerbConjugation,
)
from langtools.es.utils import clean_form, detect_gender_from_article, extract_article

logger = logging.getLogger(__name__)


class SpanishParser:
    """Parser for Spanish grammatical forms from Wiktionary."""

    LANGUAGE = "Spanish"
    LANGUAGE_CODE = "es"

    # Template patterns for different parts of speech
    NOUN_TEMPLATE_PATTERNS = [
        r"es-noun[^}]*",  # Main noun template
        r"es-proper noun[^}]*",  # Proper noun template
    ]

    VERB_TEMPLATE_PATTERNS = [
        r"es-conj[^}]*",  # Conjugation templates
        r"es-verb[^}]*",  # Verb templates
    ]

    ADJECTIVE_TEMPLATE_PATTERNS = [
        r"es-adj[^}]*",  # Adjective templates
    ]

    ADVERB_TEMPLATE_PATTERNS = [
        r"es-adv[^}]*",  # Adverb templates
    ]

    # Person/number mapping for verbs
    PERSON_MAP = {
        "yo": "1s",
        "tú": "2s",
        "tu": "2s",
        "vos": "2s",  # Latin American informal
        "él": "3s",
        "el": "3s",
        "ella": "3s",
        "usted": "3s",
        "él/ella/usted": "3s",
        "él, ella, usted": "3s",
        "nosotros": "1p",
        "nosotras": "1p",
        "vosotros": "2p",
        "vosotras": "2p",
        "ellos": "3p",
        "ellas": "3p",
        "ustedes": "3p",
        "ellos/ellas/ustedes": "3p",
        "ellos, ellas, ustedes": "3p",
        "1st singular": "1s",
        "2nd singular": "2s",
        "3rd singular": "3s",
        "1st plural": "1p",
        "2nd plural": "2p",
        "3rd plural": "3p",
    }

    # Tense name mapping
    TENSE_MAP = {
        "present": "present",
        "presente": "present",
        "indicative present": "present",
        "presente de indicativo": "present",
        "preterite": "preterite",
        "pretérito": "preterite",
        "preterit": "preterite",
        "pretérito indefinido": "preterite",
        "pretérito perfecto simple": "preterite",
        "imperfect": "imperfect",
        "imperfecto": "imperfect",
        "pretérito imperfecto": "imperfect",
        "future": "future",
        "futuro": "future",
        "futuro simple": "future",
        "conditional": "conditional",
        "condicional": "conditional",
        "condicional simple": "conditional",
        "subjunctive": "subjunctive_present",
        "subjuntivo": "subjunctive_present",
        "present subjunctive": "subjunctive_present",
        "presente de subjuntivo": "subjunctive_present",
        "imperative": "imperative",
        "imperativo": "imperative",
    }

    def __init__(self, client: Optional[WiktionaryClient] = None, debug: bool = False):
        """
        Initialize the Spanish parser.

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
        Get all forms for a Spanish noun.

        Args:
            word: Spanish noun in singular form (lemma form)

        Returns:
            Tuple of (NounDeclension, success flag)
        """
        logger.info(f"Fetching noun forms for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return NounDeclension(word=word), False

        es_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not es_section:
            return NounDeclension(word=word), False

        # Try to detect gender from headword template
        gender = self._extract_gender(es_section)

        templates = self.client.find_templates(es_section, self.NOUN_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No noun template found for '{word}'")
            # Try to extract forms from the section text
            forms, alternatives = self._extract_noun_forms_from_text(es_section, word)
            return (
                NounDeclension(word=word, gender=gender, forms=forms, alternatives=alternatives),
                len(forms) > 0,
            )

        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        # Extract forms from template parameters first
        forms, alternatives, detected_gender = self._parse_noun_template(template_text)

        # Use detected gender if not found earlier
        if detected_gender and not gender:
            gender = detected_gender

        # If no forms from template params, try HTML parsing
        if not forms:
            html = self.client.parse_to_html(template_text)
            if html:
                forms, alternatives, number_type = self._parse_noun_table(html)
            else:
                number_type = NounNumberType.REGULAR
        else:
            number_type = self._determine_number_type(forms)

        # Ensure singular form exists
        if "singular" not in forms:
            forms["singular"] = word

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
            logger.info(f"Successfully extracted {len(forms)} noun forms for '{word}'")
        else:
            logger.warning(f"No noun forms extracted for '{word}'")

        return result, success

    def _extract_gender(self, wikitext: str) -> Optional[SpanishGender]:
        """Extract gender from wikitext."""
        # Look for gender indicators in templates
        gender_patterns = [
            (r"\|g=m\b", SpanishGender.MASCULINE),
            (r"\|g=f\b", SpanishGender.FEMININE),
            (r"\{\{es-noun\|m\b", SpanishGender.MASCULINE),
            (r"\{\{es-noun\|f\b", SpanishGender.FEMININE),
            (r"\|m\|", SpanishGender.MASCULINE),
            (r"\|f\|", SpanishGender.FEMININE),
            (r"'''el'''", SpanishGender.MASCULINE),
            (r"'''la'''", SpanishGender.FEMININE),
            (r"\{\{m\}\}", SpanishGender.MASCULINE),
            (r"\{\{f\}\}", SpanishGender.FEMININE),
        ]

        for pattern, gender in gender_patterns:
            if re.search(pattern, wikitext, re.IGNORECASE):
                return gender

        return None

    def _parse_noun_template(
        self, template_text: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]], Optional[SpanishGender]]:
        """Parse noun template parameters to extract forms."""
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}
        gender: Optional[SpanishGender] = None

        # Extract template parameters
        # Format: {{es-noun|m|plural}}
        # or {{es-noun|f|pl=plurales}}
        params = re.findall(r"\|([^|}]+)", template_text)

        for i, param in enumerate(params):
            param = param.strip()

            # Check for gender
            if param in ("m", "mf"):
                gender = SpanishGender.MASCULINE
            elif param == "f":
                gender = SpanishGender.FEMININE

            # Check for plural parameter
            if "=" in param:
                key, value = param.split("=", 1)
                key = key.strip().lower()
                value = value.strip()
                if key in ("pl", "plural"):
                    cleaned = clean_form(value)
                    if cleaned:
                        forms["plural"] = extract_primary_form(cleaned)
                        if len(cleaned) > 1:
                            alternatives["plural"] = cleaned[1:]
            elif i > 0 and param not in ("m", "f", "mf", "-"):
                # Positional parameter after gender is often the plural
                cleaned = clean_form(param)
                if cleaned and "plural" not in forms:
                    forms["plural"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["plural"] = cleaned[1:]

        return forms, alternatives, gender

    def _extract_noun_forms_from_text(
        self, wikitext: str, word: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Extract noun forms from section text when no template found."""
        forms: Dict[str, str] = {"singular": word}
        alternatives: Dict[str, List[str]] = {}

        # Look for plural patterns
        plural_patterns = [
            r"plural[:\s]+['\"]*(\w+)",
            r"plural\s*=\s*(\w+)",
            r"\|pl=(\w+)",
        ]
        for pattern in plural_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match:
                forms["plural"] = match.group(1)
                break

        return forms, alternatives

    def _parse_noun_table(
        self, html: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]], NounNumberType]:
        """Parse a Spanish noun HTML table."""
        if not BS4_AVAILABLE:
            raise ImportError(
                "BeautifulSoup4 (bs4) is required for parsing Wiktionary HTML tables. "
                "Install it with: pip install beautifulsoup4"
            )
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        # Find the inflection table
        table = soup.find("table", class_="inflection-table")
        if not table or not isinstance(table, Tag):
            table = soup.find("table")
            if not table or not isinstance(table, Tag):
                logger.warning("No inflection table found in HTML")
                return forms, alternatives, NounNumberType.REGULAR

        rows = table.find_all("tr")
        if not rows:
            return forms, alternatives, NounNumberType.REGULAR

        # Parse table for singular/plural
        for row in rows:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            header_text = cells[0].get_text(strip=True).lower()

            if "singular" in header_text:
                form_text = cells[1].get_text(strip=True)
                _, noun_form = extract_article(form_text)
                cleaned = clean_form(noun_form)
                if cleaned:
                    forms["singular"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["singular"] = cleaned[1:]
            elif "plural" in header_text:
                form_text = cells[1].get_text(strip=True)
                _, noun_form = extract_article(form_text)
                cleaned = clean_form(noun_form)
                if cleaned:
                    forms["plural"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["plural"] = cleaned[1:]

        number_type = self._determine_number_type(forms)
        return forms, alternatives, number_type

    def _determine_number_type(self, forms: Dict[str, str]) -> NounNumberType:
        """Determine the number type from available forms."""
        has_singular = "singular" in forms
        has_plural = "plural" in forms

        if has_singular and has_plural:
            return NounNumberType.REGULAR
        elif has_plural and not has_singular:
            return NounNumberType.PLURALE_TANTUM
        else:
            return NounNumberType.SINGULARE_TANTUM

    def get_verb_conjugations(self, word: str) -> Tuple[VerbConjugation, bool]:
        """
        Get all conjugation forms for a Spanish verb.

        Args:
            word: Spanish verb in infinitive form

        Returns:
            Tuple of (VerbConjugation, success flag)
        """
        logger.info(f"Fetching verb conjugations for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return VerbConjugation(word=word), False

        es_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not es_section:
            return VerbConjugation(word=word), False

        templates = self.client.find_templates(es_section, self.VERB_TEMPLATE_PATTERNS)
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

        # Extract participles and gerund
        self._extract_non_finite_forms(html, forms)

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
        """Parse a Spanish verb conjugation HTML table."""
        if not BS4_AVAILABLE:
            raise ImportError(
                "BeautifulSoup4 (bs4) is required for parsing Wiktionary HTML tables. "
                "Install it with: pip install beautifulsoup4"
            )
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

        # Detect current tense from table headers or surrounding context
        current_tense = "present"
        tense_columns: Dict[int, str] = {}

        # Check for tense in table caption or header
        caption = table.find("caption")
        if caption:
            caption_text = caption.get_text(strip=True).lower()
            for tense_name, tense_code in self.TENSE_MAP.items():
                if tense_name in caption_text:
                    current_tense = tense_code
                    break

        # Parse header row for tense columns
        header_row = rows[0]
        header_cells = header_row.find_all(["th", "td"])

        for i, cell in enumerate(header_cells):
            text = cell.get_text(strip=True).lower()
            for tense_name, tense_code in self.TENSE_MAP.items():
                if tense_name in text:
                    tense_columns[i] = tense_code
                    break

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
                tense = tense_columns.get(i, current_tense)
                form_text = cell.get_text(strip=True)
                cleaned = clean_form(form_text)

                if cleaned:
                    form_key = f"{person}_{tense}"
                    if form_key not in forms:
                        forms[form_key] = extract_primary_form(cleaned)
                        if len(cleaned) > 1:
                            alternatives[form_key] = cleaned[1:]

    def _extract_non_finite_forms(self, html: str, forms: Dict[str, str]) -> None:
        """Extract gerund and participle forms from HTML."""
        if not BS4_AVAILABLE:
            raise ImportError(
                "BeautifulSoup4 (bs4) is required for parsing Wiktionary HTML tables. "
                "Install it with: pip install beautifulsoup4"
            )
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()

        # Look for gerund (gerundio)
        gerund_patterns = [
            r"gerund[io]*[:\s]+(\w+)",
            r"gerundio[:\s]+(\w+)",
        ]
        for pattern in gerund_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                forms["gerund"] = match.group(1)
                break

        # Look for past participle (participio)
        participle_patterns = [
            r"past participle[:\s]+(\w+)",
            r"participio[:\s]+(\w+)",
            r"participio pasado[:\s]+(\w+)",
        ]
        for pattern in participle_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                forms["past_participle"] = match.group(1)
                break

    def get_adjective_declensions(self, word: str) -> Tuple[AdjectiveDeclension, bool]:
        """
        Get all forms for a Spanish adjective.

        Args:
            word: Spanish adjective in masculine singular form

        Returns:
            Tuple of (AdjectiveDeclension, success flag)
        """
        logger.info(f"Fetching adjective forms for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return AdjectiveDeclension(word=word), False

        es_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not es_section:
            return AdjectiveDeclension(word=word), False

        templates = self.client.find_templates(es_section, self.ADJECTIVE_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No adjective template found for '{word}'")
            return AdjectiveDeclension(word=word), False

        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        # Extract forms from template parameters first
        forms, alternatives = self._parse_adjective_template(template_text, word)

        # If no forms from template params, try HTML parsing
        if len(forms) <= 1:  # Only have singular_m (base form)
            html = self.client.parse_to_html(template_text)
            if html:
                html_forms, html_alts = self._parse_adjective_table(html)
                forms.update(html_forms)
                alternatives.update(html_alts)

        # Extract comparison forms from wikitext
        self._extract_comparison_forms(es_section, forms, word)

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

    def _parse_adjective_template(
        self, template_text: str, word: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Parse adjective template parameters to extract forms."""
        forms: Dict[str, str] = {"singular_m": word}
        alternatives: Dict[str, List[str]] = {}

        # Extract template parameters
        # Format: {{es-adj|f=feminine|mpl=masculine_plural|fpl=feminine_plural}}
        # or {{es-adj}} for invariable adjectives
        params = re.findall(r"\|([^|}]+)", template_text)

        for param in params:
            param = param.strip()
            if "=" in param:
                key, value = param.split("=", 1)
                key = key.strip().lower()
                value = value.strip()

                cleaned = clean_form(value)
                if not cleaned:
                    continue

                if key in ("f", "fem", "feminine"):
                    forms["singular_f"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["singular_f"] = cleaned[1:]
                elif key in ("mpl", "masculine plural", "mp"):
                    forms["plural_m"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["plural_m"] = cleaned[1:]
                elif key in ("fpl", "feminine plural", "fp"):
                    forms["plural_f"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["plural_f"] = cleaned[1:]
                elif key in ("pl", "plural"):
                    # Common plural for both genders
                    forms["plural_m"] = extract_primary_form(cleaned)
                    forms["plural_f"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["plural_m"] = cleaned[1:]
                        alternatives["plural_f"] = cleaned[1:]

        # Generate regular forms if not specified
        if "singular_f" not in forms:
            # Regular pattern: -o -> -a, or same form
            if word.endswith("o"):
                forms["singular_f"] = word[:-1] + "a"
            else:
                forms["singular_f"] = word  # invariable

        if "plural_m" not in forms:
            # Regular pattern: add -s or -es
            if word.endswith(("a", "e", "i", "o", "u")):
                forms["plural_m"] = word + "s"
            else:
                forms["plural_m"] = word + "es"

        if "plural_f" not in forms:
            f_form = forms.get("singular_f", word)
            if f_form.endswith(("a", "e", "i", "o", "u")):
                forms["plural_f"] = f_form + "s"
            else:
                forms["plural_f"] = f_form + "es"

        return forms, alternatives

    def _parse_adjective_table(self, html: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Parse a Spanish adjective HTML table."""
        if not BS4_AVAILABLE:
            raise ImportError(
                "BeautifulSoup4 (bs4) is required for parsing Wiktionary HTML tables. "
                "Install it with: pip install beautifulsoup4"
            )
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        table = soup.find("table", class_="inflection-table")
        if not table or not isinstance(table, Tag):
            return forms, alternatives

        rows = table.find_all("tr")
        if not rows:
            return forms, alternatives

        # Parse table - typically has masculine/feminine columns and singular/plural rows
        for row in rows:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            header_text = cells[0].get_text(strip=True).lower()

            if "singular" in header_text:
                # Look for masculine and feminine columns
                for i, cell in enumerate(cells[1:], start=1):
                    form_text = cell.get_text(strip=True)
                    cleaned = clean_form(form_text)
                    if cleaned:
                        if i == 1:
                            forms["singular_m"] = extract_primary_form(cleaned)
                        elif i == 2:
                            forms["singular_f"] = extract_primary_form(cleaned)
            elif "plural" in header_text:
                for i, cell in enumerate(cells[1:], start=1):
                    form_text = cell.get_text(strip=True)
                    cleaned = clean_form(form_text)
                    if cleaned:
                        if i == 1:
                            forms["plural_m"] = extract_primary_form(cleaned)
                        elif i == 2:
                            forms["plural_f"] = extract_primary_form(cleaned)

        return forms, alternatives

    def _extract_comparison_forms(self, wikitext: str, forms: Dict[str, str], word: str) -> None:
        """Extract comparative and superlative forms from wikitext."""
        forms["positive"] = word

        # Look for comparative
        comp_patterns = [
            r"comparative[:\s]+(\w+)",
            r"comparativo[:\s]+(\w+)",
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
            r"superlativo[:\s]+(\w+)",
            r"\|sup=(\w+)",
        ]
        for pattern in sup_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match:
                forms["superlative"] = match.group(1)
                break

    def get_adverb_forms(self, word: str) -> Tuple[AdverbForms, bool]:
        """
        Get comparative forms for a Spanish adverb.

        Args:
            word: Spanish adverb in positive form

        Returns:
            Tuple of (AdverbForms, success flag)
        """
        logger.info(f"Fetching adverb forms for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return AdverbForms(word=word, forms={"positive": word}), True

        es_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not es_section:
            return AdverbForms(word=word, forms={"positive": word}), True

        forms: Dict[str, str] = {"positive": word}
        alternatives: Dict[str, List[str]] = {}

        templates = self.client.find_templates(es_section, self.ADVERB_TEMPLATE_PATTERNS)
        raw_template: Optional[str] = None

        if templates:
            template_name, template_text = templates[0]
            raw_template = template_text
            logger.debug(f"Found adverb template: {template_name}")

            html = self.client.parse_to_html(template_text)
            if html:
                parsed_forms, parsed_alts = self._parse_adverb_data(html, es_section, word)
                forms.update(parsed_forms)
                alternatives.update(parsed_alts)

        # Try to extract from wikitext
        self._extract_adverb_comparison(es_section, forms)

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
        if not BS4_AVAILABLE:
            raise ImportError(
                "BeautifulSoup4 (bs4) is required for parsing Wiktionary HTML tables. "
                "Install it with: pip install beautifulsoup4"
            )
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        soup = BeautifulSoup(html, "html.parser")

        # Look for comparative forms in various formats
        degree_keywords = {
            "positive": ["positive", "positivo"],
            "comparative": ["comparative", "comparativo"],
            "superlative": ["superlative", "superlativo"],
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
            r"comparativo[:\s]+(\w+)",
        ]
        for pattern in comp_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match and "comparative" not in forms:
                forms["comparative"] = match.group(1)
                break

        sup_patterns = [
            r"superlative[:\s]+(\w+)",
            r"superlativo[:\s]+(\w+)",
        ]
        for pattern in sup_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match and "superlative" not in forms:
                forms["superlative"] = match.group(1)
                break


# Convenience functions for direct use


def get_spanish_noun_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get Spanish noun forms from Wiktionary.

    Args:
        word: Spanish noun to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = SpanishParser(debug=debug)
    result, success = parser.get_noun_declensions(word)
    return result.forms, success


def get_spanish_verb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get Spanish verb conjugations from Wiktionary.

    Args:
        word: Spanish verb (infinitive) to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = SpanishParser(debug=debug)
    result, success = parser.get_verb_conjugations(word)
    return result.forms, success


def get_spanish_adjective_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get Spanish adjective forms from Wiktionary.

    Args:
        word: Spanish adjective to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = SpanishParser(debug=debug)
    result, success = parser.get_adjective_declensions(word)
    return result.forms, success


def get_spanish_adverb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get Spanish adverb forms from Wiktionary.

    Args:
        word: Spanish adverb to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = SpanishParser(debug=debug)
    result, success = parser.get_adverb_forms(word)
    return result.forms, success
