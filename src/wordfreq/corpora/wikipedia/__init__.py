"""Wikipedia sources for the ``wiki_*`` corpora.

Driven by :mod:`wordfreq.corpora.build_wikipedia`, which holds the CLI; this
package holds everything that CLI reads.

1. ``article_lists`` loads the YAML lists in ``lists/`` that name the articles
   making up each corpus, and applies the shared redactions.
2. ``wiki_dump`` looks a page up by title in a downloaded Wikimedia snapshot.
3. ``wiki_text`` parses that page's wikitext down to running prose.

The result then goes through the shared
:mod:`wordfreq.corpora.frequency_build`, exactly as the Gutenberg and SCOTUS
corpora do, so proper-noun detection, per-document weighting and the output
format are the same code.

Unlike the other two corpora, the source here is a single large snapshot that
is downloaded by hand rather than fetched per document; there is no
``download_wikipedia`` step.
"""
