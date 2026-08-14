"""
Šernas - Synonym and Alternative Form Generator Agent

"Šernas" means "boar" in Lithuanian - persistent in finding similar things.

The agent's workflow now lives in :mod:`words.synonym_workflow` (orchestration)
and :mod:`words.synonym_coverage` (discovery), with the per-lemma generation
pipeline in :mod:`words.synonyms`. This module only keeps the ``SernasAgent``
name working for callers that have not migrated yet.
"""

from words.synonym_workflow import SynonymWorkflow

# Compatibility alias while external callers migrate from the animal name.
SernasAgent = SynonymWorkflow

__all__ = ["SernasAgent", "SynonymWorkflow"]
