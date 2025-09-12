
#!/usr/bin/env python3
"""
Lithuanian noun forms generation and management.

This module handles the generation of Lithuanian noun declensions,
focusing on nominative plural forms for the wireword export system.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class LithuanianNounForms:
    """Structure for Lithuanian noun forms."""
    singular_nominative: str  # Base form (vilkas)
    plural_nominative: Optional[str] = None  # vilkai
    # Future: add other declensions as needed

def get_required_noun_forms() -> List[str]:
    """
    Get list of required noun forms for Lithuanian.
    Currently only returns plural nominative, but designed to be extensible.
    
    Returns:
        List of form names needed
    """
    return [
        "plural_nominative"  # Start with just this form
        # Future additions:
        # "singular_genitive", "singular_dative", etc.
    ]

def create_noun_forms_prompt(noun: str, pos_subtype: str = None) -> str:
    """
    Create a prompt for generating Lithuanian noun forms.
    
    Args:
        noun: The Lithuanian noun in nominative singular
        pos_subtype: Optional POS subtype for context
        
    Returns:
        Formatted prompt for LLM
    """
    subtype_context = f" (subtype: {pos_subtype})" if pos_subtype else ""
    
    return f"""Generate the Lithuanian noun forms for "{noun}"{subtype_context}.

Please provide the following forms:
1. Plural nominative (e.g., vilkas → vilkai)

Rules for Lithuanian noun declension:
- Most masculine nouns ending in -as form plurals with -ai (vilkas → vilkai)
- Most masculine nouns ending in -is form plurals with -iai (namas → namai, but naktis → naktys)
- Most feminine nouns ending in -a form plurals with -os (mama → mamos)
- Most feminine nouns ending in -ė form plurals with -ės (mergaitė → mergaitės)
- Some nouns are irregular and need special handling

Consider the gender, ending, and any irregular patterns for this specific noun."""

def parse_noun_forms_response(response_data: Dict) -> Optional[LithuanianNounForms]:
    """
    Parse LLM response into noun forms structure.
    
    Args:
        response_data: Structured response from LLM
        
    Returns:
        LithuanianNounForms object or None if parsing fails
    """
    try:
        if not isinstance(response_data, dict):
            return None
            
        forms = response_data.get('forms', {})
        if not forms:
            return None
            
        # Extract the forms we need
        return LithuanianNounForms(
            singular_nominative=forms.get('singular_nominative', ''),
            plural_nominative=forms.get('plural_nominative')
        )
    except Exception:
        return None
