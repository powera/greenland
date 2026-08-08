"""Release-file serialization for linguistic elements.

Each module here owns the mapping between one element type's ORM rows and its
``data/release`` JSONL records, in both directions, with no Flask or CLI
dependency. The Barsukas sync blueprints and the ``storage.migrate`` CLI both
call into these so a record is built in exactly one place.
"""
