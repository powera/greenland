#!/usr/bin/python3

"""Loading the Wikipedia article lists that define the ``wiki_*`` corpora.

The lists themselves are data, not code, and live in ``lists/`` as YAML:
several thousand article titles, which as Python source made
``vital_articles.py`` one of the longest files in the tree without any of it
being logic.  YAML rather than JSON because the provenance of a list is worth
keeping beside it -- which titles were dropped, which were renamed between the
2026 upstream revision and the 2022 snapshot, and why a title was deliberately
excluded -- and JSON cannot hold a comment.

Each file carries:

* ``source`` -- the upstream page the titles came from.
* ``snapshot`` -- the dump the titles were resolved against.  A title renamed
  since then is stored under its snapshot spelling, because
  :mod:`wordfreq.corpora.wikipedia.wiki_dump` looks a page up by exact title
  and a redirect is a miss.
* ``groups`` -- the titles, under the section names the upstream page uses.
  The grouping is how a gap in coverage is spotted; the corpus builder
  flattens it.

``lists/redactions.yaml`` names titles kept out of every list, with the reason.
These are not resolver failures: a title with no snapshot article is reported
as missing when the list is built and noted in that list's own header.  A
redaction is a title that resolves fine and is still unwanted -- most often
because the 2022 snapshot predates its subject, so the article is a stub about
something that had not happened yet.  Filtering here rather than by deleting
lines means a re-fetch of an upstream page cannot quietly reintroduce one.
"""

import functools
import os
from typing import Dict, List

import yaml

LISTS_DIR = os.path.join(os.path.dirname(__file__), "lists")
REDACTIONS_FILE = "redactions.yaml"


@functools.lru_cache(maxsize=1)
def load_redactions() -> Dict[str, str]:
    """Titles excluded from every list, mapped to the reason they were cut."""
    path = os.path.join(LISTS_DIR, REDACTIONS_FILE)
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return dict(data.get("redactions") or {})


@functools.lru_cache(maxsize=None)
def load_list(name: str) -> Dict[str, List[str]]:
    """Load one article list by file stem, e.g. ``"arts"``.

    Args:
        name: The file stem under ``lists/``, without the ``.yaml``.

    Returns:
        Article titles grouped by the upstream page's section names, with any
        redacted title removed.  Ordering follows the file, which follows the
        upstream page.

    Raises:
        FileNotFoundError: If no such list file exists.
        ValueError: If the file has no ``groups`` mapping.
    """
    path = os.path.join(LISTS_DIR, f"{name}.yaml")
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    groups = (data or {}).get("groups")
    if not isinstance(groups, dict):
        raise ValueError(f"{path}: no 'groups' mapping")

    redactions = load_redactions()
    out: Dict[str, List[str]] = {}
    for group, titles in groups.items():
        kept = [title for title in (titles or []) if title not in redactions]
        if kept:
            out[group] = kept
    return out


def load_lists(*names: str, prefix_groups: bool = False) -> Dict[str, List[str]]:
    """Load and merge several lists into one set of groups.

    Args:
        *names: File stems to load, in order.
        prefix_groups: Prefix each group name with the list it came from.
            Use this when merging lists whose section names would otherwise
            collide or lose their provenance, as ``wiki_modern_life`` does.

    Returns:
        The merged groups, in the order the lists were given.
    """
    merged: Dict[str, List[str]] = {}
    for name in names:
        for group, titles in load_list(name).items():
            key = f"{name}: {group}" if prefix_groups else group
            merged.setdefault(key, []).extend(titles)
    return merged


def flatten(groups: Dict[str, List[str]]) -> List[str]:
    """Every title in ``groups``, in order, without duplicates.

    A title can legitimately appear in two groups of a merged list; the corpus
    counts an article once however many groups name it.
    """
    seen: set = set()
    out: List[str] = []
    for titles in groups.values():
        for title in titles:
            if title not in seen:
                seen.add(title)
                out.append(title)
    return out
