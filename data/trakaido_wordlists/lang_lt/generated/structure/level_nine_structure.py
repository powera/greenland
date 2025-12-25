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
from ..dictionary.emotion_feeling_dictionary import *
from ..dictionary.food_drink_dictionary import *
from ..dictionary.location_dictionary import *
from ..dictionary.quality_dictionary import *
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
    "words": [N08_014, N08_008, N08_013, N08_019, N08_020, N08_021, N08_022, N08_023, N08_024, N08_025, N08_026]
  },
  'Tool Machine': {
    "display_name": 'Tool Machine',
    "words": [N12_011, N12_021, N12_033, N12_020, N12_019, N12_034, N12_026, N12_015, N12_025, N12_017, N12_028, N12_022, N12_031, N12_013, N12_012, N12_014, N12_016, N12_018, N12_023, N12_024, N12_027, N12_029, N12_030, N12_032, N12_035, N12_036, N12_037]
  },
  'Emotion Feeling': {
    "display_name": 'Emotion Feeling',
    "words": [N23_013, N23_010, N23_009, N23_008, N23_015, N23_024, N23_016, N23_023, N23_014, N23_019, N23_012, N23_017, N23_018]
  },
  'Quality': {
    "display_name": 'Quality',
    "words": [A05_015, A05_021, A05_018, A05_019, A05_030, A05_031, A05_032, A05_017, A05_020, A05_024, A05_022, A05_016, A05_025, A05_034, A05_029, A05_023, A05_026, A05_028, A05_027, A05_033, A05_008, A05_012]
  },
  'Location': {
    "display_name": 'Location',
    "words": [D07_007, D07_001, D07_006, D07_003, D07_002, D07_004, D07_011, D07_010, D07_005, D07_008, D07_012, D07_009]
  },
  'Sequence': {
    "display_name": 'Sequence',
    "words": [A15_001, A15_002, A15_003, A15_004, A15_005, A15_006, A15_007, A15_008, A15_009, A15_010]
  },
}
