"""HTTP facade for the lemma tag endpoints.

Tags are free-form labels on a lemma (``["legal", "archaic"]``). Corpus
ingestion applies them in bulk without a human in the loop, so these calls exist
to review the result afterwards: list what a run produced, then hard-delete the
tags that do not belong.

Mirrors ``src/barsukas/routes/api/tag_routes.py``. Any change to a route
signature or response shape there must be reflected here in the same commit.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, TypedDict, cast

from api._http import delete_json, get_json, post_json
from api._mirror import mirrored_route
from api.constants import API_V1_PREFIX


class TagCount(TypedDict):
    tag: str
    lemma_count: int


class TagListResponse(TypedDict):
    data: List[TagCount]
    metadata: Dict[str, object]


class TaggedLemma(TypedDict):
    guid: str
    lemma_text: str
    definition: str
    pos_type: str
    tags: List[str]


class TaggedLemmaListResponse(TypedDict):
    data: List[TaggedLemma]
    metadata: Dict[str, object]


class LemmaTags(TypedDict):
    guid: str
    tags: List[str]


class LemmaTagsResponse(TypedDict, total=False):
    data: LemmaTags
    metadata: Dict[str, object]


@mirrored_route("/api/v1/tags", "GET")
def list_tags(*, base_url: Optional[str] = None) -> TagListResponse:
    """List every tag in use, with the number of lemmas carrying each."""
    return cast(
        TagListResponse,
        get_json(f"{API_V1_PREFIX}/tags", base_url=base_url),
    )


@mirrored_route("/api/v1/tags/<tag>", "GET")
def lemmas_for_tag(tag: str, *, base_url: Optional[str] = None) -> TaggedLemmaListResponse:
    """List the lemmas carrying ``tag`` -- the review sweep after a corpus run."""
    return cast(
        TaggedLemmaListResponse,
        get_json(f"{API_V1_PREFIX}/tags/{tag}", base_url=base_url),
    )


@mirrored_route("/api/v1/lemma/<guid>/tags", "GET")
def get_lemma_tags(guid: str, *, base_url: Optional[str] = None) -> LemmaTagsResponse:
    """Return the tags on one lemma."""
    return cast(
        LemmaTagsResponse,
        get_json(f"{API_V1_PREFIX}/lemma/{guid}/tags", base_url=base_url),
    )


@mirrored_route("/api/v1/lemma/<guid>/tags", "POST")
def add_lemma_tags(
    guid: str, tags: Sequence[str], *, base_url: Optional[str] = None
) -> LemmaTagsResponse:
    """Add ``tags`` to a lemma, keeping any already present.

    Tags are free-form, so an unrecognized tag is stored rather than rejected.
    Adding a tag the lemma already carries is a no-op.
    """
    return cast(
        LemmaTagsResponse,
        post_json(
            f"{API_V1_PREFIX}/lemma/{guid}/tags",
            {"tags": list(tags)},
            base_url=base_url,
        ),
    )


@mirrored_route("/api/v1/lemma/<guid>/tags", "DELETE")
def remove_lemma_tags(
    guid: str, tags: Sequence[str], *, base_url: Optional[str] = None
) -> LemmaTagsResponse:
    """Hard-delete ``tags`` from a lemma.

    The tags are removed outright rather than flagged; the operation log keeps
    the record. Removing a tag the lemma does not carry is a no-op.
    """
    return cast(
        LemmaTagsResponse,
        delete_json(
            f"{API_V1_PREFIX}/lemma/{guid}/tags",
            {"tags": list(tags)},
            base_url=base_url,
        ),
    )
