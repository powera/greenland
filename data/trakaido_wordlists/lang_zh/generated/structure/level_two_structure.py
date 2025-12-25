"""
Nouns Two - Category Structure

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

from ..dictionary.animal_dictionary import *
from ..dictionary.small_movable_object_dictionary import *

level_two_structure = {
  'Animal': {
    "display_name": 'Animal',
    "words": [N02_004, N02_001, N02_009, N02_003, N02_002, N02_005, N02_006]
  },
  'Small Movable Object': {
    "display_name": 'Small Movable Object',
    "words": [N08_007]
  },
}
