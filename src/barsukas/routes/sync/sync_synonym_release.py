#!/usr/bin/python3

"""Sync synonym entries between per-language release files and SQLite.

Synonyms live in the ``synonyms`` array of a lemma's per-language file, beside
the inflections in ``forms``::

    {"guid": "N02_001", "synonyms": [
        {"grammatical_form": "synonym", "text": "bicycle"},
        {"grammatical_form": "abbreviation", "text": "bike"}
    ]}

They are kept separate from inflections because the same ``grammatical_form``
can repeat for one lemma, and because a synonym has no base form. The routes
come from :mod:`barsukas.routes.sync.lang_array_sync`, which the derivative
sync shares.
"""

from barsukas.routes.sync.lang_array_sync import LangArraySpec, build_blueprint

SPEC = LangArraySpec(
    slug="synonyms",
    blueprint_name="sync_synonym_release",
    noun="synonym",
    title="Synonyms",
    icon="bi-link-45deg",
    array_key="synonyms",
    has_base_form=False,
)

bp = build_blueprint(SPEC)
