#!/usr/bin/python3

"""What element types ``data/release`` holds, and how each one moves.

One entry per element type, naming its subdirectory under the release root and
the callables that move it in each direction. The CLI dispatches over this
instead of carrying a branch per (entity, direction) pair, and the Barsukas
sync blueprints read their directory and display name from the same entry, so
the two cannot disagree about where an idiom lives or what to call it.

This is a table of file locations and functions, not a domain abstraction: it
adds no adapter over the ORM, hides no querying, and gives no element type a
shared base class. Each module beside it stays hand-written, and an entry is
just a way to name what that module already does. (Compare
``docs/element_types_design.md``, which argues against a registry over the
*models* -- a different layer, and one this does not touch.)

**Not exhaustive over data/release.** Three subdirectories have no entry
because no element module owns them: ``audio_reviews/``, ``operation_logs/``
and ``verifications/`` are written only by the JSONL backend, and reach the
CLI through the whole-database ``database`` pseudo-entity instead.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from storage.release import idiom, lemma, lemma_audio, name, phrase, sentence, tombstone

#: A direction's worth of work: ``(session, release_dir, **options) -> stats``.
#: The stats object differs per element type; callers print it rather than
#: inspect it, so the registry does not constrain its shape.
ReleaseCallable = Callable[..., Any]


@dataclass(frozen=True)
class ReleaseEntitySpec:
    """How one element type moves between the database and ``data/release``."""

    #: CLI token and registry key, e.g. ``"lemma-audio"``.
    name: str
    #: Directory under the release root. Not unique: lemma audio writes
    #: ``audio.jsonl`` inside the lemma tree, so it shares ``lemmas``.
    subdir: str
    #: Singular noun for messages, e.g. ``"idiom"``.
    noun: str
    #: Database -> release files, or None where no exporter exists.
    export: Optional[ReleaseCallable] = None
    #: Release files -> database, or None where no importer exists.
    import_: Optional[ReleaseCallable] = None
    #: Whether ``--category`` may scope this element type.
    accepts_categories: bool = False
    #: Whether ``--prune`` may delete rows the files no longer list.
    accepts_prune: bool = False

    def supports(self, direction: str) -> bool:
        """Whether this element type can move in ``direction``."""
        return (self.export if direction == "export" else self.import_) is not None

    def callable_for(self, direction: str) -> ReleaseCallable:
        """The callable for ``direction``; call only when :meth:`supports`."""
        chosen = self.export if direction == "export" else self.import_
        if chosen is None:
            raise ValueError(f"{self.name} does not support {direction}")
        return chosen

    def release_dir(self, release_root: Path) -> Path:
        """This element type's directory under ``release_root``."""
        return Path(release_root) / self.subdir


#: Every element type the release CLI knows, keyed by CLI token.
#:
#: Ordered as a full export runs: lemmas first because everything else refers
#: to them by GUID, tombstones last because they record what the others no
#: longer contain.
ENTITY_SPECS: Dict[str, ReleaseEntitySpec] = {
    "lemmas": ReleaseEntitySpec(
        name="lemmas",
        subdir="lemmas",
        noun="lemma",
        export=lemma.export_to_release,
        # Lemmas are imported by the whole-database load rather than one at a
        # time; there is no per-element importer to point at yet.
    ),
    "sentences": ReleaseEntitySpec(
        name="sentences",
        subdir="sentences",
        noun="sentence",
        export=sentence.export_to_release,
        # Sentences themselves are imported by the whole-database load; only
        # their inline audio has a per-element importer (see sentence.py).
        import_=sentence.import_audio_from_release,
    ),
    "phrases": ReleaseEntitySpec(
        name="phrases",
        subdir="phrases",
        noun="phrase",
        export=phrase.export_to_release,
    ),
    "idioms": ReleaseEntitySpec(
        name="idioms",
        subdir="idioms",
        noun="idiom",
        export=idiom.export_to_release,
        import_=idiom.import_from_release,
    ),
    "names": ReleaseEntitySpec(
        name="names",
        subdir="names",
        noun="name",
        export=name.export_to_release,
        import_=name.import_from_release,
    ),
    "lemma-audio": ReleaseEntitySpec(
        name="lemma-audio",
        subdir="lemmas",
        noun="lemma audio record",
        export=lemma_audio.export_to_release,
        import_=lemma_audio.import_from_release,
        accepts_categories=True,
        accepts_prune=True,
    ),
    "tombstones": ReleaseEntitySpec(
        name="tombstones",
        subdir=tombstone.RELEASE_DIRNAME,
        noun="tombstone",
        export=tombstone.export_to_release,
        import_=tombstone.import_from_release,
    ),
}


def specs_for(direction: str, names: Optional[Any] = None) -> list[ReleaseEntitySpec]:
    """Resolve CLI entity tokens to specs, in registry order.

    ``names`` of None (or containing ``"all"``) selects every element type that
    supports ``direction``, skipping the rest rather than failing: coverage is
    deliberately asymmetric, so ``export all`` and ``import all`` should both
    work and widen on their own as importers are added.
    """
    if names is None or "all" in names:
        return [spec for spec in ENTITY_SPECS.values() if spec.supports(direction)]

    chosen: list[ReleaseEntitySpec] = []
    for token in names:
        spec = ENTITY_SPECS.get(token)
        if spec is None:
            raise KeyError(f"unknown element type {token!r}")
        if not spec.supports(direction):
            raise ValueError(f"{token!r} does not support {direction}")
        chosen.append(spec)
    return chosen
