"""
Nouns Eighteen - Category Structure

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

from ..dictionary.natural_feature_dictionary import *
from ..dictionary.temporal_name_dictionary import *

level_eighteen_structure = {
  'Natural Feature': {
    "display_name": 'Natural Feature',
    "words": [N11_007, N11_004, N11_010, N11_006, N11_002, N11_001, N11_012, N11_005, N11_003, N11_009, N11_016, N11_008, N11_015, N11_011, N11_014, N11_018, N11_013, N11_017, N11_019, N11_032]
  },
  'Temporal Name': {
    "display_name": 'Temporal Name',
    "words": [N32_012, N32_010, N32_015, N32_013, N32_014, N32_011, N32_017, N32_016, N32_019, N32_008, N32_018, N32_009, N32_006, N32_005, N32_007, N32_001, N32_004, N32_002, N32_003]
  },
}
