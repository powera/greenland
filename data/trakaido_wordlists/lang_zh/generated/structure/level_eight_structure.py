"""
Nouns Eight - Category Structure

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
from ..dictionary.plant_dictionary import *

level_eight_structure = {
  'Clothing Accessory': {
    "display_name": 'Clothing Accessory',
    "words": [N09_013, N09_014, N09_015, N09_016, N09_017]
  },
  'Plant': {
    "display_name": 'Plant',
    "words": [N05_007, N05_008]
  },
  'Building Structure': {
    "display_name": 'Building Structure',
    "words": [N07_012, N07_013, N07_014, N07_015, N07_016, N07_017, N07_026, N07_028, N07_030]
  },
}
