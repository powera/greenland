"""
Nouns Seventeen - Category Structure

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

from ..dictionary.conjunction_other_dictionary import *
from ..dictionary.unit_of_measurement_dictionary import *

level_seventeen_structure = {
  'Unit Of Measurement': {
    "display_name": 'Unit Of Measurement',
    "words": [N34_009, N34_004, N34_001, N34_002, N34_003, N34_005, N34_006, N34_007, N34_008, N34_010, N34_011]
  },
  'Conjunction Other': {
    "display_name": 'Conjunction Other',
    "words": [C99_001, C99_011, C99_008, C99_006, C99_017, C99_004, C99_009, C99_010, C99_003, C99_002, C99_007, C99_016, C99_015, C99_014, C99_012, C99_013, C99_005]
  },
}
