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

from ..dictionary.building_structure_dictionary import *
from ..dictionary.clothing_accessory_dictionary import *
from ..dictionary.food_drink_dictionary import *

level_one_structure = {
  'Food Drink': {
    "display_name": 'Food Drink',
    "words": [N06_002, N06_001, N06_012, N06_013, N06_007, N06_003, N06_006, N06_004, N06_005, N06_015, N06_020, N06_021, N06_014, N06_018, N06_016]
  },
  'Clothing Accessory': {
    "display_name": 'Clothing Accessory',
    "words": [N09_003, N09_008, N09_006, N09_001, N09_005, N09_002, N09_009, N09_012, N09_007, N09_011]
  },
  'Building Structure': {
    "display_name": 'Building Structure',
    "words": [N07_001, N07_002, N07_008, N07_003, N07_009, N07_005, N07_007, N07_010, N07_006, N07_011]
  },
}
