"""
Small Movable Object - Dictionary Data

This file contains detailed word entries for the "Small Movable Object" subtype.
Each entry is a variable assignment with the GUID as the variable name.

Entry structure:
- guid: Unique identifier (e.g., N14001)
- english: English word/phrase
- chinese: Chinese translation
- alternatives: Dictionary with separate lists for English and Lithuanian alternatives
- metadata: Extensible object with difficulty_level, frequency_rank, tags, and notes
"""

N08_007 = {
  'guid': 'N08_007',
  'english': 'phone',
  'chinese': '电话',
  'alternatives': {
    'english': [],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 2,
    'frequency_rank': 1233,
    'tags': [],
    'notes': '[2025-08-12 20:54] Updated with gpt-5-mini'
  }
}

N08_019 = {
  'guid': 'N08_019',
  'english': 'pen',
  'chinese': '笔',
  'alternatives': {
    'english': ['ballpoint pen', 'fountain pen', 'writing instrument'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': 3778,
    'tags': [],
    'notes': "This entry focuses on 'pen' as a writing instrument (Lithuanian 'rašiklis'). The English word 'pen' has other meanings (e.g., an enclosure for animals or the verb 'to pen'), which are excluded here per instructions. In Lithuanian, 'rašiklis' is the general term; 'tušinukas' commonly denotes a ballpoint pen and 'plunksnakotis' an older/quill-style pen. All translations provided are base (lemma) forms."
  }
}

N08_020 = {
  'guid': 'N08_020',
  'english': 'pencil',
  'chinese': '铅笔',
  'alternatives': {
    'english': [],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': 5506,
    'tags': [],
    'notes': 'Primary meaning treated as the common, countable noun (singular). Do not confuse with the verbal idiom "to pencil (in)" (to provisionally schedule), which is a different POS (verb). Lithuanian pieštukas is the standard term; "grafitinis pieštukas" specifies a graphite pencil. French crayon is the usual translation but can also mean other drawing sticks (context distinguishes). Swahili often borrows \'penseli\' for pencil.'
  }
}

N08_021 = {
  'guid': 'N08_021',
  'english': 'knife',
  'chinese': '刀',
  'alternatives': {
    'english': [],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': 971,
    'tags': [],
    'notes': "Primary meaning treated as a countable noun (singular lemma 'knife'). The word can refer to many specific types (kitchen knife, pocketknife, butcher's knife, dagger) but those are separate lemmas. In English 'knife' can also be used as a verb ('to knife' = to stab), but this entry focuses only on the noun. Chinese often uses 刀子 (刀子) in colloquial speech and specific knives have names like 菜刀 (cleaver). All translations are given in base/lemma form."
  }
}

N08_022 = {
  'guid': 'N08_022',
  'english': 'comb',
  'chinese': '梳子',
  'alternatives': {
    'english': ['comb (verb: to comb)'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': 10053,
    'tags': [],
    'notes': "Primary meaning given: the grooming tool. Lithuanian šukos is commonly used as a plural-form lemma (pluralia tantum) for 'comb'; a singular form šukė exists but is less common. Chinese and Korean also have related verb forms (梳, 빗다) and French has the verb peigner — those are not the focus here. Swahili single-word equivalents vary by region; a descriptive phrase (kifaa cha kupamba nywele = 'tool for arranging hair') is provided to avoid incorrect single-word guesses."
  }
}

N08_023 = {
  'guid': 'N08_023',
  'english': 'toothbrush',
  'chinese': '牙刷',
  'alternatives': {
    'english': ['tooth brush'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': 10555,
    'tags': [],
    'notes': 'Countable, everyday personal hygiene item. Variants include electric toothbrush (electric dantų šepetėlis / 電動牙刷 / 전동칫솔 / brosse à dents électrique / mswaki wa umeme / bàn chải đánh răng điện) and toothbrush head (replaceable part). Translations given are the common, base-form equivalents in each language.'
  }
}

N08_024 = {
  'guid': 'N08_024',
  'english': 'string',
  'chinese': '线',
  'alternatives': {
    'english': ['cord', 'thread', 'twine'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': 9304,
    'tags': [],
    'notes': 'This entry focuses on the physical object sense of "string" (as translated by Lithuanian "vervelė"). The English lemma "string" also has other senses (e.g., a sequence of characters in computing, a series of items, or a musical instrument string) which are not covered here; those senses map to different translations in other languages. Translations provided are the most common, base-form equivalents for the physical cord/thread sense.'
  }
}

N08_025 = {
  'guid': 'N08_025',
  'english': 'candle',
  'chinese': '蜡烛',
  'alternatives': {
    'english': ['taper', 'tealight', 'votive'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': 3786,
    'tags': [],
    'notes': 'Common materials: paraffin, beeswax, soy. Types include tapers (long thin), votive, pillar, and tealight. Candles are used for lighting, decoration, ceremonies, and scent. All translations are given in base (lemma) form and the entry focuses on the primary, literal meaning (an object that produces light when lit).'
  }
}

N08_026 = {
  'guid': 'N08_026',
  'english': 'spatula',
  'chinese': '刮刀',
  'alternatives': {
    'english': ['scraper', 'turner'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 9,
    'frequency_rank': 10808,
    'tags': [],
    'notes': "'Spatula' covers several related kitchen tools: rubber/silicone spatulas used for scraping and mixing (often called 刮刀/抹刀 in Chinese or 'rubber spatula' in English), and flat metal or plastic turners used for flipping (often called 锅铲/铲子 or 'turner'). Translations vary by type and region—e.g., Chinese: 刮刀 (scraper/rubber spatula) vs. 锅铲 (wok/turner); Korean: 주걱 (general scoop/scraper) vs. 뒤집개 (turner); French 'spatule' covers both. Swahili often borrows 'spatula' from English. Provided translations are base/lemma forms and focus on the common kitchen-tool meaning."
  }
}

N08_027 = {
  'guid': 'N08_027',
  'english': 'umbrella',
  'chinese': '雨伞',
  'alternatives': {
    'english': ['parasol'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': 10342,
    'tags': [],
    'notes': "Here 'umbrella' refers to the common handheld rain/sun shield (skėtis). 'Parasol' denotes a sun-specific umbrella in English; Lithuanian alternatives include less common or dialectal forms."
  }
}

N08_028 = {
  'guid': 'N08_028',
  'english': 'stapler',
  'chinese': '订书机',
  'alternatives': {
    'english': ['paper stapler'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': None,
    'tags': [],
    'notes': "Focuses on common office stapler (handheld or desktop). Lithuanian 'segtuvas' is the standard term; 'segtukas' can also be used but sometimes refers to a small clip or safety pin."
  }
}

N08_029 = {
  'guid': 'N08_029',
  'english': 'pillow',
  'chinese': '枕头',
  'alternatives': {
    'english': [],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': 3543,
    'tags': [],
    'notes': "Refers to the common bedding item for head support during sleep; does not cover metaphorical uses (e.g., 'pillow of air') or specialized cushions like decorative cushions (which can also be called 'cushion')."
  }
}

N08_030 = {
  'guid': 'N08_030',
  'english': 'blanket',
  'chinese': '毯子',
  'alternatives': {
    'english': ['comforter', 'coverlet', 'quilt'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': 4679,
    'tags': [],
    'notes': "This entry treats 'blanket' in the primary sense of a bed covering (Lithuanian 'antklodė'). Other senses (e.g., blanket statement, blanket coverage as adjective) are excluded per instructions."
  }
}

N08_031 = {
  'guid': 'N08_031',
  'english': 'pan',
  'chinese': '平底锅',
  'alternatives': {
    'english': ['frying pan', 'skillet'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': 9174,
    'tags': [],
    'notes': "Analysis focuses on 'pan' meaning a cooking pan (Lithuanian keptuvė). Other meanings (e.g., to pan a camera, to criticize) are excluded per instructions."
  }
}

N08_032 = {
  'guid': 'N08_032',
  'english': 'vase',
  'chinese': '花瓶',
  'alternatives': {
    'english': ['urn'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': None,
    'tags': [],
    'notes': "Here 'vase' refers to a decorative flower container. 'Urn' can be a larger or funerary container; included as a related alternative. All translations are in base (singular/lemma) form."
  }
}

N08_033 = {
  'guid': 'N08_033',
  'english': 'soap',
  'chinese': '肥皂',
  'alternatives': {
    'english': ['soap (bar)', 'soap (liquid)'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': 4972,
    'tags': [],
    'notes': "This entry covers the common cleaning product (solid or liquid). Does not cover metaphorical uses (e.g., 'soap' as a genre: soap opera). All forms given as base/lemma."
  }
}

N08_034 = {
  'guid': 'N08_034',
  'english': 'razor',
  'chinese': '剃刀',
  'alternatives': {
    'english': ['razor (safety razor)', 'razor (straight razor)'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': 9507,
    'tags': [],
    'notes': "Analysis focuses on the personal shaving device meaning (Lithuanian 'skustuvas'). Does not cover figurative uses (e.g., 'razor' in compound names) or other senses like 'razor blade' as separate noun."
  }
}

N08_035 = {
  'guid': 'N08_035',
  'english': 'doll',
  'chinese': '洋娃娃',
  'alternatives': {
    'english': [],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': 4816,
    'tags': [],
    'notes': "Primary meaning: toy resembling a human. 'Doll' can have figurative uses (affectionate term), but those are excluded per lemma focus."
  }
}

N08_036 = {
  'guid': 'N08_036',
  'english': 'toy',
  'chinese': '玩具',
  'alternatives': {
    'english': ['toy (also verb: toying)'],
    'chinese': []
  },
  'metadata': {
    'difficulty_level': 15,
    'frequency_rank': 6621,
    'tags': [],
    'notes': "Primary meaning as a noun (children's play object). 'Toy' can also be a verb meaning to play with or treat lightly, but that reading is excluded per instructions."
  }
}
