"""
Display functions for the Lokys agent.

This module contains all display/output formatting functions for the Lokys agent,
separated from the main logic to follow the pattern established in other refactored agents.
"""


def display_lemma_validation_result(result: dict, lemma_text: str):
    """
    Display lemma form validation results.

    Args:
        result: Validation result dictionary from validate_lemma_form
        lemma_text: The lemma text being validated
    """
    print(f"\nLemma form validation:")
    print(f"  Is lemma: {result['is_lemma']}")
    print(f"  Confidence: {result['confidence']:.2f}")
    if not result['is_lemma']:
        print(f"  Suggested: {result['suggested_lemma']}")
        print(f"  Reason: {result['reason']}")


def display_definition_validation_result(result: dict, lemma_text: str, definition_text: str, dry_run: bool = False):
    """
    Display definition validation results.

    Args:
        result: Validation result dictionary from validate_definition
        lemma_text: The lemma text being validated
        definition_text: The current definition text
        dry_run: Whether this is a dry run

    Returns:
        Tuple of (applied_fix: bool, new_definition: str or None)
    """
    print(f"\nDefinition validation:")
    print(f"  Is valid: {result['is_valid']}")
    print(f"  Confidence: {result['confidence']:.2f}")

    if not result['is_valid']:
        print(f"  Issues: {', '.join(result['issues'])}")
        if result['suggested_definition']:
            print(f"  Suggested: {result['suggested_definition']}")
            if dry_run:
                print(f"  [DRY RUN] Would update: '{definition_text}' → '{result['suggested_definition']}'")
                return False, None
            else:
                return True, result['suggested_definition']
        else:
            print(f"  ⚠ No suggested definition provided by LLM")
            return False, None

    return False, None


def display_disambiguation_validation_result(result: dict, lemma_text: str):
    """
    Display disambiguation validation results.

    Args:
        result: Validation result dictionary from check_single_disambiguation
        lemma_text: The lemma text being validated
    """
    print(f"\nDisambiguation validation:")
    print(f"  Needs disambiguation: {result['needs_disambiguation']}")
    if not result["needs_disambiguation"]:
        print(f"  Reason: {result.get('reason', 'n/a')}")
        return

    if result.get("has_parenthetical"):
        print(f"  Already disambiguated: {lemma_text}")
        return

    suggestions = result.get("llm_suggestions", {})
    suggested = suggestions.get("suggested_disambiguation")
    confidence = suggestions.get("confidence")
    if suggested:
        print(f"  Suggested: {lemma_text} ({suggested})")
    if confidence is not None:
        print(f"  Confidence: {confidence:.2f}")


def display_single_lemma_header(lemma, guid: str):
    """
    Display header for single lemma validation.

    Args:
        lemma: Lemma object being validated
        guid: GUID of the lemma
    """
    print(f"\nValidating lemma: {lemma.lemma_text} (GUID: {guid})")


def display_fix_applied(old_value: str, new_value: str):
    """
    Display message when a fix is applied.

    Args:
        old_value: Original value
        new_value: New value
    """
    print(f"  ✓ Updated definition: '{old_value}' → '{new_value}'")
