"""Pattern sentences for beverage nouns."""

# Metadata for this subtype
METADATA = {
    "pos_type": "noun",
    "pos_subtype": "beverage",
    "min_level": 1,
    "max_level": 10,
}

# Pattern templates
# Format: Each dict contains:
#   - template: sentence with [beverage] placeholder
#   - fixed_words: list of dicts with "guid" (preferred) or "lemma_text"+"pos_type"
#   - notes: brief description
PATTERNS = [
    {
        "template": "i drink [beverage]",
        "fixed_words": [{"guid": "V01_004"}],  # drink
        "notes": "Drinking beverages",
    },
    {
        "template": "i want [beverage]",
        "fixed_words": [{"guid": "V05_004"}],  # want
        "notes": "Wanting a beverage",
    },
    # Room for 8+ more patterns...
]
