"""Pattern sentences for clothing_accessory nouns."""

# Metadata for this subtype
METADATA = {
    "pos_type": "noun",
    "pos_subtype": "clothing_accessory",
    "min_level": 1,
    "max_level": 10,
}

# Pattern templates
# Format: Each dict contains:
#   - template: sentence with [clothing_accessory] placeholder
#   - fixed_words: list of dicts with "guid" (preferred) or "lemma_text"+"pos_type"
#   - notes: brief description
PATTERNS = [
    {
        "template": "i want a [clothing_accessory]",
        "fixed_words": [{"guid": "V05_004"}],  # want
        "notes": "Wanting clothing",
    },
    {
        "template": "i wear [clothing_accessory]",
        "fixed_words": [{"lemma_text": "wear", "pos_type": "verb"}],  # wear (no GUID found yet)
        "notes": "Wearing clothing",
    },
    # Room for 8+ more patterns...
]
