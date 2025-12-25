"""
Other - Dictionary Data

This file contains detailed word entries for the "Other" subtype.
Each entry is a variable assignment with the GUID as the variable name.

Entry structure:
- guid: Unique identifier (e.g., N14001)
- english: English word/phrase
- lithuanian: Lithuanian translation
- alternatives: Dictionary with separate lists for English and Lithuanian alternatives
- metadata: Extensible object with difficulty_level, frequency_rank, tags, and notes
"""

N99_001 = {
  'guid': 'N99_001',
  'english': 'excuse me',
  'lithuanian': 'atsiprašau',
  'alternatives': {
    'english': [],
    'lithuanian': []
  },
  'metadata': {
    'difficulty_level': 5,
    'frequency_rank': None,
    'tags': [],
    'notes': 'Commonly used in social interactions to politely ask for attention or to apologize.'
  }
}

N99_002 = {
  'guid': 'N99_002',
  'english': 'thank you',
  'lithuanian': 'ačiū',
  'alternatives': {
    'english': [],
    'lithuanian': []
  },
  'metadata': {
    'difficulty_level': 5,
    'frequency_rank': None,
    'tags': [],
    'notes': "'Thank you' is a common phrase used to express appreciation. In Lithuanian, 'ačiū' serves the same purpose."
  }
}

N99_003 = {
  'guid': 'N99_003',
  'english': 'yes',
  'lithuanian': 'taip',
  'alternatives': {
    'english': ['affirmative', 'yah', 'yeah', 'yep'],
    'lithuanian': ['taip (taipgi)']
  },
  'metadata': {
    'difficulty_level': 5,
    'frequency_rank': 10648,
    'tags': [],
    'notes': "Analyzed as the base interjection/adverb meaning an affirmative response. Alternatives listed are colloquial variants; Lithuanian primary alternative 'taipgi' is emphatic. Not treated as a noun ('a yes') or as part of fixed phrases."
  }
}

N99_004 = {
  'guid': 'N99_004',
  'english': 'no',
  'lithuanian': 'ne',
  'alternatives': {
    'english': [],
    'lithuanian': []
  },
  'metadata': {
    'difficulty_level': 5,
    'frequency_rank': 33,
    'tags': [],
    'notes': "Analyzed as the negation/response interjection/adverb meaning 'no' (not the determiner 'no' as in 'no people'). In Lithuanian, 'ne' is the standard negation/response form."
  }
}

N99_005 = {
  'guid': 'N99_005',
  'english': 'please',
  'lithuanian': 'prašau',
  'alternatives': {
    'english': [],
    'lithuanian': ['prašyti (verb)']
  },
  'metadata': {
    'difficulty_level': 5,
    'frequency_rank': 523,
    'tags': [],
    'notes': "Primary use as an interjection for polite requests. In some languages 'please' corresponds to different grammatical forms (e.g., Lithuanian 'prašau' is an interjection; a related verb is 'prašyti')."
  }
}

N99_006 = {
  'guid': 'N99_006',
  'english': 'maybe',
  'lithuanian': 'galbūt',
  'alternatives': {
    'english': ['perhaps'],
    'lithuanian': ['gal']
  },
  'metadata': {
    'difficulty_level': 5,
    'frequency_rank': 376,
    'tags': [],
    'notes': 'Functions primarily as an adverb indicating possibility; can also be used discourse-wise to soften statements. No noun/verb base form per primary usage.'
  }
}
