"""Smoke tests: the tree imports.

Every test here is marked ``smoke`` and is meant to run on every commit. They
assert only that modules load, which is deliberately shallow -- the point is to
catch the failure this repo actually keeps hitting, where a module or package is
moved and something that referenced it by name is not updated. Import errors and
stale ``mock.patch`` target strings both surface here long before the slower
behavioral tests get a chance to run.

Keep this file fast and dependency-light. Anything that needs a database, an
LLM client, or fixtures belongs in the base suite instead.
"""

import importlib
import pkgutil
from pathlib import Path
from typing import List

import pytest

pytestmark = pytest.mark.smoke

SRC = Path(__file__).resolve().parent.parent


def _module_names(package_dir: str, prefix: str) -> List[str]:
    """Return importable ``prefix.<name>`` modules directly under package_dir."""
    root = SRC / package_dir
    return sorted(f"{prefix}.{p.stem}" for p in root.glob("*.py") if p.stem != "__init__")


def test_agent_modules_import() -> None:
    """Every agent CLI module imports.

    Agents are entry points run by hand, so a broken import here would otherwise
    only be discovered when someone tries to run that agent.
    """
    failures = []
    for name in _module_names("agents", "agents"):
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - report all, not just the first
            failures.append(f"{name}: {type(exc).__name__}: {exc}")

    assert not failures, "Agent modules failed to import:\n  " + "\n  ".join(failures)


@pytest.mark.parametrize(
    "module",
    [
        "agents.papuga.cli",
        "barsukas.app",
        # benchmarks.lib.utils eagerly pulls in every runner, generator and the
        # registry, so this one name covers the whole benchmarks import graph --
        # including the optional-native-dep guards (jieba, pypinyin) that keep it
        # collectable in environments where those wheels are not installed.
        "benchmarks.lib.utils",
        "clients.unified_client",
        "storage.models.schema",
        "storage.translation_helpers",
        "storage.backend.config",
        "langtools.form_registry",
        "wordfreq.frequency.combined_rank",
        "workqueue.task_queue",
    ],
)
def test_core_module_imports(module: str) -> None:
    """Core modules that most of the tree depends on import cleanly."""
    assert importlib.import_module(module) is not None


def test_tokenizer_language_hooks_resolve() -> None:
    """Every tier 1/2 lemma-matching module loads, and one lookup works.

    langtools.tokenizer finds ``langtools.<lang>.tokenizer`` by building the
    name as a string, so importing the dispatcher alone proves nothing about
    the language modules -- a renamed or broken one would silently fall back
    to exact matching.  One call per language forces the import.
    """
    from langtools.tokenizer import lemma_lookup_keys, supports_lemma_candidates
    from storage.translation_helpers import TIER_1_LANGUAGES, TIER_2_LANGUAGES

    missing = [
        code for code in TIER_1_LANGUAGES + TIER_2_LANGUAGES if not supports_lemma_candidates(code)
    ]
    assert not missing, f"No candidate_lemmas hook for: {missing}"
    assert "canción" in lemma_lookup_keys("es", "canciones")


def test_storage_package_fully_imports() -> None:
    """Every module under storage/ imports.

    storage is the schema layer nearly everything else builds on, so a partial
    import failure here tends to surface far from its cause.
    """
    import storage

    failures = []
    for info in pkgutil.walk_packages(storage.__path__, prefix="storage."):
        try:
            importlib.import_module(info.name)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{info.name}: {type(exc).__name__}: {exc}")

    assert not failures, "storage modules failed to import:\n  " + "\n  ".join(failures)
