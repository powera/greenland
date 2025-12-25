"""
Nouns One - Category Structure

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

from ..dictionary.clothing_accessory_dictionary import *
from ..dictionary.food_drink_dictionary import *

level_one_structure = {
  'Food Drink': {
    "display_name": 'Food Drink',
    "words": [N06_002, N06_001, N06_012, N06_013, N06_007, N06_003, N06_006, N06_004, N06_005, N06_015, N06_020, N06_021, N06_014, N06_018, N06_016]
  },
  'Clothing Accessory': {
    "display_name": 'Clothing Accessory',
    "words": [N09_003]
  },
}
