#!/usr/bin/env python3
"""
Simple script that directly mirrors the CreateWordFreq.ipynb notebook.

This script follows the exact same structure and imports as the original notebook.
"""

import os
import sys

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
src_dir = os.path.join(project_root, 'src')
sys.path.insert(0, src_dir)

# Direct imports from the notebook
import wordfreq.translation.client
import wordfreq.dictionary.reviewer
import wordfreq.storage.database

# Initialize client and reviewer (from notebook cells)
CLIENT = wordfreq.translation.client.LinguisticClient()
REVIEWER = wordfreq.dictionary.reviewer.LinguisticReviewer()

# Create database session (from notebook cell)
session = wordfreq.storage.database.create_database_session()

# Ensure all database tables exist
print("Initializing database tables...")
wordfreq.storage.database.ensure_tables_exist(session)

# Initialize corpora entries
print("Initializing corpora...")
wordfreq.storage.database.initialize_corpora(session)

# Import additional modules (from notebook cells)
import wordfreq.frequency.analysis
import wordfreq.frequency.importer

# Import frequency data (from notebook cells)
data_dir = os.path.join(src_dir, "wordfreq", "data")

print("Importing 19th century books data...")
wordfreq.frequency.importer.import_frequency_data(os.path.join(data_dir, "19th_books.json"), "19th_books", max_words=2000, corpus_description="Word frequency data from 19th century books")

print("Importing 20th century books data...")
wordfreq.frequency.importer.import_frequency_data(os.path.join(data_dir, "20th_books.json"), "20th_books", max_words=2000, corpus_description="Word frequency data from 20th century books")

print("Importing subtitles data...")
wordfreq.frequency.importer.import_frequency_data(os.path.join(data_dir, "subtlex.txt"), "subtitles", file_type="subtlex", max_words=2000, corpus_description="Word frequency data from movie and TV subtitles")

print("Importing Wikipedia vital articles data...")
wordfreq.frequency.importer.import_frequency_data(os.path.join(data_dir, "wiki_vital.json"), "wiki_vital", max_words=2000, value_type="frequency", corpus_description="Word frequency data from Wikipedia vital articles")

# Import constants and calculate harmonic mean ranks (from notebook cells)
import constants
print("Calculating harmonic mean ranks...")
wordfreq.frequency.analysis.calculate_harmonic_mean_ranks(db_path=constants.WORDFREQ_DB_PATH)

print("Word frequency data population completed!")