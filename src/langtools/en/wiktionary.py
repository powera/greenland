"""English Wiktionary parsing for grammatical forms."""

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
from langtools.en.types import (
    AdjectiveDeclension,
    AdverbForms,
    NounDeclension,
    VerbConjugation,
)
from langtools.en.utils import (
    clean_form,
    generate_3s_present,
    generate_comparative,
    generate_past_tense,
    generate_present_participle,
    generate_regular_plural,
    generate_superlative,
)

logger = logging.getLogger(__name__)


class EnglishParser:
    """Parser for English grammatical forms from Wiktionary."""

    LANGUAGE = "English"
    LANGUAGE_CODE = "en"

    # Template patterns for different parts of speech
    NOUN_TEMPLATE_PATTERNS = [
        r"en-noun[^}]*",  # Main noun template
        r"en-plural noun[^}]*",  # Plurale tantum
    ]

    VERB_TEMPLATE_PATTERNS = [
        r"en-verb[^}]*",  # Main verb template
    ]

    ADJECTIVE_TEMPLATE_PATTERNS = [
        r"en-adj[^}]*",  # Adjective templates
    ]

    ADVERB_TEMPLATE_PATTERNS = [
        r"en-adv[^}]*",  # Adverb templates
    ]

    def __init__(self, client: Optional[WiktionaryClient] = None, debug: bool = False):
        """
        Initialize the English parser.

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
        Get all forms for an English noun.

        Args:
            word: English noun in singular form (lemma form)

        Returns:
            Tuple of (NounDeclension, success flag)
        """
        logger.info(f"Fetching noun forms for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return NounDeclension(word=word), False

        en_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not en_section:
            return NounDeclension(word=word), False

        templates = self.client.find_templates(en_section, self.NOUN_TEMPLATE_PATTERNS)

        forms: Dict[str, str] = {"singular": word}
        alternatives: Dict[str, List[str]] = {}
        raw_template: Optional[str] = None
        number_type = NounNumberType.REGULAR

        if templates:
            template_name, template_text = templates[0]
            raw_template = template_text
            logger.debug(f"Found template: {template_name}")

            # Check for plurale tantum
            if "plural noun" in template_name:
                number_type = NounNumberType.PLURALE_TANTUM
                forms = {"plural": word}
            else:
                # Extract plural from template
                plural, alts = self._extract_plural_from_template(template_text, word)
                if plural:
                    forms["plural"] = plural
                    if alts:
                        alternatives["plural"] = alts

        # If no plural found, generate regular plural
        if "plural" not in forms and number_type == NounNumberType.REGULAR:
            forms["plural"] = generate_regular_plural(word)

        # Check for uncountable marker
        if raw_template and ("-" in raw_template or "~" in raw_template):
            # May be uncountable, but we still store the regular plural
            pass

        result = NounDeclension(
            word=word,
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

    def _extract_plural_from_template(
        self, template_text: str, word: str
    ) -> Tuple[Optional[str], List[str]]:
        """Extract plural form from noun template."""
        alternatives: List[str] = []

        # Look for explicit plural parameter
        # {{en-noun|plurals}} or {{en-noun|pl=plurals}}
        plural_match = re.search(r"\|pl(?:ural)?=([^|}]+)", template_text)
        if plural_match:
            plural = plural_match.group(1).strip()
            if plural and plural != "-":
                cleaned = clean_form(plural)
                if cleaned:
                    return extract_primary_form(cleaned), cleaned[1:]

        # Extract positional parameters
        # {{en-noun|mice}} or {{en-noun|+|mice}}
        params = re.findall(r"\|([^|}]+)", template_text)

        for param in params:
            param = param.strip()
            if param in ("-", "~", "+", "!", "?", "s", "es"):
                continue
            if "=" in param:
                continue

            # Looks like a plural form
            cleaned = clean_form(param)
            if cleaned:
                return extract_primary_form(cleaned), cleaned[1:]

        return None, alternatives

    def get_verb_conjugations(self, word: str) -> Tuple[VerbConjugation, bool]:
        """
        Get all conjugation forms for an English verb.

        Args:
            word: English verb in base/infinitive form

        Returns:
            Tuple of (VerbConjugation, success flag)
        """
        logger.info(f"Fetching verb conjugations for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return VerbConjugation(word=word), False

        en_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not en_section:
            return VerbConjugation(word=word), False

        templates = self.client.find_templates(en_section, self.VERB_TEMPLATE_PATTERNS)

        forms: Dict[str, str] = {"infinitive": word}
        alternatives: Dict[str, List[str]] = {}
        raw_template: Optional[str] = None

        if templates:
            template_name, template_text = templates[0]
            raw_template = template_text
            logger.debug(f"Found template: {template_name}")

            # Extract forms from template
            extracted_forms, extracted_alts = self._parse_verb_template(template_text, word)
            forms.update(extracted_forms)
            alternatives.update(extracted_alts)

        # Generate missing regular forms
        if "3s_present" not in forms:
            forms["3s_present"] = generate_3s_present(word)
        if "past" not in forms:
            forms["past"] = generate_past_tense(word)
        if "past_participle" not in forms:
            forms["past_participle"] = forms.get("past", generate_past_tense(word))
        if "present_participle" not in forms:
            forms["present_participle"] = generate_present_participle(word)

        result = VerbConjugation(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=raw_template,
        )

        success = len(forms) > 1  # More than just infinitive
        if success:
            logger.info(f"Successfully extracted {len(forms)} conjugation forms for '{word}'")
        else:
            logger.warning(f"No conjugation forms extracted for '{word}'")

        return result, success

    def _parse_verb_template(
        self, template_text: str, word: str
    ) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
        """Parse verb template parameters to extract forms."""
        forms: Dict[str, str] = {}
        alternatives: Dict[str, List[str]] = {}

        # English verb template: {{en-verb|3s|past|past_part|pres_part}}
        # Or with named params: {{en-verb|past=went|past_ptc=gone}}

        # Named parameters first
        named_patterns = [
            (r"\|past(?:_tense)?=([^|}]+)", "past"),
            (r"\|past[_ ]?p(?:art)?(?:iciple)?=([^|}]+)", "past_participle"),
            (r"\|past[_ ]?ptc=([^|}]+)", "past_participle"),
            (r"\|pres[_ ]?p(?:art)?(?:iciple)?=([^|}]+)", "present_participle"),
            (r"\|pres[_ ]?ptc=([^|}]+)", "present_participle"),
            (r"\|3(?:rd)?[_ ]?s(?:ing)?(?:ular)?=([^|}]+)", "3s_present"),
        ]

        for pattern, form_key in named_patterns:
            match = re.search(pattern, template_text, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value and value not in ("-", "+"):
                    cleaned = clean_form(value)
                    if cleaned:
                        forms[form_key] = extract_primary_form(cleaned)
                        if len(cleaned) > 1:
                            alternatives[form_key] = cleaned[1:]

        # Positional parameters: {{en-verb|goes|went|gone|going}}
        # or {{en-verb|going|went|gone}} etc.
        params = re.findall(r"\|([^|}=]+)", template_text)
        positional = [p.strip() for p in params if "=" not in p and p.strip()]
        positional = [p for p in positional if p not in ("-", "+", "~", "++", "--")]

        # Try to identify forms by pattern
        for p in positional:
            cleaned = clean_form(p)
            if not cleaned:
                continue
            primary = extract_primary_form(cleaned)

            # Gerund/present participle ends in -ing
            if primary.endswith("ing") and "present_participle" not in forms:
                forms["present_participle"] = primary
                if len(cleaned) > 1:
                    alternatives["present_participle"] = cleaned[1:]
            # 3rd person singular often ends in -s, -es
            elif (
                primary.endswith(("s", "es"))
                and not primary.endswith("ss")
                and "3s_present" not in forms
            ):
                forms["3s_present"] = primary
                if len(cleaned) > 1:
                    alternatives["3s_present"] = cleaned[1:]
            # Past forms - harder to identify, try by position or -ed ending
            elif primary.endswith("ed") and "past" not in forms:
                forms["past"] = primary
                if "past_participle" not in forms:
                    forms["past_participle"] = primary
                if len(cleaned) > 1:
                    alternatives["past"] = cleaned[1:]
            elif "past" not in forms and not primary.endswith("ing"):
                forms["past"] = primary
                if len(cleaned) > 1:
                    alternatives["past"] = cleaned[1:]
            elif "past_participle" not in forms and not primary.endswith("ing"):
                forms["past_participle"] = primary
                if len(cleaned) > 1:
                    alternatives["past_participle"] = cleaned[1:]

        return forms, alternatives

    def get_adjective_declensions(self, word: str) -> Tuple[AdjectiveDeclension, bool]:
        """
        Get comparison forms for an English adjective.

        Args:
            word: English adjective in positive form

        Returns:
            Tuple of (AdjectiveDeclension, success flag)
        """
        logger.info(f"Fetching adjective forms for '{word}'")

        wikitext = self.client.fetch_page_wikitext(word)
        if not wikitext:
            return AdjectiveDeclension(word=word, forms={"positive": word}), False

        en_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
        if not en_section:
            return AdjectiveDeclension(word=word, forms={"positive": word}), False

        templates = self.client.find_templates(en_section, self.ADJECTIVE_TEMPLATE_PATTERNS)

        forms: Dict[str, str] = {"positive": word}
        alternatives: Dict[str, List[str]] = {}
        raw_template: Optional[str] = None

        if templates:
            template_name, template_text = templates[0]
            raw_template = template_text
            logger.debug(f"Found template: {template_name}")

            # Extract comparative/superlative from template
            self._extract_adjective_forms(template_text, word, forms, alternatives)

        # If not found in template, check if it's a short adjective and generate forms
        if "comparative" not in forms and "superlative" not in forms:
            # Check if this looks like a short adjective that takes -er/-est
            if self._is_short_adjective(word):
                forms["comparative"] = generate_comparative(word)
                forms["superlative"] = generate_superlative(word)
            else:
                # Long adjectives use more/most
                forms["comparative"] = f"more {word}"
                forms["superlative"] = f"most {word}"

        result = AdjectiveDeclension(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=raw_template,
        )

        success = len(forms) > 1
        if success:
            logger.info(f"Successfully extracted {len(forms)} adjective forms for '{word}'")
        else:
            logger.warning(f"No adjective forms extracted for '{word}'")

        return result, success

    def _is_short_adjective(self, word: str) -> bool:
        """Heuristic to check if adjective takes -er/-est forms."""
        if not word:
            return False

        # One syllable words usually take -er/-est
        # Two syllable words ending in -y, -le, -er, -ow often do too
        vowels = sum(1 for c in word.lower() if c in "aeiou")

        # Very rough syllable count
        if vowels <= 1:
            return True
        if vowels == 2 and word.endswith(("y", "le", "er", "ow", "ple", "ble")):
            return True

        return False

    def _extract_adjective_forms(
        self,
        template_text: str,
        word: str,
        forms: Dict[str, str],
        alternatives: Dict[str, List[str]],
    ) -> None:
        """Extract comparative and superlative from template."""
        # Named parameters
        comp_match = re.search(r"\|comp(?:arative)?=([^|}]+)", template_text)
        if comp_match:
            value = comp_match.group(1).strip()
            if value and value not in ("-", "more"):
                cleaned = clean_form(value)
                if cleaned:
                    forms["comparative"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["comparative"] = cleaned[1:]

        sup_match = re.search(r"\|sup(?:erlative)?=([^|}]+)", template_text)
        if sup_match:
            value = sup_match.group(1).strip()
            if value and value not in ("-", "most"):
                cleaned = clean_form(value)
                if cleaned:
                    forms["superlative"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["superlative"] = cleaned[1:]

        # Check for "more" marker indicating periphrastic comparison
        if re.search(r"\|more\b", template_text):
            forms["comparative"] = f"more {word}"
            forms["superlative"] = f"most {word}"
            return

        # Check for "-" marker indicating no comparison
        if re.search(r"\|-\s*\|", template_text) or template_text.endswith("|-}}"):
            # No comparison forms (absolute adjective)
            return

        # Positional parameters: {{en-adj|bigger|biggest}}
        params = re.findall(r"\|([^|}=]+)", template_text)
        positional = [p.strip() for p in params if "=" not in p and p.strip()]
        positional = [p for p in positional if p not in ("-", "+", "more", "most", "~")]

        for p in positional:
            cleaned = clean_form(p)
            if not cleaned:
                continue
            primary = extract_primary_form(cleaned)

            if primary.endswith("er") and "comparative" not in forms:
                forms["comparative"] = primary
                if len(cleaned) > 1:
                    alternatives["comparative"] = cleaned[1:]
            elif primary.endswith("est") and "superlative" not in forms:
                forms["superlative"] = primary
                if len(cleaned) > 1:
                    alternatives["superlative"] = cleaned[1:]

    def get_adverb_forms(self, word: str) -> Tuple[AdverbForms, bool]:
        """
        Get comparative forms for an English adverb.

        Args:
            word: English adverb in positive form

        Returns:
            Tuple of (AdverbForms, success flag)
        """
        logger.info(f"Fetching adverb forms for '{word}'")

        forms: Dict[str, str] = {"positive": word}
        alternatives: Dict[str, List[str]] = {}
        raw_template: Optional[str] = None

        wikitext = self.client.fetch_page_wikitext(word)
        if wikitext:
            en_section = self.client.extract_language_section(wikitext, self.LANGUAGE)
            if en_section:
                templates = self.client.find_templates(en_section, self.ADVERB_TEMPLATE_PATTERNS)
                if templates:
                    template_name, template_text = templates[0]
                    raw_template = template_text
                    logger.debug(f"Found adverb template: {template_name}")

                    # Extract comparative forms
                    self._extract_adverb_forms(template_text, word, forms, alternatives)

        # If no forms found from template, try to generate
        if "comparative" not in forms and "superlative" not in forms:
            # Short adverbs (fast, hard, etc.) take -er/-est
            # Adverbs ending in -ly use more/most
            if word.endswith("ly"):
                forms["comparative"] = f"more {word}"
                forms["superlative"] = f"most {word}"
            else:
                forms["comparative"] = generate_comparative(word)
                forms["superlative"] = generate_superlative(word)

        result = AdverbForms(
            word=word,
            forms=forms,
            alternatives=alternatives,
            raw_template=raw_template,
        )

        logger.info(f"Successfully extracted {len(forms)} adverb forms for '{word}'")
        return result, True

    def _extract_adverb_forms(
        self,
        template_text: str,
        word: str,
        forms: Dict[str, str],
        alternatives: Dict[str, List[str]],
    ) -> None:
        """Extract comparative and superlative from adverb template."""
        # Same logic as adjective
        comp_match = re.search(r"\|comp(?:arative)?=([^|}]+)", template_text)
        if comp_match:
            value = comp_match.group(1).strip()
            if value and value not in ("-", "more"):
                cleaned = clean_form(value)
                if cleaned:
                    forms["comparative"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["comparative"] = cleaned[1:]

        sup_match = re.search(r"\|sup(?:erlative)?=([^|}]+)", template_text)
        if sup_match:
            value = sup_match.group(1).strip()
            if value and value not in ("-", "most"):
                cleaned = clean_form(value)
                if cleaned:
                    forms["superlative"] = extract_primary_form(cleaned)
                    if len(cleaned) > 1:
                        alternatives["superlative"] = cleaned[1:]

        # Check for "more" marker
        if re.search(r"\|more\b", template_text):
            forms["comparative"] = f"more {word}"
            forms["superlative"] = f"most {word}"


# Convenience functions for direct use


def get_english_noun_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get English noun forms from Wiktionary.

    Args:
        word: English noun to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = EnglishParser(debug=debug)
    result, success = parser.get_noun_declensions(word)
    return result.forms, success


def get_english_verb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get English verb conjugations from Wiktionary.

    Args:
        word: English verb (base form) to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = EnglishParser(debug=debug)
    result, success = parser.get_verb_conjugations(word)
    return result.forms, success


def get_english_adjective_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get English adjective forms from Wiktionary.

    Args:
        word: English adjective to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = EnglishParser(debug=debug)
    result, success = parser.get_adjective_declensions(word)
    return result.forms, success


def get_english_adverb_forms(word: str, debug: bool = False) -> Tuple[Dict[str, str], bool]:
    """
    Get English adverb forms from Wiktionary.

    Args:
        word: English adverb to look up
        debug: Enable debug logging

    Returns:
        Tuple of (forms dict, success flag)
    """
    parser = EnglishParser(debug=debug)
    result, success = parser.get_adverb_forms(word)
    return result.forms, success
