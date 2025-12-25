"""
Nouns Sixteen - Category Structure

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

from ..dictionary.building_structure_dictionary import *

level_sixteen_structure = {
  'Building Structure': {
    "display_name": 'Building Structure',
    "words": [N07_031, N07_032, N07_033, N07_034, N07_035, N07_036, N07_037, N07_038, N07_039, N07_040, N07_041]
  },
}
