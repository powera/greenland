import re

def count_syllables(word):
    """Count the number of syllables in a word."""
    word = word.lower()
    count = 0
    vowels = "aeiouy"
    if word[0] in vowels:
        count += 1
    for index in range(1, len(word)):
        if word[index] in vowels and word[index - 1] not in vowels:
            count += 1
    if word.endswith("e"):
        count -= 1
    if word.endswith("le"):
        count += 1
    if count == 0:
        count += 1
    return count

def flesch_kincaid_grade(text):
    """Calculate the Flesch-Kincaid Grade Level for the given text."""
    sentences = re.findall(r'\w+[.!?]', text)
    words = re.findall(r'\b\w+\b', text.lower())
    
    total_sentences = len(sentences)
    total_words = len(words)
    total_syllables = sum(count_syllables(word) for word in words)
    
    if total_sentences == 0 or total_words == 0:
        return 0.0
    
    grade = 0.39 * (total_words / total_sentences) + 11.8 * (total_syllables / total_words) - 15.59
    return round(grade, 2)
