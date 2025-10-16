#!/usr/bin/env python3
"""
Wiktionary-based Lithuanian noun declension lookup.

This module fetches Lithuanian noun declensions from English Wiktionary
(en.wiktionary.org) by parsing the wikitext templates and extracting
declension table data.
"""

import logging
import requests
from typing import Dict, Optional, List, Tuple
import re
from bs4 import BeautifulSoup
import unicodedata

logger = logging.getLogger(__name__)

# Wiktionary API endpoint
WIKTIONARY_API_URL = "https://en.wiktionary.org/w/api.php"

# User-Agent header required by Wikimedia APIs
# See: https://meta.wikimedia.org/wiki/User-Agent_policy
HEADERS = {
    "User-Agent": "LithuanianDeclensionBot/1.0 (Educational/Research; Python requests)"
}

# Case names mapping from Wiktionary templates to our internal format
CASE_MAPPING = {
    "nom_s": "nominative_singular",
    "gen_s": "genitive_singular",
    "dat_s": "dative_singular",
    "acc_s": "accusative_singular",
    "ins_s": "instrumental_singular",
    "loc_s": "locative_singular",
    "voc_s": "vocative_singular",
    "nom_p": "nominative_plural",
    "gen_p": "genitive_plural",
    "dat_p": "dative_plural",
    "acc_p": "accusative_plural",
    "ins_p": "instrumental_plural",
    "loc_p": "locative_plural",
    "voc_p": "vocative_plural",
}


def remove_stress_marks(text: str) -> str:
    """
    Remove stress/accent marks from Lithuanian text while preserving Lithuanian letters.

    Lithuanian has distinct letters with diacritics (ą, č, ė, ę, į, š, ū, ų, ž)
    that must be preserved. However, stress marks (acute ´, grave `, tilde ~)
    that can appear on ANY vowel for pronunciation are removed.

    Complex case: stress marks can appear on top of Lithuanian letters (e.g., ų̃)
    In this case, we need to preserve the Lithuanian letter (ų) but remove the stress (tilde).

    Args:
        text: Text with stress marks

    Returns:
        Text without stress marks but with Lithuanian letters preserved
    """
    # Lithuanian alphabet letters with diacritics that should be PRESERVED
    # These are precomposed characters in Unicode
    lithuanian_letters = set('ąčėęįšūųž' + 'ĄČĖĘĮŠŪŲŽ')

    # Stress/tone combining marks that should be REMOVED
    # U+0300: COMBINING GRAVE ACCENT (grave: ò)
    # U+0301: COMBINING ACUTE ACCENT (acute: ó)
    # U+0303: COMBINING TILDE (tilde: õ)
    # Note: U+0307 (COMBINING DOT ABOVE) has dual purpose:
    #       - On 'e' or 'E': forms Lithuanian ė/Ė (must be preserved)
    #       - On other vowels: stress/accent mark (must be removed)
    # Note: U+030C (COMBINING CARON) is NOT a stress mark - it's part of č, š, ž
    # Note: U+0304 (COMBINING MACRON) is NOT a stress mark - it's part of ū
    # Note: U+0328 (COMBINING OGONEK) is NOT a stress mark - it's part of ą, ę, į, ų
    stress_marks = {'\u0300', '\u0301', '\u0303'}  # U+0307 handled specially below

    # Decompose unicode characters into base + combining marks
    # NFD = Canonical Decomposition
    decomposed = unicodedata.normalize('NFD', text)

    # Build result by filtering combining marks
    result = []
    i = 0
    while i < len(decomposed):
        char = decomposed[i]

        # Check if this is a base character
        if unicodedata.category(char) != 'Mn':
            # It's a base character, check what follows
            base = char
            combining_marks = []

            # Collect any combining marks that follow
            j = i + 1
            while j < len(decomposed) and unicodedata.category(decomposed[j]) == 'Mn':
                combining_marks.append(decomposed[j])
                j += 1

            # Separate stress marks from other combining marks
            # Special handling for U+0307 (dot above):
            # - Keep it if base is 'e' or 'E' (Lithuanian ė/Ė)
            # - Remove it on other letters (stress mark)
            non_stress_marks = []
            for m in combining_marks:
                if m in stress_marks:
                    # Always remove these stress marks
                    continue
                elif m == '\u0307':
                    # Dot above: keep only if base is 'e' or 'E'
                    if base.lower() == 'e':
                        non_stress_marks.append(m)
                    # Otherwise skip (it's a stress mark)
                else:
                    # Keep other combining marks (Lithuanian letter components)
                    non_stress_marks.append(m)

            # Reconstruct with only non-stress marks
            reconstructed = unicodedata.normalize('NFC', base + ''.join(non_stress_marks))

            # Add to result
            result.append(reconstructed)

            # Skip past the combining marks we processed
            i = j
        else:
            # Orphan combining mark - skip it if it's a stress mark, otherwise keep
            if char not in stress_marks and char != '\u0307':
                result.append(char)
            i += 1

    return ''.join(result)


def clean_declension_form(text: str) -> List[str]:
    """
    Clean a declension form by removing stress marks and handling alternatives.

    Args:
        text: Raw form text (may contain stress marks, slashes for alternatives, etc.)

    Returns:
        List of cleaned forms (multiple if there are alternatives separated by /)
    """
    if not text or text in ('—', '-', ''):
        return []

    # Split by slash to handle alternative forms
    forms = [f.strip() for f in text.split('/')]

    # Remove stress marks from each form
    cleaned_forms = [remove_stress_marks(form) for form in forms]

    # Filter out empty strings
    cleaned_forms = [f for f in cleaned_forms if f]

    return cleaned_forms


def fetch_wiktionary_page(word: str, language_code: str = "lt") -> Optional[str]:
    """
    Fetch the wikitext content for a word from Wiktionary.

    Args:
        word: The word to look up
        language_code: Language code (default: "lt" for Lithuanian)

    Returns:
        Raw wikitext content or None if not found
    """
    params = {
        "action": "query",
        "format": "json",
        "titles": word,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
    }

    try:
        response = requests.get(WIKTIONARY_API_URL, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Extract page content
        pages = data.get("query", {}).get("pages", {})
        for page_id, page_data in pages.items():
            if page_id == "-1":
                logger.warning(f"Word '{word}' not found in Wiktionary")
                return None

            revisions = page_data.get("revisions", [])
            if revisions:
                content = revisions[0].get("slots", {}).get("main", {}).get("*", "")
                return content

        return None

    except requests.RequestException as e:
        logger.error(f"Error fetching Wiktionary page for '{word}': {e}")
        return None


def extract_lithuanian_section(wikitext: str) -> Optional[str]:
    """
    Extract the Lithuanian language section from Wiktionary wikitext.

    Args:
        wikitext: Full wikitext content

    Returns:
        Lithuanian section text or None if not found
    """
    # Find the start of the Lithuanian section (with optional spaces around heading)
    # Pattern: ==<spaces>Lithuanian<spaces>==
    lt_heading_match = re.search(r'==\s*Lithuanian\s*==', wikitext)
    if not lt_heading_match:
        logger.warning("No Lithuanian section found in wikitext")
        return None

    start = lt_heading_match.start()

    # Find the next language section (next level-2 heading)
    # Look for pattern like \n==<spaces>AnyText<spaces>==
    rest = wikitext[lt_heading_match.end():]
    next_section_match = re.search(r'\n==\s*[A-Z][a-zA-Z\s]+\s*==', rest)

    if next_section_match:
        end = lt_heading_match.end() + next_section_match.start()
        return wikitext[start:end]
    else:
        # Lithuanian section goes to end of document
        return wikitext[start:]


def extract_declension_template(lithuanian_section: str) -> Optional[str]:
    """
    Extract the Lithuanian declension template from the Lithuanian section.

    Common templates include:
    - {{lt-decl-noun}} - generic declension template
    - {{lt-noun-m-as-2|...}} - masculine, -as ending, declension 2
    - {{lt-noun-f-dė-3|...}} - feminine, -dė ending, declension 3
    - {{lt-noun-f-tė|...}} - feminine, -tė ending
    - And many other variations with gender (m/f), endings, and numbers

    Args:
        lithuanian_section: Lithuanian language section text

    Returns:
        Template text or None if not found
    """
    # Look for declension templates
    # Match any template starting with lt-noun or lt-decl or lt-ndecl
    # The pattern matches {{lt-noun followed by any characters until }}
    patterns = [
        r'\{\{lt-noun-[^}]*\}\}',  # Matches all lt-noun-* variants
        r'\{\{lt-decl-noun[^}]*\}\}',  # Generic declension template
        r'\{\{lt-ndecl[^}]*\}\}',  # Alternative template name
    ]

    for pattern in patterns:
        match = re.search(pattern, lithuanian_section)
        if match:
            return match.group(0)

    logger.warning("No declension template found in Lithuanian section")
    return None


def parse_declension_template(template: str) -> Dict[str, str]:
    """
    Parse a Lithuanian declension template to extract forms.

    This is a basic parser that handles common template formats.
    For full accuracy, we would need to use the MediaWiki parser API
    or expand templates, but this gives us a starting point.

    Args:
        template: Template text (e.g., "{{lt-decl-noun|vil|kas}}")

    Returns:
        Dictionary mapping our case names to forms
    """
    # For now, return empty dict - we'll need to call the parse API
    # to properly resolve templates
    logger.info(f"Found template: {template}")
    return {}


def expand_wikitext_template(wikitext: str) -> Optional[str]:
    """
    Expand wikitext templates using the Wiktionary API.

    This uses the expandtemplates API to get the rendered wikitext,
    which resolves all template calls.

    Args:
        wikitext: Raw wikitext containing templates

    Returns:
        Expanded wikitext or None if expansion fails
    """
    params = {
        "action": "expandtemplates",
        "format": "json",
        "text": wikitext,
        "prop": "wikitext",
    }

    try:
        response = requests.get(WIKTIONARY_API_URL, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            logger.warning(f"Error expanding templates: {data['error']}")
            return None

        expanded = data.get("expandtemplates", {}).get("wikitext", "")
        return expanded

    except requests.RequestException as e:
        logger.error(f"Error expanding templates: {e}")
        return None


def parse_wikitext_to_html(wikitext: str) -> Optional[str]:
    """
    Parse wikitext to HTML using the Wiktionary API.

    This uses the parse API to convert wikitext (including templates)
    into rendered HTML.

    Args:
        wikitext: Raw wikitext to parse

    Returns:
        Parsed HTML content or None if parsing fails
    """
    params = {
        "action": "parse",
        "format": "json",
        "text": wikitext,
        "prop": "text",
        "contentmodel": "wikitext",
    }

    try:
        response = requests.get(WIKTIONARY_API_URL, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            logger.warning(f"Error parsing wikitext: {data['error']}")
            return None

        html = data.get("parse", {}).get("text", {}).get("*", "")
        return html

    except requests.RequestException as e:
        logger.error(f"Error parsing wikitext: {e}")
        return None


def extract_declension_from_html(html: str) -> Dict[str, str]:
    """
    Extract declension forms from parsed HTML table.

    Lithuanian declension tables typically have a specific structure with
    headers for cases and columns for singular/plural.

    Args:
        html: Parsed HTML content

    Returns:
        Dictionary mapping case names to forms
    """
    soup = BeautifulSoup(html, 'html.parser')

    # Find the declension table - it typically has class "inflection-table"
    table = soup.find('table', class_='inflection-table')
    if not table:
        logger.warning("No inflection table found in HTML")
        return {}

    declensions = {}

    # The table structure varies:
    # Regular words:
    #   Row 1: Headers (blank, Singular, Plural)
    #   Row 2+: Case name, singular form, plural form
    # Plurale tantum (plural-only):
    #   Row 1+: Case name, plural form (no header row, no singular column)
    # Singulare tantum (singular-only):
    #   Row 1+: Case name, singular form (no header row, no plural column)
    rows = table.find_all('tr')

    # Detect table structure by checking first row
    # If first row contains "singular" or "plural" in header cells, skip it
    # Otherwise, start processing from first row
    start_row = 0
    if rows:
        first_row_cells = rows[0].find_all(['th', 'td'])
        first_row_text = ' '.join(cell.get_text(strip=True).lower() for cell in first_row_cells)
        if 'singular' in first_row_text or 'plural' in first_row_text:
            start_row = 1  # Skip header row

    # Map Lithuanian case names to our internal format
    case_name_map = {
        'nominative': 'nominative',
        'genitive': 'genitive',
        'dative': 'dative',
        'accusative': 'accusative',
        'instrumental': 'instrumental',
        'locative': 'locative',
        'vocative': 'vocative',
    }

    for row in rows[start_row:]:
        cells = row.find_all(['th', 'td'])
        if len(cells) < 2:
            continue

        # First cell is the case name
        case_name_cell = cells[0].get_text(strip=True).lower()

        # Try to match against known case names
        matched_case = None
        for known_case, internal_name in case_name_map.items():
            if known_case in case_name_cell:
                matched_case = internal_name
                break

        if not matched_case:
            continue

        # Handle both regular and plurale tantum (plural-only) tables
        # Regular tables have 3 columns: case | singular | plural
        # Plurale tantum tables have 2 columns: case | plural
        if len(cells) == 3:
            # Regular table with singular and plural forms
            # Second cell is singular form
            singular_form = cells[1].get_text(strip=True)
            cleaned_singular = clean_declension_form(singular_form)
            if cleaned_singular:
                # If there are multiple forms, join them with "/" for now
                # (or we could store just the first one as primary)
                declensions[f"{matched_case}_singular"] = cleaned_singular[0]
                # Store alternatives if present
                if len(cleaned_singular) > 1:
                    declensions[f"{matched_case}_singular_alt"] = cleaned_singular[1:]

            # Third cell is plural form
            plural_form = cells[2].get_text(strip=True)
            cleaned_plural = clean_declension_form(plural_form)
            if cleaned_plural:
                # If there are multiple forms, join them with "/" for now
                declensions[f"{matched_case}_plural"] = cleaned_plural[0]
                # Store alternatives if present
                if len(cleaned_plural) > 1:
                    declensions[f"{matched_case}_plural_alt"] = cleaned_plural[1:]

        elif len(cells) == 2:
            # Plurale tantum (plural-only) table
            # Second cell is the plural form (no singular exists)
            plural_form = cells[1].get_text(strip=True)
            cleaned_plural = clean_declension_form(plural_form)
            if cleaned_plural:
                declensions[f"{matched_case}_plural"] = cleaned_plural[0]
                # Store alternatives if present
                if len(cleaned_plural) > 1:
                    declensions[f"{matched_case}_plural_alt"] = cleaned_plural[1:]

    logger.info(f"Extracted {len(declensions)} declension forms from HTML table")
    return declensions


def get_lithuanian_declensions(word: str) -> Tuple[Dict[str, str], bool]:
    """
    Get Lithuanian noun declensions for a word from Wiktionary.

    This is the main entry point that coordinates the fetch and parse operations.

    DEPRECATED: Use get_lithuanian_noun_forms() instead for unified API.

    Args:
        word: The Lithuanian word to look up

    Returns:
        Tuple of (dictionary mapping case names to forms, success flag)
    """
    logger.info(f"Fetching declensions for '{word}' from Wiktionary")

    # Step 1: Fetch the wikitext
    wikitext = fetch_wiktionary_page(word)
    if not wikitext:
        return {}, False

    # Step 2: Extract Lithuanian section
    lt_section = extract_lithuanian_section(wikitext)
    if not lt_section:
        return {}, False

    # Step 3: Find declension template
    template = extract_declension_template(lt_section)
    if not template:
        return {}, False

    # Step 4: Parse the template to HTML using MediaWiki API
    logger.info(f"Parsing template for '{word}'")
    html = parse_wikitext_to_html(template)
    if not html:
        logger.warning(f"Failed to parse template to HTML for '{word}'")
        return {}, False

    # Step 5: Extract declensions from the HTML table
    declensions = extract_declension_from_html(html)

    if declensions:
        logger.info(f"Successfully extracted {len(declensions)} forms for '{word}'")
        return declensions, True
    else:
        logger.warning(f"No declensions extracted for '{word}'")
        return {}, False


def get_lithuanian_noun_forms(word: str) -> Tuple[Dict[str, str], bool]:
    """
    Get Lithuanian noun declensions for a word from Wiktionary.

    This is the unified API entry point that matches the interface expected
    by the generate tool and client code.

    Args:
        word: The Lithuanian word to look up

    Returns:
        Tuple of (dictionary mapping case names to forms, success flag)
        Forms use keys like: nominative_singular, genitive_plural, etc.
    """
    return get_lithuanian_declensions(word)


def test_wiktionary_fetch():
    """
    Test function to verify Wiktionary API access and parsing.

    Tests with a common Lithuanian word like "šuo" (dog).
    """
    test_word = "gaisras"
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing Wiktionary declension extraction for '{test_word}'")
    logger.info(f"{'='*60}\n")

    declensions, success = get_lithuanian_declensions(test_word)

    if success:
        logger.info(f"\n✓ Successfully extracted declensions for '{test_word}':")
        logger.info(f"\nSingular forms:")
        for case in ['nominative', 'genitive', 'dative', 'accusative', 'instrumental', 'locative', 'vocative']:
            key = f"{case}_singular"
            if key in declensions:
                logger.info(f"  {case.capitalize():15} {declensions[key]}")

        logger.info(f"\nPlural forms:")
        for case in ['nominative', 'genitive', 'dative', 'accusative', 'instrumental', 'locative', 'vocative']:
            key = f"{case}_plural"
            if key in declensions:
                logger.info(f"  {case.capitalize():15} {declensions[key]}")
    else:
        logger.error(f"\n✗ Failed to extract declensions for '{test_word}'")


def test_stress_mark_removal():
    """
    Test that stress marks are removed but Lithuanian letters are preserved.
    """
    test_cases = [
        # (input, expected_output, description)
        # Basic stress mark removal on regular vowels
        ("šuõ", "šuo", "Remove tilde stress mark from o"),
        ("šuñs", "šuns", "Remove acute stress mark from u"),
        ("šùnį", "šunį", "Remove grave stress mark from u"),

        # Preserve Lithuanian letters WITHOUT stress marks
        ("svogūnas", "svogūnas", "Preserve ū (distinct Lithuanian letter)"),
        ("ąčiū", "ąčiū", "Preserve ą and ū (Lithuanian letters)"),
        ("ė", "ė", "Preserve ė (Lithuanian letter)"),
        ("ę", "ę", "Preserve ę (Lithuanian letter)"),
        ("į", "į", "Preserve į (Lithuanian letter)"),
        ("ų", "ų", "Preserve ų (Lithuanian letter)"),
        ("ū", "ū", "Preserve ū (Lithuanian letter)"),
        ("š", "š", "Preserve š (Lithuanian letter)"),
        ("ž", "ž", "Preserve ž (Lithuanian letter)"),
        ("č", "č", "Preserve č (Lithuanian letter)"),
        ("ą", "ą", "Preserve ą (Lithuanian letter)"),

        # CRITICAL: Stress marks ON TOP OF Lithuanian letters
        # These should remove the stress but keep the Lithuanian letter
        ("ų̃", "ų", "Remove tilde from ų (Lithuanian letter with stress)"),
        ("ū́", "ū", "Remove acute from ū (Lithuanian letter with stress)"),
        ("ė̃", "ė", "Remove tilde from ė (Lithuanian letter with stress)"),
        ("į̃", "į", "Remove tilde from į (Lithuanian letter with stress)"),
        ("ą̃", "ą", "Remove tilde from ą (Lithuanian letter with stress)"),
        ("ę́", "ę", "Remove acute from ę (Lithuanian letter with stress)"),
        ("š́", "š", "Remove acute from š (Lithuanian letter with stress)"),

        # Complex words with multiple types
        ("šuniù/šunimì", "šuniu/šunimi", "Remove stress marks from alternatives"),
        ("ženklų̃", "ženklų", "Remove tilde from ų in real word (keeps ų)"),
    ]

    print("\n" + "="*60)
    print("Testing stress mark removal")
    print("="*60)

    all_passed = True
    for input_text, expected, description in test_cases:
        # For the slash case, we need to test each part
        if "/" in input_text:
            parts = input_text.split("/")
            results = [remove_stress_marks(part) for part in parts]
            result = "/".join(results)
        else:
            result = remove_stress_marks(input_text)

        passed = result == expected
        all_passed = all_passed and passed

        status = "✓" if passed else "✗"
        print(f"{status} {description}")
        print(f"  Input:    '{input_text}'")
        print(f"  Expected: '{expected}'")
        print(f"  Got:      '{result}'")
        if not passed:
            print(f"  ** FAILED **")
        print()

    if all_passed:
        print("All tests passed! ✓")
    else:
        print("Some tests failed! ✗")

    return all_passed


def test_clean_declension_form():
    """
    Test the full cleaning function with alternatives.
    """
    test_cases = [
        ("šuõ", ["šuo"], "Single form with stress"),
        ("šuniù/šunimì", ["šuniu", "šunimi"], "Alternative forms with stress"),
        ("svogūnas", ["svogūnas"], "Lithuanian ū preserved"),
        ("—", [], "Em dash (no form)"),
        ("-", [], "Hyphen (no form)"),
        ("", [], "Empty string"),
    ]

    print("\n" + "="*60)
    print("Testing clean_declension_form()")
    print("="*60)

    all_passed = True
    for input_text, expected, description in test_cases:
        result = clean_declension_form(input_text)
        passed = result == expected
        all_passed = all_passed and passed

        status = "✓" if passed else "✗"
        print(f"{status} {description}")
        print(f"  Input:    '{input_text}'")
        print(f"  Expected: {expected}")
        print(f"  Got:      {result}")
        if not passed:
            print(f"  ** FAILED **")
        print()

    if all_passed:
        print("All tests passed! ✓")
    else:
        print("Some tests failed! ✗")

    return all_passed


if __name__ == "__main__":
    # Set up logging for testing
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Run unit tests first
    stress_tests_passed = test_stress_mark_removal()
    clean_tests_passed = test_clean_declension_form()

    if stress_tests_passed and clean_tests_passed:
        print("\n" + "="*60)
        print("All unit tests passed! Now testing live Wiktionary fetch...")
        print("="*60 + "\n")
        test_wiktionary_fetch()
    else:
        print("\n" + "="*60)
        print("Unit tests failed! Skipping live Wiktionary test.")
        print("="*60)
