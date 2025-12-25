"""
Nouns Eleven - Category Structure

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

from ..dictionary.food_drink_dictionary import *

level_eleven_structure = {
  'Food Drink': {
    "display_name": 'Food Drink',
    "words": [N06_008, N06_011, N06_009, N06_022, N06_010, N06_017, N06_023, N06_019, N06_084]
  },
}
