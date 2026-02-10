"""Pattern sentences for body_part nouns."""

# Metadata for this subtype
METADATA = {
    "pos_type": "noun",
    "pos_subtype": "body_part",
    "min_level": 1,
    "max_level": 10,
}

# Pattern templates
# Format: Each dict contains:
#   - template: sentence with [body_part] placeholder
#   - fixed_words: list of dicts with "guid" (preferred) or "lemma_text"+"pos_type"
#   - notes: brief description
PATTERNS = [
    {
        "template": "my [body_part] aches",
        "fixed_words": [{"guid": "V01_096"}],  # hurt (ache)
        "notes": "Expressing pain in body part",
    },
    {
        "template": "my [body_part] hurts",
        "fixed_words": [{"guid": "V01_096"}],  # hurt (ache)
        "notes": "Body part is painful",
    },
    # Room for 8+ more patterns...
]
