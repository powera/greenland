#!/usr/bin/python3

"""Sync derivative forms between per-language release files and SQLite.

Derivative forms live in the ``forms`` array of a lemma's per-language file::

    data/release/lemmas/{pos_type}/{pos_subtype}/{lang_code}.jsonl
    {"guid": "N02_001", "forms": [
        {"grammatical_form": "noun/es_singular", "text": "perro", "is_base_form": true,
         "ipa": "/ˈpe.ro/", "phonetic": null},
        {"grammatical_form": "noun/es_plural", "text": "perros", "is_base_form": false}
    ]}

The routes come from :mod:`barsukas.routes.sync.lang_array_sync`, which the
synonym sync shares.
"""

from barsukas.routes.sync.lang_array_sync import LangArraySpec, build_blueprint

SPEC = LangArraySpec(
    slug="derivatives",
    blueprint_name="sync_derivative_release",
    noun="derivative",
    title="Derivative Forms",
    icon="bi-diagram-3",
    array_key="forms",
    has_base_form=True,
)

bp = build_blueprint(SPEC)
