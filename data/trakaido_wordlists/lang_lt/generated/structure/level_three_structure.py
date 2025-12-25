"""
Nouns Three - Category Structure

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

from ..dictionary.body_part_dictionary import *
from ..dictionary.color_dictionary import *
from ..dictionary.emotion_feeling_dictionary import *

level_three_structure = {
  'Color': {
    "display_name": 'Color',
    "words": [A02_002, A02_001, A02_003, A02_005, A02_007, A02_004, A02_006, A02_008]
  },
  'Emotion Feeling': {
    "display_name": 'Emotion Feeling',
    "words": [N23_001, N23_005, N23_003, N23_007, N23_002, N23_006, N23_004, N23_020, N23_011, N23_022, N23_021, N23_025]
  },
  'Body Part': {
    "display_name": 'Body Part',
    "words": [N03_014, N03_030, N03_003, N03_027, N03_005, N03_011, N03_024, N03_004, N03_006, N03_020, N03_015, N03_028, N03_022, N03_029, N03_016]
  },
}
