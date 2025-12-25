from lang_lt.wordlists import get_all_word_pairs_flat


def find_missing_words(input_words):
    """
    Find English words that are not already in the app's wordlists.
    
    Args:
        input_words: Either a list of words ["word1", "word2"] or a file path 
                    containing one word per line.
    
    Returns:
        list: A list of English words (in order) that are not found in any 
              of the app's wordlists.
    """
    # Get all existing English words from the app
    existing_words = set()
    flat_words = get_all_word_pairs_flat()
    for word_pair in flat_words:
        existing_words.add(word_pair['english'].lower())
    
    # Determine if input_words is a file path or a list
    if isinstance(input_words, str):
        # It's a file path
        try:
            with open(input_words, 'r', encoding='utf-8') as file:
                words_to_check = [line.strip() for line in file if line.strip()]
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {input_words}")
        except Exception as e:
            raise Exception(f"Error reading file {input_words}: {e}")
    elif isinstance(input_words, list):
        # It's a list of words
        words_to_check = input_words
    else:
        raise TypeError("input_words must be either a list of words or a file path string")
    
    # Find missing words (preserve order)
    missing_words = []
    for word in words_to_check:
        if word.lower() not in existing_words:
            missing_words.append(word)
    
    return missing_words


def check_for_duplicates():
    """
    Checks for duplicate words in the wordlists.
    
    This function identifies four types of duplicates:
    1. Exact English duplicates - the same English word appears multiple times
    2. Semantic English duplicates - the same English word with different Lithuanian translations
       (potentially different meanings)
    3. Exact Lithuanian duplicates - the same Lithuanian word appears multiple times
    4. Semantic Lithuanian duplicates - the same Lithuanian word with different English translations
       (potentially different meanings)
    
    Returns:
        tuple: (english_exact_duplicates, english_semantic_duplicates, 
                lithuanian_exact_duplicates, lithuanian_semantic_duplicates)
            - english_exact_duplicates: A list of English words that appear multiple times
            - english_semantic_duplicates: A dictionary where keys are English words and values
              are lists of different Lithuanian translations
            - lithuanian_exact_duplicates: A list of Lithuanian words that appear multiple times
            - lithuanian_semantic_duplicates: A dictionary where keys are Lithuanian words and values
              are lists of different English translations
    """
    flat_words = get_all_word_pairs_flat()
    
    # Track English word occurrences and translations
    english_word_count = {}
    english_word_translations = {}
    
    # Track Lithuanian word occurrences and translations
    lithuanian_word_count = {}
    lithuanian_word_translations = {}
    
    # Find duplicates
    english_exact_duplicates = []
    english_semantic_duplicates = {}
    lithuanian_exact_duplicates = []
    lithuanian_semantic_duplicates = {}
    
    for word_pair in flat_words:
        english = word_pair['english']
        lithuanian = word_pair['lithuanian']
        
        # Track English word count
        if english in english_word_count:
            english_word_count[english] += 1
            if english_word_count[english] == 2:  # Only add to duplicates list once
                english_exact_duplicates.append(english)
        else:
            english_word_count[english] = 1
        
        # Track different Lithuanian translations for English words
        if english in english_word_translations:
            if lithuanian not in english_word_translations[english]:
                english_word_translations[english].append(lithuanian)
                # If we find a new translation, it's a semantic duplicate
                if len(english_word_translations[english]) == 2:  # Only add to semantic duplicates once
                    english_semantic_duplicates[english] = english_word_translations[english]
        else:
            english_word_translations[english] = [lithuanian]
        
        # Track Lithuanian word count
        if lithuanian in lithuanian_word_count:
            lithuanian_word_count[lithuanian] += 1
            if lithuanian_word_count[lithuanian] == 2:  # Only add to duplicates list once
                lithuanian_exact_duplicates.append(lithuanian)
        else:
            lithuanian_word_count[lithuanian] = 1
        
        # Track different English translations for Lithuanian words
        if lithuanian in lithuanian_word_translations:
            if english not in lithuanian_word_translations[lithuanian]:
                lithuanian_word_translations[lithuanian].append(english)
                # If we find a new translation, it's a semantic duplicate
                if len(lithuanian_word_translations[lithuanian]) == 2:  # Only add to semantic duplicates once
                    lithuanian_semantic_duplicates[lithuanian] = lithuanian_word_translations[lithuanian]
        else:
            lithuanian_word_translations[lithuanian] = [english]
    
    return english_exact_duplicates, english_semantic_duplicates, lithuanian_exact_duplicates, lithuanian_semantic_duplicates


def print_words_by_frequency():
    """
    Print all words from the wordlists sorted by frequency_rank.
    
    Words with frequency_rank of None (null) will be printed at the end.
    For each word, prints: frequency_rank, English word, Lithuanian word, corpus, group
    """
    flat_words = get_all_word_pairs_flat()
    
    # Separate words with frequency_rank from those without
    words_with_rank = []
    words_without_rank = []
    
    for word_pair in flat_words:
        frequency_rank = word_pair.get('metadata', {}).get('frequency_rank')
        if frequency_rank is not None:
            words_with_rank.append(word_pair)
        else:
            words_without_rank.append(word_pair)
    
    # Sort words with frequency_rank by their rank (lower rank = more frequent)
    words_with_rank.sort(key=lambda x: x['metadata']['frequency_rank'])
    
    # Sort words without frequency_rank alphabetically by English word
    words_without_rank.sort(key=lambda x: x['english'].lower())
    
    # Print header
    print(f"{'Rank':<8} {'English':<20} {'Lithuanian':<20} {'Corpus':<20} {'Group':<30}")
    print("-" * 98)
    
    # Print words with frequency_rank
    for word_pair in words_with_rank:
        rank = word_pair['metadata']['frequency_rank']
        english = word_pair['english']
        lithuanian = word_pair['lithuanian']
        corpus = word_pair['corpus']
        group = word_pair['group']
        
        print(f"{rank:<8} {english:<20} {lithuanian:<20} {corpus:<20} {group:<30}")
    
    # Print separator for words without rank
    if words_without_rank:
        print("\n" + "=" * 98)
        print("WORDS WITHOUT FREQUENCY RANK:")
        print("=" * 98)
        
        # Print words without frequency_rank
        for word_pair in words_without_rank:
            english = word_pair['english']
            lithuanian = word_pair['lithuanian']
            corpus = word_pair['corpus']
            group = word_pair['group']
            
            print(f"{'N/A':<8} {english:<20} {lithuanian:<20} {corpus:<20} {group:<30}")
    
    # Print summary
    total_words = len(flat_words)
    words_with_rank_count = len(words_with_rank)
    words_without_rank_count = len(words_without_rank)
    
    print(f"\nSUMMARY:")
    print(f"Total words: {total_words}")
    print(f"Words with frequency rank: {words_with_rank_count}")
    print(f"Words without frequency rank: {words_without_rank_count}")
