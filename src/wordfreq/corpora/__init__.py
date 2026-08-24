"""Corpus construction from Project Gutenberg plain-text books.

The three corpora built here (``19th_books``, ``20th_books``,
``religious_translated``) are word-frequency JSON files consumed by
``wordfreq.frequency.corpus`` / ``wordfreq.frequency.importer``.

Pipeline:

1. ``book_lists`` names the Gutenberg ebook IDs that make up each corpus.
2. ``download_gutenberg`` fetches those texts into a scratch cache directory.
3. ``gutenberg_text`` strips the Gutenberg header/footer and tokenizes.
4. ``frequency_build`` counts, separates proper nouns, aggregates across books
   and writes the corpus JSON.
"""
