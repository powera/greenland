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
from ..dictionary.style_dictionary import *

level_eleven_structure = {
  'Food Drink': {
    "display_name": 'Food Drink',
    "words": [N06_008, N06_011, N06_009, N06_039, N06_022, N06_010, N06_017, N06_038, N06_066, N06_030, N06_076, N06_028, N06_042, N06_023, N06_019, N06_040, N06_077, N06_074, N06_073, N06_068, N06_036, N06_033, N06_078, N06_060, N06_062, N06_031, N06_041, N06_061, N06_079, N06_048, N06_049, N06_026, N06_058, N06_027, N06_063, N06_045, N06_053, N06_083, N06_065, N06_035, N06_082, N06_044, N06_057, N06_067, N06_056, N06_047, N06_081, N06_032, N06_080, N06_072, N06_025, N06_034, N06_024, N06_029, N06_037, N06_043, N06_046, N06_050, N06_051, N06_052, N06_054, N06_055, N06_059, N06_064, N06_069, N06_070, N06_071, N06_075, N06_084]
  },
  'Style': {
    "display_name": 'Style',
    "words": [D01_003, D01_009, D01_008, D01_010, D01_002, D01_001, D01_007, D01_006, D01_004, D01_005]
  },
}
