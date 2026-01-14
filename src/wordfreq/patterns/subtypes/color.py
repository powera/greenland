"""Pattern sentences for color adjectives."""

# Metadata for this subtype
METADATA = {
    "pos_type": "adjective",
    "pos_subtype": "color",
    "min_level": 1,
    "max_level": 10,
}

# Pattern templates
# Format: Each dict contains:
#   - template: sentence with [color] placeholder
#   - fixed_words: list of dicts with "guid" (preferred) or "lemma_text"+"pos_type"
#   - notes: brief description
PATTERNS = [
    {
        "template": "i like [color]",
        "fixed_words": [{"guid": "V05_001"}],  # like
        "notes": "Expressing color preference",
    },
    {
        "template": "it is [color]",
        "fixed_words": [],
        "notes": "Describing color of something",
    },
    # Room for 8+ more patterns...
]
