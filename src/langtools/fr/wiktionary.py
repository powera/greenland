"""French Wiktionary parsing for grammatical forms."""

import logging
import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from clients.wiktionary import WiktionaryClient, extract_primary_form
from clients.wiktionary.types import NounNumberType
from langtools.fr.types import (
    AdjectiveDeclension,
    AdverbForms,
    FrenchGender,
    NounDeclension,
    VerbConjugation,
)
from langtools.fr.utils import clean_form, detect_gender_from_article, extract_article

logger = logging.getLogger(__name__)


class FrenchParser:
    """Parser for French grammatical forms from Wiktionary."""

    LANGUAGE = "French"
    LANGUAGE_CODE = "fr"

    # Template patterns for different parts of speech
    NOUN_TEMPLATE_PATTERNS = [
        r"fr-noun[^}]*",  # Noun template
        r"fr-noun-form[^}]*",  # Noun form template
    ]

    VERB_TEMPLATE_PATTERNS = [
        r"fr-conj[^}]*",  # Conjugation templates
        r"fr-verb[^}]*",  # Verb templates
    ]

    ADJECTIVE_TEMPLATE_PATTERNS = [
        r"fr-adj[^}]*",  # Adjective templates
    ]

    ADVERB_TEMPLATE_PATTERNS = [
        r"fr-adv[^}]*",  # Adverb templates
    ]

    # Person/number mapping for verbs
    PERSON_MAP = {
        "je": "1s",
        "j'": "1s",
        "tu": "2s",
        "il": "3s",
        "elle": "3s",
        "il/elle": "3s",
        "on": "3s",
        "nous": "1p",
        "vous": "2p",
        "ils": "3p",
        "elles": "3p",
        "ils/elles": "3p",
        "1st singular": "1s",
        "2nd singular": "2s",
        "3rd singular": "3s",
        "1st plural": "1p",
        "2nd plural": "2p",
        "3rd plural": "3p",
    }

    # Tense mapping - values align with GrammaticalForm enum codes
    TENSE_MAP = {
        "present": "present",
        "présent": "present",
        "indicative present": "present",
        "imperfect": "impf",  # Matches GrammaticalForm VERB_FR_*_IMPF
        "imparfait": "impf",
        "future": "future",
        "futur": "future",
        "futur simple": "future",
    }

    def __init__(self, client: Optional[WiktionaryClient] = None, debug: bool = False):
        """
        Initialize the French parser.

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
        Get singular and plural forms for a French noun.

        Args:
            word: French noun in singular form

        Returns:
            Tuple of (NounDeclension, success flag)
        """
        logger.info(f"Fetching noun forms for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return NounDeclension(word=word), False

        fr_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not fr_section:
            return NounDeclension(word=word), False

        # Try to detect gender
        gender = self._extract_gender(fr_section)

        # Try to find noun template
        templates = self.client.find_templates(fr_section, self.NOUN_TEMPLATE_PATTERNS)

        forms: Dict[str, str] = {"singular": word}
        alternatives: Dict[str, List[str]] = {}
        raw_template: Optional[str] = None

        if templates:
            template_name, template_text = templates[0]
            raw_template = template_text
            logger.debug(f"Found template: {template_name}")

            # Extract plural from template parameters
            plural = self._extract_plural_from_template(template_text, word)
            if plural:
                forms["plural"] = plural

        # If no plural found from template, try to parse from wikitext
        if "plural" not in forms:
            plural = self._extract_plural_from_wikitext(fr_section, word)
            if plural:
                forms["plural"] = plural

        # Determine number type
        number_type = NounNumberType.REGULAR
        if "plural" not in forms or forms.get("plural") == "-":
            number_type = NounNumberType.SINGULARE_TANTUM
            forms.pop("plural", None)

        result = NounDeclension(
            word=word,
            gender=gender,
            number_type=number_type,
            forms=forms,
            alternatives=alternatives,
            raw_template=raw_template,
        )

        success = len(forms) > 0
        if success:
            logger.info(f"Successfully extracted {len(forms)} noun forms for '{word}'")
        else:
            logger.warning(f"No noun forms extracted for '{word}'")

        return result, success

    def _extract_gender(self, wikitext: str) -> Optional[FrenchGender]:
        """Extract gender from wikitext."""
        gender_patterns = [
            (r"\|g=m\b", FrenchGender.MASCULINE),
            (r"\|g=f\b", FrenchGender.FEMININE),
            (r"\{\{fr-noun\|m\b", FrenchGender.MASCULINE),
            (r"\{\{fr-noun\|f\b", FrenchGender.FEMININE),
            (r"\{\{m\}\}", FrenchGender.MASCULINE),
            (r"\{\{f\}\}", FrenchGender.FEMININE),
            (r"'''m'''", FrenchGender.MASCULINE),
            (r"'''f'''", FrenchGender.FEMININE),
        ]

        for pattern, gender in gender_patterns:
            if re.search(pattern, wikitext, re.IGNORECASE):
                return gender

        return None

    def _extract_plural_from_template(self, template: str, word: str) -> Optional[str]:
        """Extract plural form from noun template."""
        # Look for explicit plural parameter
        plural_match = re.search(r"\|pl(?:ural)?=([^|}]+)", template)
        if plural_match:
            plural = plural_match.group(1).strip()
            if plural and plural != "-":
                return plural

        # Look for second positional parameter (often the plural)
        # {{fr-noun|m|plural}}
        parts = re.findall(r"\|([^|}]+)", template)
        if len(parts) >= 2:
            potential_plural: str = parts[1].strip()
            # Check if it looks like a plural (not a gender or other parameter)
            if potential_plural and potential_plural not in ("m", "f", "mf", "-"):
                if not potential_plural.startswith(("g=", "pl=", "head=")):
                    return potential_plural

        return None

    def _extract_plural_from_wikitext(self, wikitext: str, word: str) -> Optional[str]:
        """Try to extract plural from wikitext patterns."""
        # Look for plural patterns in definitions or headword
        patterns = [
            rf"plural[:\s]+([{word}]\w*)",
            r"pluriel[:\s]+(\w+)",
            rf"\|pl=(\w+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match:
                return match.group(1)

        # Try common French plural rules as fallback
        return self._generate_regular_plural(word)

    def _generate_regular_plural(self, word: str) -> Optional[str]:
        """Generate regular French plural form."""
        if not word:
            return None

        # Words already ending in -s, -x, -z don't change
        if word.endswith(("s", "x", "z")):
            return word

        # Words ending in -au, -eau, -eu add -x
        if word.endswith(("au", "eau", "eu")):
            return word + "x"

        # Words ending in -al change to -aux (with exceptions)
        if word.endswith("al"):
            exceptions = {"bal", "carnaval", "festival", "récital", "chacal"}
            if word.lower() not in exceptions:
                return word[:-2] + "aux"

        # Regular plural: add -s
        return word + "s"

    def get_verb_conjugations(self, word: str) -> Tuple[VerbConjugation, bool]:
        """
        Get conjugation forms for a French verb.

        Args:
            word: French verb in infinitive form

        Returns:
            Tuple of (VerbConjugation, success flag)
        """
        logger.info(f"Fetching verb conjugations for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return VerbConjugation(word=word), False

        fr_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not fr_section:
            return VerbConjugation(word=word), False

        templates = self.client.find_templates(fr_section, self.VERB_TEMPLATE_PATTERNS)
        if not templates:
            logger.warning(f"No verb conjugation template found for '{word}'")
            return VerbConjugation(word=word), False

        template_name, template_text = templates[0]
        logger.debug(f"Found template: {template_name}")

        html = self.client.parse_to_html(template_text)
        if not html:
            return VerbConjugation(word=word, raw_template=template_text), False

        forms, alternatives = self._parse_verb_table(html)
        forms["infinitive"] = word

        # Try to detect auxiliary
        auxiliary = self._detect_auxiliary(fr_section)

        result = VerbConjugation(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=template_text,
            auxiliary=auxiliary,
        )

        success = len(forms) > 1  # More than just infinitive
        if success:
            logger.info(f"Successfully extracted {len(forms)} conjugation forms for '{word}'")
        else:
            logger.warning(f"No conjugation forms extracted for '{word}'")

        return result, success

    def _parse_verb_table(self, html: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Parse a French verb conjugation HTML table."""
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

        # Also look for participles
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

        # Try to detect tense from headers
        current_tense = "present"
        tense_columns: Dict[int, str] = {}

        for row in rows:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue

            # Check if this is a header row indicating tense
            header_text = cells[0].get_text(strip=True).lower()
            for tense_name, tense_code in self.TENSE_MAP.items():
                if tense_name in header_text:
                    current_tense = tense_code
                    # Check for column headers
                    for i, cell in enumerate(cells[1:], start=1):
                        cell_text = cell.get_text(strip=True).lower()
                        for t_name, t_code in self.TENSE_MAP.items():
                            if t_name in cell_text:
                                tense_columns[i] = t_code
                    break

            # Check if first cell contains person
            person = None
            for pattern, person_code in self.PERSON_MAP.items():
                if pattern.lower() in header_text:
                    person = person_code
                    break

            if person:
                # Extract forms from subsequent cells
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

    def _extract_participles(self, soup: BeautifulSoup, forms: Dict[str, str]) -> None:
        """Extract participle forms from the page.

        Past participle form names align with GrammaticalForm enum (pc_m, pc_f).
        """
        text = soup.get_text()

        # Past participle - masculine form (for passé composé)
        past_part_patterns = [
            r"past participle[:\s]+(\w+)",
            r"participe passé[:\s]+(\w+)",
        ]
        for pattern in past_part_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                pp = match.group(1)
                forms["pc_m"] = pp  # Masculine past participle
                # Generate feminine form (typically +e)
                if not pp.endswith("e"):
                    forms["pc_f"] = pp + "e"
                else:
                    forms["pc_f"] = pp
                break

    def _detect_auxiliary(self, wikitext: str) -> Optional[str]:
        """Detect auxiliary verb (avoir or être)."""
        if re.search(r"\bêtre\b.*auxiliary", wikitext, re.IGNORECASE):
            return "être"
        if re.search(r"\bavoir\b.*auxiliary", wikitext, re.IGNORECASE):
            return "avoir"
        if re.search(r"aux=être", wikitext):
            return "être"
        if re.search(r"aux=avoir", wikitext):
            return "avoir"
        return None

    def get_adjective_declensions(self, word: str) -> Tuple[AdjectiveDeclension, bool]:
        """
        Get agreement forms for a French adjective.

        Args:
            word: French adjective in masculine singular form

        Returns:
            Tuple of (AdjectiveDeclension, success flag)
        """
        logger.info(f"Fetching adjective forms for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return AdjectiveDeclension(word=word), False

        fr_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not fr_section:
            return AdjectiveDeclension(word=word), False

        templates = self.client.find_templates(fr_section, self.ADJECTIVE_TEMPLATE_PATTERNS)

        forms: Dict[str, str] = {"singular_m": word}
        alternatives: Dict[str, List[str]] = {}
        raw_template: Optional[str] = None

        if templates:
            template_name, template_text = templates[0]
            raw_template = template_text
            logger.debug(f"Found template: {template_name}")

            # Extract forms from template
            self._extract_adjective_forms_from_template(template_text, word, forms)

        # If forms not found from template, try HTML parsing
        if len(forms) <= 2:
            html = self.client.parse_to_html(fr_section)
            if html:
                parsed_forms, parsed_alts = self._parse_adjective_table(html)
                forms.update(parsed_forms)
                alternatives.update(parsed_alts)

        # Generate regular forms if not found
        self._generate_regular_adjective_forms(word, forms)

        result = AdjectiveDeclension(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=raw_template,
        )

        success = len(forms) > 2  # More than just ms and positive
        if success:
            logger.info(f"Successfully extracted {len(forms)} adjective forms for '{word}'")
        else:
            logger.warning(f"Limited adjective forms extracted for '{word}'")

        return result, success

    def _extract_adjective_forms_from_template(
        self, template: str, word: str, forms: Dict[str, str]
    ) -> None:
        """Extract adjective forms from template parameters.

        Form names align with GrammaticalForm enum (singular_m, singular_f, etc.)
        """
        # Look for feminine singular
        fs_match = re.search(r"\|f(?:eminine)?(?:_?s(?:ing)?)?=([^|}]+)", template)
        if fs_match:
            forms["singular_f"] = fs_match.group(1).strip()

        # Look for masculine plural
        mp_match = re.search(r"\|m(?:asc)?(?:_?p(?:l)?)?=([^|}]+)", template)
        if mp_match:
            forms["plural_m"] = mp_match.group(1).strip()

        # Look for feminine plural
        fp_match = re.search(r"\|f(?:em)?(?:_?p(?:l)?)?=([^|}]+)", template)
        if fp_match:
            forms["plural_f"] = fp_match.group(1).strip()

    def _parse_adjective_table(self, html: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Parse an adjective HTML table."""
        soup = BeautifulSoup(html, "html.parser")
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        table = soup.find("table", class_="inflection-table")
        if not table or not isinstance(table, Tag):
            return forms, alternatives

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            header = cells[0].get_text(strip=True).lower()

            # Map header to form keys (aligned with GrammaticalForm enum)
            if "masculin" in header and "singul" in header:
                form_key = "singular_m"
            elif "féminin" in header and "singul" in header:
                form_key = "singular_f"
            elif "masculin" in header and "plur" in header:
                form_key = "plural_m"
            elif "féminin" in header and "plur" in header:
                form_key = "plural_f"
            else:
                continue

            form_text = cells[1].get_text(strip=True)
            cleaned = clean_form(form_text)
            if cleaned:
                forms[form_key] = extract_primary_form(cleaned)
                if len(cleaned) > 1:
                    alternatives[form_key] = cleaned[1:]

        return forms, alternatives

    def _generate_regular_adjective_forms(self, word: str, forms: Dict[str, str]) -> None:
        """Generate regular French adjective forms if not already present.

        Form names align with GrammaticalForm enum (singular_m, singular_f, etc.)
        """
        ms = forms.get("singular_m", word)

        # Feminine singular
        if "singular_f" not in forms:
            forms["singular_f"] = self._generate_feminine(ms)

        # Masculine plural
        if "plural_m" not in forms:
            forms["plural_m"] = self._generate_plural(ms)

        # Feminine plural
        if "plural_f" not in forms:
            fs = forms.get("singular_f", self._generate_feminine(ms))
            forms["plural_f"] = self._generate_plural(fs)

    def _generate_feminine(self, word: str) -> str:
        """Generate regular feminine form of an adjective."""
        if not word:
            return word

        # Already ends in -e (usually same in feminine)
        if word.endswith("e") and not word.endswith("é"):
            return word

        # Common patterns
        if word.endswith("eux"):
            return word[:-1] + "se"
        if word.endswith("if"):
            return word[:-1] + "ve"
        if word.endswith("er"):
            return word[:-2] + "ère"
        if word.endswith("et"):
            return word[:-2] + "ète"
        if word.endswith("el"):
            return word + "le"
        if word.endswith("en"):
            return word + "ne"
        if word.endswith("on"):
            return word + "ne"

        # Default: add -e
        return word + "e"

    def _generate_plural(self, word: str) -> str:
        """Generate regular plural form."""
        if not word:
            return word

        if word.endswith(("s", "x", "z")):
            return word
        if word.endswith(("au", "eau", "eu")):
            return word + "x"

        return word + "s"

    def get_adverb_forms(self, word: str) -> Tuple[AdverbForms, bool]:
        """
        Get comparative forms for a French adverb.

        Args:
            word: French adverb in positive form

        Returns:
            Tuple of (AdverbForms, success flag)
        """
        logger.info(f"Fetching adverb forms for '{word}'")

        forms: Dict[str, str] = {"positive": word}
        alternatives: Dict[str, List[str]] = {}
        raw_template: Optional[str] = None

        wikitext = self.client.fetch_page_wikitext(word)
        if wikitext:
            fr_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
            if fr_section:
                templates = self.client.find_templates(fr_section, self.ADVERB_TEMPLATE_PATTERNS)
                if templates:
                    template_name, template_text = templates[0]
                    raw_template = template_text

                # Extract comparative forms
                self._extract_adverb_comparison(fr_section, forms)

        result = AdverbForms(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=raw_template,
        )

        logger.info(f"Successfully extracted {len(forms)} adverb forms for '{word}'")
        return result, True

    def _extract_adverb_comparison(self, wikitext: str, forms: Dict[str, str]) -> None:
        """Extract comparative and superlative forms from wikitext."""
        # French adverbs typically use "plus X" for comparative
        # and "le plus X" for superlative, but some have irregular forms
        comp_patterns = [
            r"comparative[:\s]+(\w+)",
            r"comparatif[:\s]+(\w+)",
        ]
        for pattern in comp_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match and "comparative" not in forms:
                forms["comparative"] = match.group(1)
                break

        sup_patterns = [
            r"superlative[:\s]+(\w+)",
            r"superlatif[:\s]+(\w+)",
        ]
        for pattern in sup_patterns:
            match = re.search(pattern, wikitext, re.IGNORECASE)
            if match and "superlative" not in forms:
                forms["superlative"] = match.group(1)
                break


# Convenience functions for direct use


def get_french_noun_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get French noun forms from Wiktionary.

    Args:
        word: French noun to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = FrenchParser(debug=debug)
    result, success = parser.get_noun_declensions(word)
    return result.forms, success


def get_french_verb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get French verb conjugations from Wiktionary.

    Args:
        word: French verb (infinitive) to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = FrenchParser(debug=debug)
    result, success = parser.get_verb_conjugations(word)
    return result.forms, success


def get_french_adjective_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get French adjective forms from Wiktionary.

    Args:
        word: French adjective to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = FrenchParser(debug=debug)
    result, success = parser.get_adjective_declensions(word)
    return result.forms, success


def get_french_adverb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get French adverb forms from Wiktionary.

    Args:
        word: French adverb to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = FrenchParser(debug=debug)
    result, success = parser.get_adverb_forms(word)
    return result.forms, success
