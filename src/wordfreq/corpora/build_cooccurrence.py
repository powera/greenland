#!/usr/bin/python3

"""Build the verb/noun-subtype co-occurrence artifact from the cached corpora.

    PYTHONPATH=src GREENLAND_TEST_MODE=1 python \\
        src/wordfreq/corpora/build_cooccurrence.py --sources gutenberg
    PYTHONPATH=src GREENLAND_TEST_MODE=1 python \\
        src/wordfreq/corpora/build_cooccurrence.py --sources gutenberg,wikipedia

Reads the locally cached corpus text, counts which noun subtypes follow each
verb, and writes ``data/wordfreq/cooccurrence.json``.  The curriculum uses it
to introduce a verb alongside the words it is actually used with; see
``wordfreq.corpora.cooccurrence`` for what the score means and what it cannot
tell you.

No network.  No LLM.  It reads the database once, for the vocabulary -- which
surface forms are verbs and which are nouns of which subtype -- and writes
nothing back.

Per-source raw counts are cached under ``data/working/cooccurrence/`` so that
re-scoring with different thresholds does not re-tokenize the corpora.  Pass
``--rescan`` to ignore that cache.
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

if str(Path(__file__).parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import constants
from agents.common.common_args import add_backend_args, get_data_source_config
from wordfreq.corpora.cooccurrence import (
    DEFAULT_MIN_PAIR_COUNT,
    DEFAULT_MIN_VERB_COUNT,
    DEFAULT_WINDOW,
    HARDCODED_VERB_LEVELS,
    CooccurrenceCounts,
    count_document,
    excluded_surface_forms,
    score_affinity,
)
from wordfreq.corpora.documents import (
    SOURCE_NAMES,
    gutenberg_documents,
    scotus_documents,
    wikipedia_documents,
)
from wordfreq.corpora.download_gutenberg import default_cache_dir as gutenberg_cache_dir
from wordfreq.corpora.download_scotus import default_cache_dir as scotus_cache_dir
from wordfreq.corpora.gutenberg_text import iter_tokens

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = Path("data/wordfreq/cooccurrence.json")
COUNT_CACHE_DIR = Path("data/working/cooccurrence")

#: How many subtypes to keep per verb in the artifact.  Past the first few the
#: lift is at or below 1.0 and the entry is noise.
TOP_SUBTYPES_PER_VERB = 8


def load_vocabulary(args: argparse.Namespace) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return ``(verbs, nouns)`` as ``surface form -> pos_subtype``.

    Only leveled lemmas are considered: a word with no curriculum level is not
    something a named unit can be built around.  Where a surface form has
    several senses the first is kept -- the counts cannot tell senses apart
    anyway, which is the homograph caveat the module docstring records.
    """
    from storage.backend import create_session
    from storage.models.schema import Lemma

    session = create_session(get_data_source_config(args))
    try:
        verbs: Dict[str, str] = {}
        nouns: Dict[str, str] = {}
        rows = (
            session.query(Lemma.lemma_text, Lemma.pos_type, Lemma.pos_subtype)
            .filter(Lemma.difficulty_level.isnot(None))
            .filter(Lemma.difficulty_level > 0)
            .all()
        )
        for lemma_text, pos_type, pos_subtype in rows:
            if not lemma_text or not pos_subtype:
                continue
            target = verbs if pos_type == "verb" else nouns if pos_type == "noun" else None
            if target is None:
                continue
            target.setdefault(lemma_text.lower(), pos_subtype)
        return verbs, nouns
    finally:
        session.close()


def _cache_path(source: str, window: int) -> Path:
    """Where one source's raw counts live, keyed by the window they used."""
    return COUNT_CACHE_DIR / f"{source}-w{window}.json"


def _counts_to_json(counts: CooccurrenceCounts) -> Dict[str, object]:
    return {
        "verb_totals": dict(counts.verb_totals),
        "pair_counts": {verb: dict(pairs) for verb, pairs in counts.pair_counts.items()},
        "subtype_totals": dict(counts.subtype_totals),
        "documents_scanned": counts.documents_scanned,
    }


def _counts_from_json(payload: Any) -> CooccurrenceCounts:
    """Rebuild counts from a cache file.

    The argument is ``Any`` because it is whatever ``json.loads`` returned:
    the shape is asserted here rather than assumed, so a cache file written by
    an older version fails loudly instead of half-loading.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"Cached counts must be a JSON object, got {type(payload).__name__}")

    counts = CooccurrenceCounts()
    counts.verb_totals = Counter(payload.get("verb_totals") or {})
    counts.pair_counts = {
        verb: Counter(pairs) for verb, pairs in (payload.get("pair_counts") or {}).items()
    }
    counts.subtype_totals = Counter(payload.get("subtype_totals") or {})
    counts.documents_scanned = int(payload.get("documents_scanned") or 0)
    return counts


def scan_source(
    source: str,
    verbs: Mapping[str, str],
    nouns: Mapping[str, str],
    *,
    window: int,
    gutenberg_dir: Path,
    scotus_dir: Path,
    limit: Optional[int] = None,
) -> Optional[CooccurrenceCounts]:
    """Tokenize one source and count it, or return None when it is absent."""
    if source == "gutenberg":
        if not gutenberg_dir.exists():
            logger.warning("Gutenberg cache not found at %s, skipping", gutenberg_dir)
            return None
        documents = gutenberg_documents(gutenberg_dir)
    elif source == "scotus":
        if not scotus_dir.exists():
            logger.warning("SCOTUS cache not found at %s, skipping", scotus_dir)
            return None
        documents = scotus_documents(scotus_dir)
    elif source == "wikipedia":
        if not Path(constants.WIKI_CORPUS_BASE_PATH).exists():
            logger.warning(
                "Wikipedia snapshot not mounted at %s, skipping",
                constants.WIKI_CORPUS_BASE_PATH,
            )
            return None
        documents = wikipedia_documents()
    else:
        raise ValueError(f"Unknown source: {source}")

    excluded = excluded_surface_forms()
    counts = CooccurrenceCounts()
    for index, (slug, text) in enumerate(documents):
        if limit is not None and index >= limit:
            break
        tokens = [token for token, _capitalized, _initial in iter_tokens(text)]
        count_document(tokens, verbs, nouns, counts, window=window, excluded=excluded)
        if counts.documents_scanned % 500 == 0:
            logger.info("%s: %s documents", source, counts.documents_scanned)
    logger.info("%s: %s documents scanned", source, counts.documents_scanned)
    return counts


def build_payload(
    counts: CooccurrenceCounts,
    *,
    sources: Sequence[str],
    window: int,
    min_verb_count: int,
    min_pair_count: int,
) -> Dict[str, object]:
    """Score the counts and assemble the JSON artifact."""
    scored = score_affinity(counts, min_verb_count=min_verb_count, min_pair_count=min_pair_count)
    verbs_payload: Dict[str, object] = {}
    for verb, affinities in sorted(scored.items()):
        verbs_payload[verb] = {
            "occurrences": counts.verb_totals.get(verb, 0),
            "subtypes": [
                {
                    "subtype": affinity.subtype,
                    "count": affinity.count,
                    "share": round(affinity.share, 4),
                    "lift": round(affinity.lift, 3),
                }
                for affinity in affinities[:TOP_SUBTYPES_PER_VERB]
            ],
        }

    return {
        "version": 1,
        "sources": list(sources),
        "window": window,
        "documents_scanned": counts.documents_scanned,
        "min_verb_count": min_verb_count,
        "min_pair_count": min_pair_count,
        # Recorded in the artifact so a consumer cannot mistake the absence of
        # these verbs for "no evidence found". They are placed by hand.
        "hardcoded_verbs": dict(HARDCODED_VERB_LEVELS),
        "caveat": (
            "Matching is on surface form, so noun and verb senses of one "
            "spelling are conflated (work, play, call). Evidence for a human "
            "decision, not an assignment."
        ),
        "verbs": verbs_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_backend_args(parser)
    parser.add_argument(
        "--sources",
        default="gutenberg",
        help=f"Comma-separated sources to scan from {SOURCE_NAMES} (default: gutenberg)",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=DEFAULT_WINDOW,
        help=f"Tokens after a verb that count as its window (default: {DEFAULT_WINDOW})",
    )
    parser.add_argument(
        "--min-verb-count",
        type=int,
        default=DEFAULT_MIN_VERB_COUNT,
        help=f"Occurrences before a verb is scored (default: {DEFAULT_MIN_VERB_COUNT})",
    )
    parser.add_argument(
        "--min-pair-count",
        type=int,
        default=DEFAULT_MIN_PAIR_COUNT,
        help=f"Occurrences before a pairing is scored (default: {DEFAULT_MIN_PAIR_COUNT})",
    )
    parser.add_argument(
        "--gutenberg-dir", type=Path, default=None, help="Override the Gutenberg cache directory"
    )
    parser.add_argument(
        "--scotus-dir", type=Path, default=None, help="Override the SCOTUS cache directory"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Scan at most this many documents per source"
    )
    parser.add_argument("--rescan", action="store_true", help="Ignore the cached per-source counts")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sources = [name.strip() for name in args.sources.split(",") if name.strip()]
    unknown = [name for name in sources if name not in SOURCE_NAMES]
    if unknown:
        parser.error(f"Unknown source(s): {', '.join(unknown)}. Choose from {SOURCE_NAMES}.")

    verbs, nouns = load_vocabulary(args)
    logger.info("Vocabulary: %s verbs, %s nouns", len(verbs), len(nouns))

    gutenberg_dir = args.gutenberg_dir or gutenberg_cache_dir()
    scotus_dir = args.scotus_dir or scotus_cache_dir()

    combined = CooccurrenceCounts()
    scanned_any = False
    for source in sources:
        cache_path = _cache_path(source, args.window)
        # The limit makes a partial scan, which must never be cached as if it
        # were the whole source.
        use_cache = cache_path.exists() and not args.rescan and args.limit is None
        if use_cache:
            logger.info("%s: reading cached counts from %s", source, cache_path)
            counts: Optional[CooccurrenceCounts] = _counts_from_json(
                json.loads(cache_path.read_text(encoding="utf-8"))
            )
        else:
            counts = scan_source(
                source,
                verbs,
                nouns,
                window=args.window,
                gutenberg_dir=gutenberg_dir,
                scotus_dir=scotus_dir,
                limit=args.limit,
            )
            if counts is not None and args.limit is None:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(_counts_to_json(counts), ensure_ascii=False), encoding="utf-8"
                )
        if counts is None:
            continue
        combined.merge(counts)
        scanned_any = True

    if not scanned_any:
        logger.error("No source produced any counts; nothing written.")
        return 1

    payload = build_payload(
        combined,
        sources=sources,
        window=args.window,
        min_verb_count=args.min_verb_count,
        min_pair_count=args.min_pair_count,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Wrote %s: %s verbs scored from %s documents",
        args.output,
        len(payload["verbs"]),  # type: ignore[arg-type]
        combined.documents_scanned,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
