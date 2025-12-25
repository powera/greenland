"""
Nouns Fifteen - Category Structure

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
from ..dictionary.body_part_dictionary import *
from ..dictionary.building_structure_dictionary import *
from ..dictionary.clothing_accessory_dictionary import *
from ..dictionary.plant_dictionary import *
from ..dictionary.small_movable_object_dictionary import *

level_fifteen_structure = {
  'Animal': {
    "display_name": 'Animal',
    "words": [N02_017, N02_018, N02_019, N02_020, N02_021, N02_022, N02_023, N02_024, N02_025, N02_026, N02_027, N02_028]
  },
  'Plant': {
    "display_name": 'Plant',
    "words": [N05_009, N05_010, N05_011, N05_012, N05_013, N05_014, N05_015, N05_016, N05_017]
  },
  'Clothing Accessory': {
    "display_name": 'Clothing Accessory',
    "words": [N09_018, N09_019, N09_020, N09_021, N09_022, N09_023, N09_024, N09_025]
  },
  'Small Movable Object': {
    "display_name": 'Small Movable Object',
    "words": [N08_027, N08_028, N08_029, N08_030, N08_031, N08_032, N08_033, N08_034, N08_035, N08_036]
  },
  'Building Structure': {
    "display_name": 'Building Structure',
    "words": [N07_018, N07_019, N07_020, N07_021, N07_022, N07_023, N07_024, N07_025, N07_027, N07_029]
  },
  'Body Part': {
    "display_name": 'Body Part',
    "words": [N03_031, N03_032, N03_033, N03_034, N03_035, N03_036, N03_037, N03_038, N03_039, N03_040, N03_041, N03_042, N03_043, N03_044, N03_045]
  },
}
