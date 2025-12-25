"""
Nouns Five - Category Structure

This file contains the organizational structure mapping categories to word objects.
Each category contains a list of word objects imported from the dictionary files.

Structure:
- Each category has a "display_name" for pretty printing
- Each category has a "words" list containing the actual word objects
- Word objects are imported from their respective dictionary files

Format: "Category": {
  "display_name": "Pretty Category Name",
  "words": [word_object1, word_object2, ...]
}
"""

from ..dictionary.other_dictionary import *

level_five_structure = {
  'Other': {
    "display_name": 'Other',
    "words": [N99_001, N99_002, N99_003, N99_004, N99_005, N99_006]
  },
}
