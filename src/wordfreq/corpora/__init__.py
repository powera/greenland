"""Corpus construction from books, court opinions and Wikipedia.

The corpora built here are word-frequency JSON files consumed by
``wordfreq.frequency.corpus`` / ``wordfreq.frequency.importer``.  Three
builders share the package, one per kind of source:

* ``build_gutenberg`` -- the five Project Gutenberg book lists.
* ``build_scotus`` -- ``legal_scotus``, from Supreme Court opinions.
* ``build_wikipedia`` -- ``wiki_vital`` and ``wiki_math``, from a dump snapshot.

Each has its own text extraction, and they share everything after it:

1. A source module names the documents (``book_lists``,
   ``wikipedia.vital_articles``) or a downloader fetches them
   (``download_gutenberg``, ``download_scotus``).
2. A text module reduces one document to running prose (``gutenberg_text``,
   ``scotus_text``, ``wikipedia.wiki_text``).
3. ``frequency_build`` counts, separates proper nouns, aggregates across
   documents and writes the corpus JSON.

See ``README.md`` for how to run each one.
"""
