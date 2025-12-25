"""
Nouns Nineteen - Category Structure

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

from ..dictionary.personal_name_dictionary import *

level_nineteen_structure = {
  'Personal Name': {
    "display_name": 'Personal Name',
    "words": [N29_004, N29_005, N29_006, N29_007, N29_008, N29_009, N29_012, N29_013]
  },
}
