#!/usr/bin/python3

"""
Wikipedia Word Frequency Generator

This script generates word frequency lists from Wikipedia articles.
It uses the WikiLoader to extract text content from articles listed in a file,
cleans the wiki markup, and counts word frequencies.
"""

import re
import os
import sys
import time
import string
from collections import Counter
from typing import Dict, List, Set, Tuple

# Import the WikiLoader from the uploaded module
from util.wiki_loader import WikiLoader
import constants

# Configure paths
DATA_DIR = os.path.join(constants.PROJECT_ROOT, "data")

import wordfreq.data.vital1000

OUTPUT_DIR = os.path.join(DATA_DIR, "word_frequencies")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Regular expressions for cleaning wiki markup
WIKI_MARKUP_PATTERNS = [
    r"\{\{[^}]*\}\}",  # Templates: {{...}}
    r"\[\[[^\]]*\|([^\]]*)\]\]",  # Internal links with text: [[page|text]] -> text
    r"\[\[([^\]]*)\]\]",  # Internal links: [[page]] -> page
    r"\[https?://[^\s\]]*\s([^\]]*)\]",  # External links with text: [http://example.com text] -> text
    r"\[https?://[^\s\]]*\]",  # External links without text: [http://example.com] -> ''
    r"<ref[^>]*>.*?</ref>",  # References: <ref>...</ref>
    r"<[^>]*>",  # HTML tags: <tag>
    r"^\s*=+\s*([^=]+)\s*=+\s*$",  # Headers: == Header == -> Header
    r"'''([^']*)'''",  # Bold text: '''text''' -> text
    r"''([^']*)''",  # Italic text: ''text'' -> text
    r"<!--.*?-->",  # HTML comments: <!-- comment -->
    r"__[A-Z]+__",  # Magic words: __TOC__, __NOTOC__, etc.
    r"^[\*#:;]+\s*",  # List markers and indentation
    r"^----+$",  # Horizontal rules
]


def load_article_list(file_path: str) -> List[str]:
    """
    Load the list of article names from a file.

    Args:
        file_path: Path to the file containing article names (one per line)

    Returns:
        List of article names
    """
    if not os.path.exists(file_path):
        print(f"Error: Article list file not found: {file_path}")
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def clean_wiki_text(text: str) -> str:
    """
    Clean Wiki markup from text.

    Args:
        text: Raw Wiki text

    Returns:
        Cleaned text
    """
    # Replace specific wiki entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')

    # Apply regex patterns to remove wiki markup
    for pattern in WIKI_MARKUP_PATTERNS:
        if "(" in pattern:  # If the pattern has a capturing group
            text = re.sub(pattern, r"\1", text, flags=re.MULTILINE | re.DOTALL)
        else:
            text = re.sub(pattern, " ", text, flags=re.MULTILINE | re.DOTALL)

    # Handle tables - this is a simple approach; tables can be complex
    text = re.sub(r"\{\|[\s\S]*?\|\}", " ", text)

    # Remove file/image links
    text = re.sub(r"\[\[File:[^\]]*\]\]", " ", text)
    text = re.sub(r"\[\[Image:[^\]]*\]\]", " ", text)

    # Remove remaining markup and clean up spacing
    text = re.sub(r"[=]{2,}", " ", text)  # Remove any remaining === header marks ===
    text = re.sub(r"\n+", " ", text)  # Replace newlines with spaces
    text = re.sub(r"\s+", " ", text)  # Replace multiple spaces with single space

    return text.strip()


def tokenize_text(text: str) -> List[str]:
    """
    Split text into tokens (words).

    Args:
        text: Cleaned text

    Returns:
        List of words
    """
    # Convert to lowercase
    text = text.lower()

    # Remove punctuation and replace with spaces
    translator = str.maketrans(string.punctuation, " " * len(string.punctuation))
    text = text.translate(translator)

    # Split on whitespace
    tokens = text.split()

    # Filter out tokens that are just numbers or single characters (except 'a' and 'i')
    valid_tokens = []
    for token in tokens:
        if token.isdigit():
            continue
        if len(token) == 1 and token not in ["a", "i"]:
            continue
        valid_tokens.append(token)

    return valid_tokens


def process_article(wiki_loader: WikiLoader, article_name: str) -> Counter:
    """
    Process a single article and count its words.

    Args:
        wiki_loader: Initialized WikiLoader instance
        article_name: Name of the article to process

    Returns:
        Counter object with word frequencies
    """
    try:
        # Get the raw wiki text
        raw_text = wiki_loader.get_text_from_page(article_name)

        # Clean the text
        cleaned_text = clean_wiki_text(raw_text)

        # Tokenize the text
        tokens = tokenize_text(cleaned_text)

        # Count words
        word_counts = Counter(tokens)

        print(
            f"Processed article: {article_name} - {len(tokens)} tokens, {len(word_counts)} unique words"
        )
        return word_counts

    except Exception as e:
        print(f"Error processing article '{article_name}': {e}")
        return Counter()


def main():
    """Main function to process articles and generate word frequencies."""
    # Initialize the WikiLoader
    wiki_loader = WikiLoader()

    # Load the list of articles
    article_names = [
        item
        for sublist in wordfreq.data.vital1000.vital.values()
        if isinstance(sublist, list)
        for item in sublist
    ]

    if not article_names:
        print("No articles found. Exiting.")
        return

    print(f"Found {len(article_names)} articles to process")

    # Process all articles and aggregate word counts
    total_word_counts = Counter()
    total_articles_processed = 0

    start_time = time.time()

    for i, article_name in enumerate(article_names, 1):
        print(f"Processing article {i}/{len(article_names)}: {article_name}")

        article_counts = process_article(wiki_loader, article_name)
        if article_counts:
            total_word_counts.update(article_counts)
            total_articles_processed += 1

        # Optional: Save progress periodically
        if i % 10 == 0 or i == len(article_names):
            print(f"Progress update: {i}/{len(article_names)} articles processed")

    end_time = time.time()
    processing_time = end_time - start_time

    print(f"\nProcessing complete.")
    print(f"Total time: {processing_time:.2f} seconds")
    print(f"Articles processed: {total_articles_processed}")
    print(f"Total unique words: {len(total_word_counts)}")

    # Save the results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"word_frequencies_{timestamp}.txt")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("word,frequency\n")
        for word, count in total_word_counts.most_common():
            f.write(f"{word},{count}\n")

    print(f"Word frequencies saved to {output_file}")

    # Also save a JSON version for easier processing
    json_output_file = os.path.join(OUTPUT_DIR, f"word_frequencies_{timestamp}.json")

    import json

    with open(json_output_file, "w", encoding="utf-8") as f:
        json.dump(dict(total_word_counts.most_common()), f, ensure_ascii=False, indent=2)

    print(f"Word frequencies also saved as JSON to {json_output_file}")


if __name__ == "__main__":
    main()
