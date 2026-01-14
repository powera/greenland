"""Pattern sentences for building_structure nouns."""

# Metadata for this subtype
METADATA = {
    "pos_type": "noun",
    "pos_subtype": "building_structure",
    "min_level": 1,
    "max_level": 10,
}

# Pattern templates
# Format: Each dict contains:
#   - template: sentence with [building_structure] placeholder
#   - fixed_words: list of dicts with "guid" (preferred) or "lemma_text"+"pos_type"
#   - notes: brief description
PATTERNS = [
    {
        "template": "where is the [building_structure]",
        "fixed_words": [],
        "notes": "Asking about location of a building",
    },
    {
        "template": "i go to the [building_structure]",
        "fixed_words": [{"guid": "V12_007"}, {"guid": "R99_006"}],  # go, to
        "notes": "Going to a building",
    },
    # Room for 8+ more patterns...
]
