
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
    singular_accusative: Optional[str] = None  # vilką
    plural_accusative: Optional[str] = None  # vilkus

def get_required_noun_forms(min_level: int = 1) -> Dict[str, int]:
    """
    Get dictionary of required noun forms for Lithuanian with their minimum levels.
    
    Args:
        min_level: Minimum level to include forms for
        
    Returns:
        Dictionary mapping form names to their minimum required levels
    """
    forms_with_levels = {
        "plural_nominative": 4,
        "singular_accusative": 9,
        "plural_accusative": 9
    }
    
    # Filter forms based on minimum level
    return {form: level for form, level in forms_with_levels.items() if level >= min_level}

def create_noun_forms_prompt(noun: str, required_forms: Dict[str, int], pos_subtype: str = None) -> str:
    """
    Create a prompt for generating Lithuanian noun forms based on required forms.
    
    Args:
        noun: The Lithuanian noun in nominative singular
        required_forms: Dictionary of form names to minimum levels
        pos_subtype: Optional POS subtype for context
        
    Returns:
        Formatted prompt for LLM
    """
    subtype_context = f" (subtype: {pos_subtype})" if pos_subtype else ""
    
    # Build the forms list dynamically
    forms_list = []
    form_descriptions = {
        "plural_nominative": "Plural nominative (e.g., vilkas → vilkai)",
        "singular_accusative": "Singular accusative (e.g., vilkas → vilką)", 
        "plural_accusative": "Plural accusative (e.g., vilkas → vilkus)"
    }
    
    for i, form in enumerate(required_forms.keys(), 1):
        if form in form_descriptions:
            forms_list.append(f"{i}. {form_descriptions[form]}")
    
    forms_text = "\n".join(forms_list)
    
    return f"""Generate the Lithuanian noun forms for "{noun}"{subtype_context}.

Please provide the following forms:
{forms_text}

Rules for Lithuanian noun declension:
- Most masculine nouns ending in -as form plurals with -ai (vilkas → vilkai)
- Most masculine nouns ending in -is form plurals with -iai (namas → namai, but naktis → naktys)
- Most feminine nouns ending in -a form plurals with -os (mama → mamos)
- Most feminine nouns ending in -ė form plurals with -ės (mergaitė → mergaitės)
- Accusative case typically adds -ą for masculine singular, -us for masculine plural
- Feminine accusative typically matches nominative for singular, adds -as for plural
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
            plural_nominative=forms.get('plural_nominative'),
            singular_accusative=forms.get('singular_accusative'),
            plural_accusative=forms.get('plural_accusative')
        )
    except Exception:
        return None
