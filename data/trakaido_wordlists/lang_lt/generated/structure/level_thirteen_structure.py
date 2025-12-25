"""
Nouns Thirteen - Category Structure

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

from ..dictionary.concept_idea_dictionary import *
from ..dictionary.place_name_dictionary import *
from ..dictionary.quality_dictionary import *
from ..dictionary.time_period_dictionary import *

level_thirteen_structure = {
  'Place Name': {
    "display_name": 'Place Name',
    "words": [N30_036, N30_037, N30_039, N30_041, N30_040, N30_053, N30_048, N30_043, N30_038, N30_047, N30_052, N30_044, N30_049, N30_046, N30_051, N30_050, N30_042, N30_045]
  },
  'Concept Idea': {
    "display_name": 'Concept Idea',
    "words": [N17_016, N17_001, N17_002, N17_003, N17_018, N17_005, N17_007, N17_004, N17_006, N17_008, N17_015, N17_010, N17_017, N17_013, N17_014, N17_012, N17_009, N17_011]
  },
  'Quality': {
    "display_name": 'Quality',
    "words": [A05_035, A05_046, A05_001, A05_045, A05_040, A05_036, A05_038, A05_041, A05_044, A05_042, A05_037, A05_003, A05_039, A05_047, A05_006, A05_002, A05_043, A05_011, A05_009, A05_005, A05_014, A05_013, A05_004, A05_007, A05_010]
  },
  'Time Period': {
    "display_name": 'Time Period',
    "words": [N25_002, N25_018, N25_001, N25_003, N25_007, N25_014, N25_013, N25_017, N25_019, N25_015, N25_010, N25_004, N25_012, N25_016, N25_020, N25_011, N25_005, N25_009, N25_008, N25_006]
  },
}
