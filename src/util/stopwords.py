# English stopwords organized by categories

stopwords = {
    "pronouns": [
        "I", "me", "my", "myself", "we", "us", "our", "ours", "ourselves", "you", "your", 
        "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", 
        "hers", "herself", "it", "its", "itself", "they", "them", "their", "theirs", 
        "themselves", "who", "whom", "whose", "which", "what", "that"
    ],
    "auxiliary_verbs": [
        "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", 
        "do", "does", "did", "shall", "will", "should", "would", "may", "might", 
        "must", "can", "could"
    ],
    "prepositions": [
        "at", "by", "for", "from", "in", "into", "of", "off", "on", "onto", "out", 
        "over", "to", "under", "up", "with", "about", "above", "after", "before", 
        "between", "during", "through", "upon", "without"
    ],
    "conjunctions": [
        "and", "but", "if", "or", "because", "as", "until", "while", "though", "so", "than"
    ],
    "determiners": [
        "a", "an", "the", "this", "that", "these", "those", "some", "all", "any", 
        "every", "no", "such", "another", "each", "either", "neither"
    ],
}


CONTRACTIONS = [
    # Negative contractions (very frequent)
    "don't", "doesn't", "didn't",
    "can't", "couldn't",
    "won't", "wouldn't",
    "isn't", "aren't", "wasn't", "weren't",
    "haven't", "hasn't", "hadn't",
    
    # Pronoun contractions (very frequent)
    "I'm", "I'll", "I've", "I'd",
    "you're", "you'll", "you've",
    "he's", "she's", "it's",
    "we're", "we've", "they're",
    
    # Question word contractions (common)
    "what's", "where's", "who's", 
    "that's", "there's", "here's",
    
    # Other common contractions
    "let's", "that'll", "ain't"
]


COMMON_VERBS = [
        "said", "came", "come", "get", "going", "got", "know", "look", "looked", 
        "make", "put", "say", "see", "tell", "think", "thought", "took", "went", 
        "asked", "began", "called", "felt", "found", "gave", "give", "heard", "let", 
        "like", "liked", "made", "seemed", "took", "go", "take", "use", "want"
    ]
COMMON_NOUNS = [
        "way", "thing", "place", "room", "door", "face", "head",
        "house", "man", "men", "mind", "moment", "mother", "father", "people", 
        "person", "life", "nothing", "something", "anything", "love", "world"
    ]
COMMON_ADVERBS = [
        "now", "then", "here", "there", "where", "when", "how", "why", "again", 
        "ever", "far", "forward", "only", "quite", "still", "too", "very", "always", 
        "never", "not", "once", "more", "most", "good", "well", "new", "used", "yet"
    ]
MISC_WORDS = [
        "yes", "no", "just", "right", "left", "same", "even", "down", "away", "back", 
        "much", "whatever", "enough", "also", "else", "other", "one", "two", "three", 
        "great", "many", "little", "time", "first", "second", "next", "last"
    ]

# Create a flat list of all stopwords for easier use
all_stopwords = []
for category in stopwords.values():
    all_stopwords.extend(category)

# Remove duplicates and sort
all_stopwords = sorted(list(set(all_stopwords)))
