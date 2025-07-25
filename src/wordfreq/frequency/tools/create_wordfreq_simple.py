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
import wordfreq.frequency.corpus

# Import frequency data (from notebook cells)
data_dir = os.path.join(src_dir, "wordfreq", "data")

results = wordfreq.frequency.corpus.load_all_corpora()

# Print results
print("\nResults:")
for corpus_name, (imported, total) in results.items():
    print(f"  {corpus_name}: {imported}/{total} words imported")

# Import constants and calculate harmonic mean ranks (from notebook cells)
import constants
print("Calculating harmonic mean ranks...")
wordfreq.frequency.analysis.calculate_combined_ranks(db_path=constants.WORDFREQ_DB_PATH)

print("Word frequency data population completed!")