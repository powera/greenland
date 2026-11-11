"""English stopwords organized by categories."""

from langtools.en.grammatical_words import (
    ENGLISH_GRAMMATICAL_CONTRACTIONS,
    ENGLISH_GRAMMATICAL_WORDS_BY_CATEGORY,
)

stopwords = ENGLISH_GRAMMATICAL_WORDS_BY_CATEGORY

CONTRACTIONS = ENGLISH_GRAMMATICAL_CONTRACTIONS

COMMON_VERBS = [
    "said",
    "came",
    "come",
    "get",
    "going",
    "got",
    "know",
    "look",
    "looked",
    "make",
    "put",
    "say",
    "see",
    "tell",
    "think",
    "thought",
    "took",
    "went",
    "asked",
    "began",
    "called",
    "felt",
    "found",
    "gave",
    "give",
    "heard",
    "let",
    "like",
    "liked",
    "made",
    "seemed",
    "took",
    "go",
    "take",
    "use",
    "want",
]
COMMON_NOUNS = [
    "way",
    "thing",
    "place",
    "room",
    "door",
    "face",
    "head",
    "house",
    "man",
    "men",
    "mind",
    "moment",
    "mother",
    "father",
    "people",
    "person",
    "life",
    "nothing",
    "something",
    "anything",
    "love",
    "world",
]
COMMON_ADVERBS = [
    "now",
    "then",
    "here",
    "there",
    "where",
    "when",
    "how",
    "why",
    "again",
    "ever",
    "far",
    "forward",
    "only",
    "quite",
    "still",
    "too",
    "very",
    "always",
    "never",
    "not",
    "once",
    "more",
    "most",
    "good",
    "well",
    "new",
    "used",
    "yet",
]
MISC_WORDS = [
    "yes",
    "no",
    "just",
    "right",
    "left",
    "same",
    "even",
    "down",
    "away",
    "back",
    "much",
    "whatever",
    "enough",
    "also",
    "else",
    "other",
    "one",
    "two",
    "three",
    "great",
    "many",
    "little",
    "time",
    "first",
    "second",
    "next",
    "last",
]

# Corpus tokens that are not English vocabulary and should never become a
# lemma.  Unlike the lists above these are not common words held back from a
# report -- there is no word to add.  Each maps to why it is excluded.
NON_LEXICAL_TOKENS = {
    # Particles in personal and place names ("Guy de Maupassant", "ibn Sina"),
    # plus a few foreign function words the corpora pick up from quotations.
    "de": "name_particle",
    "des": "name_particle",
    "du": "name_particle",
    "la": "name_particle",
    "le": "name_particle",
    "der": "name_particle",
    "von": "name_particle",
    "del": "name_particle",
    "da": "name_particle",
    "di": "name_particle",
    "el": "name_particle",
    "al": "name_particle",
    "ibn": "name_particle",
    "und": "name_particle",
    "au": "name_particle",
    "los": "name_particle",
    "della": "name_particle",
    # Abbreviations: Latin ("et al.", "etc.") and citation shorthand.
    "et": "abbreviation",
    "etc": "abbreviation",
    "pp": "abbreviation",
    "ed": "abbreviation",
    "eds": "abbreviation",
    "vol": "abbreviation",
    "km": "abbreviation",
    "cm": "abbreviation",
    "mm": "abbreviation",
    "viz": "abbreviation",
    "vols": "abbreviation",
    "col": "abbreviation",
    "fol": "abbreviation",
    "nom": "abbreviation",
    "spp": "abbreviation",
    # File extensions, domain suffixes and HTML entity names left in wiki text.
    "jpg": "markup",
    "com": "markup",
    "ndash": "markup",
    "mdash": "markup",
    # Pieces the tokenizer splits off a longer written form: ordinal suffixes
    # ("19th"), elided contractions ("'em", "'tis"), "en" from "en route", and
    # "fro", which only occurs in "to and fro".
    "th": "fragment",
    "em": "fragment",
    "tis": "fragment",
    "en": "fragment",
    "fro": "fragment",
    # Halves of fixed foreign phrases: "ad hoc", "status quo", "vice versa",
    # "lingua franca", "E. coli", and "ing" from "-ing" in grammar text.
    "hoc": "fragment",
    "quo": "fragment",
    "versa": "fragment",
    "lingua": "fragment",
    "franca": "fragment",
    "coli": "fragment",
    "ing": "fragment",
    # Hesitation sounds and exclamations with no meaning a lemma could carry.
    # Interjections that do have one (wow, ouch, hello) are lemmas.
    "oh": "interjection",
    "ah": "interjection",
    "ha": "interjection",
    "eh": "interjection",
    "er": "interjection",
    "lo": "interjection",
    # Dialect spellings of function words.  A dialect form of a lemma is a
    # variant of that lemma; these spell pronouns and articles, which are not
    # lemmas, so there is nothing to attach them to.
    "tha": "dialect_function_word",
    "yer": "dialect_function_word",
    # Prefixes split off hyphenated compounds by the tokenizer ("non-linear"
    # becomes "non" and "linear").  Held back until the most frequent
    # compounds for each prefix have been imported (see
    # wordfreq.corpora.hyphenated): until then these tokens are the report's
    # pointer to that gap.  "self" is a word in its own right, and ex, sub,
    # anti and trans have standalone senses, so they will not be listed.
    # "non": "hyphen_prefix",
    # "re": "hyphen_prefix",
    # "pre": "hyphen_prefix",
    # "semi": "hyphen_prefix",
    # "multi": "hyphen_prefix",
    # "co": "hyphen_prefix",
    # "un": "hyphen_prefix",
    # "inter": "hyphen_prefix",
    # "proto": "hyphen_prefix",
    # "neo": "hyphen_prefix",
    # "pseudo": "hyphen_prefix",
    # "quasi": "hyphen_prefix",
    # "ultra": "hyphen_prefix",
}

# Create a flat list of all stopwords for easier use
all_stopwords = []
for category in stopwords.values():
    all_stopwords.extend(category)

# Remove duplicates and sort
all_stopwords = sorted(list(set(all_stopwords)))
