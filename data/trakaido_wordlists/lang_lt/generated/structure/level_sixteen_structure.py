"""
Nouns Sixteen - Category Structure

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
from ..dictionary.concept_idea_dictionary import *

level_sixteen_structure = {
  'Building Structure': {
    "display_name": 'Building Structure',
    "words": [N07_031, N07_032, N07_033, N07_034, N07_035, N07_036, N07_037, N07_038, N07_039, N07_040, N07_041]
  },
  'Concept Idea': {
    "display_name": 'Concept Idea',
    "words": [N17_021, N17_049, N17_062, N17_019, N17_022, N17_054, N17_020, N17_024, N17_046, N17_037, N17_058, N17_044, N17_030, N17_027, N17_036, N17_023, N17_031, N17_025, N17_039, N17_045, N17_029, N17_026, N17_034, N17_028, N17_057, N17_040, N17_052, N17_032, N17_038, N17_033, N17_051, N17_047, N17_041, N17_035, N17_050, N17_061, N17_063, N17_043, N17_048, N17_056, N17_055, N17_042, N17_059, N17_060, N17_053]
  },
}
