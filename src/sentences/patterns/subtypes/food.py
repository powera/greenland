"""Pattern sentences for food nouns."""

# Metadata for this subtype
METADATA = {
    "pos_type": "noun",
    "pos_subtype": "food",
    "min_level": 1,
    "max_level": 10,
}

# Pattern templates
# Format: Each dict contains:
#   - template: sentence with [food] placeholder
#   - fixed_words: list of dicts with "guid" (preferred) or "lemma_text"+"pos_type"
#   - notes: brief description
PATTERNS = [
    {
        "template": "i eat [food]",
        "fixed_words": [{"guid": "V01_006"}],  # eat
        "notes": "Eating food",
    },
    {
        "template": "i like [food]",
        "fixed_words": [{"guid": "V05_001"}],  # like
        "notes": "Expressing food preference",
    },
    # Room for 8+ more patterns...
]
