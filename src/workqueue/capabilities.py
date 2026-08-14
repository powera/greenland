"""Machine-readable descriptors for workqueue capabilities.

``registry.TASK_HANDLERS`` maps a task type to the callable that runs it, and
nothing more. That is enough for the worker, which is told what to run, but not
for anything that has to *decide* what to run: it cannot tell which capability
applies to an idiom rather than a lemma, which ones write, or what a payload
needs to contain.

This module adds that layer without changing ``TASK_HANDLERS``, which is
consumed elsewhere as a plain name-to-callable mapping. Descriptors are keyed by
canonical task type; legacy aliases are deliberately absent, since a planner
should only ever emit canonical names.

Coverage is currently partial by design - the idiom and sentence capabilities
are described because they were built alongside this module. Adding a descriptor
for an existing capability is a documentation change, and
``undescribed_task_types`` reports what is still missing so the gap stays
visible rather than silently becoming permanent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Tuple


@dataclass(frozen=True)
class CapabilityDescriptor:
    """What one workqueue capability operates on, needs, and produces.

    Attributes:
        task_type: Canonical task type, matching a ``TASK_HANDLERS`` key.
        summary: One line describing what running this does.
        target_kind: The entity the task acts on ("idiom", "lemma", "sentence"),
            or "language" for tasks that act on a language as a whole rather
            than on a specific row.
        required_payload: Payload keys that must be present.
        optional_payload: Payload keys that are honored when present.
        writes: Whether a successful run mutates the database. Read-only
            capabilities are safe to run speculatively; write capabilities are
            not.
        produces: What a successful run leaves behind, phrased so a caller can
            match it against a precondition it is trying to satisfy.
        preconditions: What must already be true for this to do useful work.
    """

    task_type: str
    summary: str
    target_kind: str
    required_payload: Tuple[str, ...] = ()
    optional_payload: Tuple[str, ...] = ()
    writes: bool = True
    produces: Tuple[str, ...] = ()
    preconditions: Tuple[str, ...] = field(default=())


IDIOM_CAPABILITIES: Tuple[CapabilityDescriptor, ...] = (
    CapabilityDescriptor(
        task_type="idioms.generate",
        summary="Propose new idioms in a source language and store them unverified.",
        target_kind="language",
        required_payload=("language_code",),
        optional_payload=("count", "theme", "difficulty_level"),
        writes=True,
        produces=("idiom rows with no equivalents",),
        preconditions=(),
    ),
    CapabilityDescriptor(
        task_type="idioms.equivalents.populate",
        summary="Fill in missing cross-language equivalents for one idiom.",
        target_kind="idiom",
        required_payload=("idiom_id",),
        optional_payload=("idiom_ids", "target_languages", "only_missing"),
        writes=True,
        produces=("idiom_equivalent rows",),
        preconditions=("the idiom has a meaning",),
    ),
    CapabilityDescriptor(
        task_type="idioms.equivalents.validate",
        summary="Audit one idiom's stored equivalents and report problems.",
        target_kind="idiom",
        required_payload=("idiom_id",),
        optional_payload=("idiom_ids",),
        writes=False,
        produces=("findings in the task result, no database change",),
        preconditions=("the idiom has at least one equivalent",),
    ),
)


# The ``produces`` and ``preconditions`` strings below are written to match each
# other across capabilities: a planner satisfies a precondition by finding a
# capability whose ``produces`` names the same thing. "sentence translations in
# the target languages" appears as both, deliberately. Keep new descriptions in
# that vocabulary rather than paraphrasing.
SENTENCE_CAPABILITIES: Tuple[CapabilityDescriptor, ...] = (
    CapabilityDescriptor(
        task_type="sentences.translations.verify",
        summary="Verify one sentence's translations and persist their verdicts.",
        target_kind="sentence",
        required_payload=("sentence_id",),
        optional_payload=("languages", "model"),
        writes=True,
        produces=("sentence translation verification verdicts",),
        preconditions=("the sentence has an English and target-language translation",),
    ),
    CapabilityDescriptor(
        task_type="sentences.links.verify",
        summary="Audit one sentence's stored lemma links and report problems.",
        target_kind="sentence",
        required_payload=("sentence_id",),
        optional_payload=("languages", "model"),
        writes=False,
        produces=("sentence lemma-link findings in the task result",),
        preconditions=("the sentence has linked lemma rows",),
    ),
    CapabilityDescriptor(
        task_type="sentences.import",
        summary=(
            "Run one sentence through the whole import path: translate, decompose, "
            "link words to lemmas, stage the rest, and finalize."
        ),
        target_kind="sentence",
        required_payload=("sentence_id",),
        optional_payload=(
            "target_languages",
            "decompose_languages",
            "annotate_dependencies",
            "auto_promote",
            "max_iterations",
            "model",
            "source",
            "tags",
        ),
        writes=True,
        produces=(
            "sentence translations in the target languages",
            "sentence_word rows with lemma_id set where resolvable",
            "sentence_word_hint rows linking unresolved words to pending imports",
            "sentence minimum_level",
        ),
        preconditions=("the sentence exists and has at least one translation",),
    ),
    CapabilityDescriptor(
        task_type="sentences.import.document",
        summary="Split a document into sentences and queue one import task per sentence.",
        target_kind="language",
        required_payload=(),
        optional_payload=(
            "text",
            "input_path",
            "document_language",
            "source_name",
            "limit",
            "target_languages",
            "decompose_languages",
            "annotate_dependencies",
            "auto_promote",
            "tags",
            "model",
        ),
        writes=True,
        produces=(
            "sentence rows with a source-language translation",
            "one queued sentences.import per sentence",
        ),
        preconditions=("document text is available",),
    ),
    CapabilityDescriptor(
        task_type="sentences.translate",
        summary="Translate one stored sentence into target languages and decompose it.",
        target_kind="sentence",
        required_payload=("sentence_id",),
        optional_payload=("sentence_ids", "selected_languages", "model", "batch"),
        writes=True,
        produces=(
            "sentence translations in the target languages",
            "sentence_word rows for each translated language",
        ),
        preconditions=("the sentence exists and has at least one translation",),
    ),
    CapabilityDescriptor(
        task_type="sentences.translate.batch_submit",
        summary="Submit stored sentences for translation through the batch API.",
        target_kind="sentence",
        required_payload=(),
        optional_payload=("sentence_ids", "selected_languages", "model"),
        writes=True,
        produces=("a submitted batch job, results applied later",),
        preconditions=("the sentences exist and have at least one translation",),
    ),
    CapabilityDescriptor(
        task_type="sentences.batch.translate.submit",
        summary="Submit a sentence translation batch job to the LLM provider.",
        target_kind="sentence",
        required_payload=(),
        optional_payload=("sentence_ids", "selected_languages", "model"),
        writes=True,
        produces=("a submitted batch job, results applied later",),
        preconditions=("the sentences exist and have at least one translation",),
    ),
    CapabilityDescriptor(
        task_type="sentences.batch.decompose.submit",
        summary="Submit a sentence decomposition batch job to the LLM provider.",
        target_kind="sentence",
        required_payload=(),
        optional_payload=("sentence_ids", "selected_languages", "model"),
        writes=True,
        produces=("a submitted batch job, results applied later",),
        preconditions=("sentence translations in the target languages",),
    ),
)


WORD_CAPABILITIES: Tuple[CapabilityDescriptor, ...] = (
    CapabilityDescriptor(
        task_type="words.translations.verify",
        summary="Verify one lemma's translations and persist their verdicts.",
        target_kind="lemma",
        required_payload=("lemma_id",),
        optional_payload=("languages", "model"),
        writes=True,
        produces=("word translation verification verdicts",),
        preconditions=("the lemma has translations in the requested languages",),
    ),
)


CAPABILITY_DESCRIPTORS: Dict[str, CapabilityDescriptor] = {
    descriptor.task_type: descriptor
    for descriptor in (*IDIOM_CAPABILITIES, *SENTENCE_CAPABILITIES, *WORD_CAPABILITIES)
}


def get_descriptor(task_type: str) -> CapabilityDescriptor | None:
    """Return the descriptor for a canonical task type, or None if undescribed."""
    return CAPABILITY_DESCRIPTORS.get(task_type)


def descriptors_for_target(target_kind: str) -> List[CapabilityDescriptor]:
    """Return every described capability that acts on one kind of target."""
    return [
        descriptor
        for descriptor in CAPABILITY_DESCRIPTORS.values()
        if descriptor.target_kind == target_kind
    ]


def undescribed_task_types(task_handlers: Mapping[str, object]) -> List[str]:
    """Return registered task types that have no descriptor yet.

    Takes the handler mapping as an argument rather than importing the registry,
    so this module stays free of the handler import chain and can be used in a
    test that builds its own mapping.
    """
    return sorted(set(task_handlers) - set(CAPABILITY_DESCRIPTORS))
