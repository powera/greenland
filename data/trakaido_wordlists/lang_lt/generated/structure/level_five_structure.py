"""
Nouns Five - Category Structure

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

from ..dictionary.human_dictionary import *
from ..dictionary.other_dictionary import *

level_five_structure = {
  'Human': {
    "display_name": 'Human',
    "words": [N01_055, N01_056, N01_060, N01_059, N01_057, N01_058, N01_061, N01_062, N01_063, N01_002, N01_064, N01_030, N01_001, N01_025, N01_003, N01_018, N01_011, N01_005, N01_009, N01_010, N01_019, N01_004, N01_026, N01_016, N01_008, N01_022, N01_021, N01_029, N01_017, N01_024, N01_020, N01_012, N01_028, N01_014, N01_006, N01_007, N01_013, N01_015, N01_023, N01_027]
  },
  'Other': {
    "display_name": 'Other',
    "words": [N99_001, N99_002, N99_003, N99_004, N99_005, N99_006]
  },
}
