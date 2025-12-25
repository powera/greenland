"""
Nouns Four - Category Structure

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

from ..dictionary.definite_quantity_dictionary import *

level_four_structure = {
  'Definite Quantity': {
    "display_name": 'Definite Quantity',
    "words": [A11_029, A11_030]
  },
}
