#!/usr/bin/python3

"""Check article-list titles against the snapshot they will be built from.

A list in ``lists/`` stores titles under their *snapshot* spelling, because
:mod:`wordfreq.corpora.wikipedia.wiki_dump` looks a page up by exact title and
a redirect is a miss.  Upstream keeps renaming articles, so a list transcribed
from a current vital-articles page names some pages the snapshot does not have.

This module answers two questions about a set of titles:

* Which ones does the snapshot not have at all (:func:`check_titles`)?  This
  needs only the offset index, so it runs without the 21GB dump mounted.
* For a title the snapshot *does* have, is it a redirect rather than an article
  (:func:`resolve_redirect`)?  This reads the dump, so the snapshot must be
  mounted.

The two are separate because they cost different things and are wanted at
different times: the missing-title check is what a list build reports every
time, while redirect resolution is a one-off done when curating a new list.

Nothing here writes a list file.  A resolution is a judgement -- "Mon-Burmese
script" could reasonably map to either "Burmese alphabet" or "Mon script" --
so the tool reports what the snapshot contains and a person decides, the same
way the ``->`` notes in each list's header were arrived at.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

import constants
from wordfreq.corpora.wikipedia.wiki_dump import WikiLoader

# ``#REDIRECT [[Target]]``, optionally with a "|label" or "#section" suffix.
_REDIRECT_RE = re.compile(r"\s*#\s*REDIRECT\s*\[\[([^\]|#]+)", re.IGNORECASE)

# The offset index is small and lives in the repo; the dump it indexes is 21GB
# and usually sits on an external drive.  Checking titles needs only the index.
DEFAULT_OFFSET_DIR = os.path.join(constants.PROJECT_ROOT, "data", "working", "wiki_offset")


def make_loader(offset_dir: Optional[str] = None) -> WikiLoader:
    """A loader pointed at the local offset index.

    Args:
        offset_dir: Where the sharded index lives.  Defaults to the in-repo
            ``data/working/wiki_offset``, which is where it is built.
    """
    return WikiLoader(offset_dir=offset_dir or DEFAULT_OFFSET_DIR)


def title_exists(title: str, loader: WikiLoader) -> bool:
    """Whether the snapshot has a page under exactly this title."""
    try:
        loader.get_offset_for_page(title)
    except ValueError:
        return False
    return True


@dataclass
class TitleReport:
    """What a snapshot has to say about one set of titles."""

    checked: int = 0
    missing: List[str] = field(default_factory=list)

    @property
    def found(self) -> int:
        return self.checked - len(self.missing)

    def summary(self) -> str:
        if not self.missing:
            return f"all {self.checked} titles resolve against the snapshot"
        return f"{self.found}/{self.checked} titles resolve; {len(self.missing)} missing"


def check_titles(titles: Iterable[str], loader: Optional[WikiLoader] = None) -> TitleReport:
    """Report which of ``titles`` the snapshot does not have.

    Uses the offset index only, so this runs whether or not the dump itself is
    mounted.  A missing title is not necessarily wrong -- it may have been
    renamed since the snapshot, in which case :func:`resolve_redirect` and a
    human decide what it was called then.
    """
    active = loader or make_loader()
    report = TitleReport()
    for title in titles:
        report.checked += 1
        if not title_exists(title, active):
            report.missing.append(title)
    return report


def check_groups(
    groups: Dict[str, Sequence[str]], loader: Optional[WikiLoader] = None
) -> Dict[str, List[str]]:
    """Per-group missing titles, keeping only the groups that have some.

    Grouping matters when curating: five misses in one section usually means
    the section was renamed upstream, not that five articles vanished.
    """
    active = loader or make_loader()
    out: Dict[str, List[str]] = {}
    for group, titles in groups.items():
        missing = [t for t in titles if not title_exists(t, active)]
        if missing:
            out[group] = missing
    return out


@dataclass(frozen=True)
class Resolution:
    """What the snapshot holds at one title."""

    title: str
    exists: bool
    redirect_target: Optional[str]
    size: Optional[int]

    @property
    def is_article(self) -> bool:
        """Present, and not a redirect to somewhere else."""
        return self.exists and self.redirect_target is None


def resolve_redirect(title: str, loader: Optional[WikiLoader] = None) -> Resolution:
    """Read ``title`` from the snapshot and say whether it redirects.

    Requires the dump to be mounted; :func:`check_titles` does not.  A title
    that is present but redirects should be stored in the list under its
    *target*, since a build resolves nothing.

    Returns:
        A :class:`Resolution`.  ``size`` is the wikitext length, which is how
        a substantive article is told from a stub when two candidate targets
        both exist.
    """
    active = loader or make_loader()
    if not title_exists(title, active):
        return Resolution(title=title, exists=False, redirect_target=None, size=None)
    text = active.get_text_from_page(title)
    match = _REDIRECT_RE.match(text)
    return Resolution(
        title=title,
        exists=True,
        redirect_target=match.group(1).strip() if match else None,
        size=len(text),
    )


def resolve_candidates(
    candidates: Iterable[str], loader: Optional[WikiLoader] = None
) -> List[Resolution]:
    """Resolve several possible snapshot spellings for one renamed title.

    The usual curation step: upstream renamed "Personal pronouns in English",
    and the snapshot might hold it as "English personal pronouns" or
    "English pronouns".  Resolving both shows which exist, which are
    redirects, and how big each is, which is enough to choose.
    """
    active = loader or make_loader()
    return [resolve_redirect(candidate, active) for candidate in candidates]
