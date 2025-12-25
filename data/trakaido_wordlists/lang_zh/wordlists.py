#!/usr/bin/python3

"""Wordlists for Trakaido, a language learning app for chinese."""

from typing import Dict, List, Any, Optional
from .generated.structure import level_structures

class WordListManager:
    """
    Manages word lists using the generated directory structure.
    
    This class loads per-level structure files that contain pre-compiled 
    word lists organized by level.
    """
    
    def __init__(self):
        self._level_cache: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    
    def _load_level_structure(self, level_name: str) -> Dict[str, List[Dict[str, Any]]]:
        """Load a per-level structure file and return compiled word lists."""
        if level_name in self._level_cache:
            return self._level_cache[level_name]
        
        # Convert level_1 to level_one format
        level_number = level_name.split('_')[1]
        
        # More scalable approach using a function for number-to-word conversion
        def number_to_word(n):
            """Convert number to word form for levels 1-100."""
            ones = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
                   'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
                   'seventeen', 'eighteen', 'nineteen']
            tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
            
            if n < 20:
                return ones[n]
            elif n < 100:
                return tens[n // 10] + ('' if n % 10 == 0 else '_' + ones[n % 10])
            else:
                return str(n)  # Fallback for numbers > 99
        
        try:
            level_num = int(level_number)
            level_word = number_to_word(level_num)
        except ValueError:
            self._level_cache[level_name] = {}
            return {}
        
        level_key = f"level_{level_word}"
        
        # Get the structure data from the imported level_structures
        if level_key not in level_structures:
            self._level_cache[level_name] = {}
            return {}
        
        raw_structure_data = level_structures[level_key]
        
        # Convert the structure format to compiled word lists
        # Format: {"Category": {"display_name": "...", "words": [word_objects]}}
        compiled_level = {}
        for category_name, category_data in raw_structure_data.items():
            if isinstance(category_data, dict) and 'words' in category_data:
                # Convert word objects to dictionaries
                word_list = []
                for word_obj in category_data['words']:
                    if hasattr(word_obj, '__dict__'):
                        # Convert object to dictionary
                        word_dict = word_obj.__dict__.copy()
                        word_list.append(word_dict)
                    elif isinstance(word_obj, dict):
                        word_list.append(word_obj)
                compiled_level[category_name] = word_list
        
        self._level_cache[level_name] = compiled_level
        return compiled_level
    
    def get_level(self, level_name: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get compiled word lists for a specific level."""
        return self._load_level_structure(level_name)

# Create global instance
_word_manager = WordListManager()

# Load from generated per-level structure for nouns
def _get_generated_levels():
    """Get word lists from generated per-level structure."""
    generated_levels = {}
    for level_num in range(1, 21):  # levels 1-20
        level_name = f"level_{level_num}"
        generated_levels[level_name] = _word_manager.get_level(level_name)
    return generated_levels

# Load generated levels
_generated_levels = _get_generated_levels()

# Create all_words structure with per-level nouns and legacy verbs/phrases
all_words = {}

# Add per-level noun data
for level_name, level_data in _generated_levels.items():
    all_words[level_name] = level_data

# Utility functions for backward compatibility
def get_all_word_pairs_flat():
    """
    Get all word pairs from all corpora as a flat list.
    
    Returns:
        list: A list of dictionaries, each containing:
            - english: English word
            - chinese: chinese word
            - corpus: Name of the corpus
            - group: Name of the group within the corpus
            - metadata: Metadata dictionary (if available)
            - guid: Unique identifier for the word entry
    """
    flat_words = []
    
    for corpus_name, corpus_data in all_words.items():
        if isinstance(corpus_data, dict):
            for group_name, word_list in corpus_data.items():
                if isinstance(word_list, list):
                    for word_entry in word_list:
                        if isinstance(word_entry, dict):
                            flat_word = {
                                'english': word_entry.get('english', ''),
                                'chinese': word_entry.get('chinese', ''),
                                'alternatives': word_entry.get('alternatives', {'english': [], 'chinese': []}),
                                'corpus': corpus_name,
                                'group': group_name,
                                'metadata': word_entry.get('metadata', {}),
                                'guid': word_entry.get('guid', '')
                            }
                            # Add person field for verbs
                            if corpus_name.startswith('verbs_') and 'person' in word_entry:
                                flat_word['person'] = word_entry['person']
                            flat_words.append(flat_word)
    
    return flat_words

def get_all_word_pairs_flat_basic():
    """
    Creates a flat list of all word pairs from all corpora with only basic fields.
    
    This function provides backward compatibility for existing API endpoints
    that expect only the basic english/chinese format.
    
    Returns:
        list: A list of dictionaries, each containing only 'english', 'chinese', 
              'corpus', and 'group' keys.
    """
    flat_words = []
    
    # Iterate through all corpora
    for corpus_name, corpus_data in all_words.items():
        # Iterate through all groups
        for group_name, word_pairs in corpus_data.items():
            # Add each word pair to the flat list with corpus information
            for word_pair in word_pairs:
                # Extract only basic fields for backward compatibility
                flat_word = {
                    'english': word_pair['english'],
                    'chinese': word_pair['chinese'],
                    'corpus': corpus_name,
                    'group': group_name
                }
                flat_words.append(flat_word)
    
    return flat_words

def get_words_by_corpus_basic(corpus_name, group_name=None):
    """
    Get words for a specific corpus and optional group with only basic fields.
    
    This function provides backward compatibility for existing API endpoints
    that expect only the basic english/chinese format.
    
    Args:
        corpus_name: The corpus name
        group_name: Optional group name
    
    Returns:
        list: A list of dictionaries with only basic fields
    """
    if corpus_name not in all_words:
        return []
    
    if group_name:
        if group_name not in all_words[corpus_name]:
            return []
        # Return only basic fields for the specific group
        return [
            {
                'english': word_pair['english'],
                'chinese': word_pair['chinese']
            }
            for word_pair in all_words[corpus_name][group_name]
        ]
    
    # If no group specified, return all words from all groups in this corpus
    result = []
    for grp, words in all_words[corpus_name].items():
        for word_pair in words:
            result.append({
                'english': word_pair['english'],
                'chinese': word_pair['chinese']
            })
    return result

def get_words_by_level_enhanced(level_name):
    """
    Get all words for a specific level with full enhanced format.
    
    Args:
        level_name: The level name (e.g., "level_1")
    
    Returns:
        list: List of word objects with all enhanced fields including GUID
    """
    level_words = []
    
    # Check if this is a noun level (has per-level data)
    if level_name in all_words:
        # Add noun words from per-level structure
        for group_name, word_list in all_words[level_name].items():
            for word_pair in word_list:
                enhanced_word = word_pair.copy()
                enhanced_word['corpus'] = level_name
                enhanced_word['group'] = group_name
                level_words.append(enhanced_word)
    
    return level_words

