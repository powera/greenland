"""Pattern sentences for animal nouns."""

# Metadata for this subtype
METADATA = {
    "pos_type": "noun",
    "pos_subtype": "animal",
    "min_level": 1,
    "max_level": 10,
}

# Pattern templates
# Format: Each dict contains:
#   - template: sentence with [animal] placeholder
#   - fixed_words: list of dicts with "guid" (preferred) or "lemma_text"+"pos_type"
#   - notes: brief description
PATTERNS = [
    {
        "template": "i see the [animal]",
        "fixed_words": [{"guid": "V10_001"}],  # see
        "notes": "Observing an animal",
    },
    {
        "template": "the [animal] drinks water",
        "fixed_words": [{"guid": "V01_004"}, {"guid": "N42_001"}],  # drink, water
        "notes": "Animal drinking water",
    },
    # Room for 8+ more patterns...
]
