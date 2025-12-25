"""
Nouns Nine - Category Structure

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
from ..dictionary.food_drink_dictionary import *
from ..dictionary.sequence_dictionary import *
from ..dictionary.small_movable_object_dictionary import *
from ..dictionary.tool_machine_dictionary import *

level_nine_structure = {
  'Food Drink': {
    "display_name": 'Food Drink',
    "words": [N06_085, N06_086, N06_087, N06_088]
  },
  'Animal': {
    "display_name": 'Animal',
    "words": [N02_011, N02_012, N02_013, N02_014, N02_015, N02_016]
  },
  'Small Movable Object': {
    "display_name": 'Small Movable Object',
    "words": [N08_019, N08_020, N08_021, N08_022, N08_023, N08_024, N08_025, N08_026]
  },
  'Tool Machine': {
    "display_name": 'Tool Machine',
    "words": [N12_036, N12_037]
  },
  'Sequence': {
    "display_name": 'Sequence',
    "words": [A15_001, A15_002, A15_003, A15_004, A15_005, A15_006, A15_007, A15_008, A15_009, A15_010]
  },
}
