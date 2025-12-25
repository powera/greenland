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
from ..dictionary.tool_machine_dictionary import *

level_two_structure = {
  'Animal': {
    "display_name": 'Animal',
    "words": [N02_004, N02_001, N02_009, N02_003, N02_002, N02_007, N02_008, N02_005, N02_010, N02_006]
  },
  'Small Movable Object': {
    "display_name": 'Small Movable Object',
    "words": [N08_005, N08_003, N08_006, N08_018, N08_007, N08_009, N08_004, N08_012, N08_016, N08_002, N08_001, N08_017, N08_010, N08_015, N08_011]
  },
  'Tool Machine': {
    "display_name": 'Tool Machine',
    "words": [N12_007, N12_001, N12_006, N12_003, N12_002, N12_009, N12_005, N12_008, N12_004, N12_010]
  },
}
