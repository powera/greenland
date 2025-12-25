"""
Tool Machine - Dictionary Data

This file contains detailed word entries for the "Tool Machine" subtype.
Each entry is a variable assignment with the GUID as the variable name.

Entry structure:
- guid: Unique identifier (e.g., N14001)
- english: English word/phrase
- chinese: Chinese translation
- alternatives: Dictionary with separate lists for English and Lithuanian alternatives
- metadata: Extensible object with difficulty_level, frequency_rank, tags, and notes
"""

N12_036 = {
  'guid': 'N12_036',
  'english': 'calculator',
  'chinese': '计算器',
  'alternatives': {
    'english': ['electronic calculator', 'pocket calculator'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': None,
    'tags': [],
    'notes': 'Translations given refer to the common device meaning (a calculating machine). Lithuanian: skaičiuotuvas is the standard term; kalkuliatorius is a less common variant. French calculatrice is the usual feminine noun (calculateur exists but is less common). Vietnamese máy tính can also mean "computer"; more specific "máy tính bỏ túi" or "máy tính cầm tay" = pocket calculator. Swahili kikokotoo is the common word for a (pocket) calculator. All forms are provided in their base/lemma forms.'
  }
}

N12_037 = {
  'guid': 'N12_037',
  'english': 'blender',
  'chinese': '搅拌机',
  'alternatives': {
    'english': ['liquidizer', 'mixer'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': None,
    'tags': [],
    'notes': "Commonly refers to an upright, countertop appliance for blending liquids and soft solids. Many languages also use loanwords (e.g., 'blenderis' in Lithuanian). Distinct from a food processor, which is usually for thicker chopping/slicing tasks."
  }
}
