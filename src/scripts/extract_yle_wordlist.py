#!/usr/bin/env python3
"""Extract Cambridge YLE (Pre A1 Starters / A1 Movers / A2 Flyers) wordlists from the
official PDF into a structured JSON.

Input PDF (download separately; lives outside source control):
    data/working/cambridge_yle/yle-flyers-word-list.pdf

Output JSON:
    data/working/cambridge_yle/yle_wordlist.json

The JSON has the shape:
    {
      "entries": [
        {
          "word": "apple",
          "pos": ["n"],
          "level": "starters",            # starters | movers | flyers
          "variants": {"UK": null, "US": null},
          "sense": null,                  # e.g. "as in a ball"
          "themes": ["Food & drink"]
        },
        ...
      ],
      "themes": { "Animals": ["animal", "bear", ...], ... },
      "by_level": { "starters": [...], "movers": [...], "flyers": [...] }
    }

Usage:
    PYTHONPATH=src python src/scripts/extract_yle_wordlist.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pdfplumber

PDF_PATH = Path("data/working/cambridge_yle/yle-flyers-word-list.pdf")
OUT_PATH = Path("data/cambridge/yle_wordlist.json")

# Per-level alphabetic wordlists (0-indexed inclusive ranges).
# Starters: pages 4-7, Movers: 8-11, Flyers: 12-16 (per the contents page).
LEVEL_PAGE_RANGES: Dict[str, Tuple[int, int]] = {
    "starters": (3, 6),   # pages 4-7
    "movers": (7, 10),    # pages 8-11
    "flyers": (11, 15),   # pages 12-16
}

# Thematic vocabulary list: pages 38-43 (0-indexed 37-42).
THEMATIC_PAGE_RANGE: Tuple[int, int] = (37, 42)

VALID_POS = {
    "adj", "adv", "conj", "det", "dis", "excl", "int",
    "n", "poss", "prep", "pron", "v", "title",
}

# Line that starts a letter section ("A", "B", ..., "Z") — a single uppercase letter.
LETTER_LINE_RE = re.compile(r"^[A-Z]$")

# Footer lines to skip in alphabetic pages (e.g. "Pre A1 Starters A–Z wordlist 4").
FOOTER_RES = [
    re.compile(r"A–Z wordlist\s+\d+$"),
    re.compile(r"alphabetic vocabulary list\s+\d+$"),
    re.compile(r"grammatical vocabulary list\s+\d+$"),
    re.compile(r"thematic vocabulary list\s+\d+$"),
    re.compile(r"^Grammatical key"),
    re.compile(r"^(adj|adv|conj|det|dis|excl|int|n|poss|prep|pron|v)\s+[a-z]"),  # key rows
]

HEADER_LINES = {
    "Pre A1 Starters A–Z wordlist",
    "A1 Movers A–Z wordlist",
    "A2 Flyers A–Z wordlist",
    "Pre A1 Starters and A1 Movers",
    "alphabetic vocabulary list",
    "Pre A1 Starters, A1 Movers and A2 Flyers",
    "grammatical vocabulary list",
    "thematic vocabulary list",
    "Grammatical key",
}


@dataclass
class Entry:
    word: str
    pos: List[str] = field(default_factory=list)
    level: str = ""
    variants: Dict[str, Optional[str]] = field(default_factory=lambda: {"UK": None, "US": None})
    sense: Optional[str] = None
    themes: List[str] = field(default_factory=list)

    def key(self) -> Tuple[str, Optional[str]]:
        return (self.word.lower(), self.sense.lower() if self.sense else None)


# --------------------------------------------------------------------------
# Parsing: per-level A–Z wordlists
# --------------------------------------------------------------------------


def _strip_footer_and_headers(lines: List[str]) -> List[str]:
    out: List[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s in HEADER_LINES:
            continue
        if any(r.search(s) for r in FOOTER_RES):
            continue
        out.append(s)
    return out


def _iter_entries_in_text(text: str) -> List[str]:
    """Yield raw entry strings from a block of multi-column text.

    Each entry ends with one of the POS tokens (possibly "adj + n", "n + v",
    etc.).  We tokenize the stream and split on POS boundaries, attaching any
    immediately-following "+ POS" additions.

    The per-level alphabetic pages are laid out as 3 or 4 columns; pdfplumber's
    default extract_text concatenates columns row-by-row, but each word entry
    always contains its POS, so we can recover entries by POS-based splitting.
    """
    # Normalise whitespace, but keep content as a single stream.
    stream = re.sub(r"\s+", " ", text).strip()
    tokens = stream.split(" ")

    entries: List[str] = []
    current: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        current.append(tok)
        if tok in VALID_POS:
            # Accept trailing "+ pos" chains, e.g., "n + v", "adj + adv + det + pron".
            while i + 2 < len(tokens) and tokens[i + 1] == "+" and tokens[i + 2] in VALID_POS:
                current.append(tokens[i + 1])
                current.append(tokens[i + 2])
                i += 2
            # Absorb preposition-sense qualifiers: "at prep of place",
            # "in prep of place + time", "on adv + prep of time".
            # The chain may end on `prep` even if it started with `adv`.
            last_pos = current[-1] if current else tok
            if last_pos == "prep" and i + 2 < len(tokens) and tokens[i + 1] == "of" \
                    and tokens[i + 2] in {"place", "time"}:
                current.append(tokens[i + 1])
                current.append(tokens[i + 2])
                i += 2
                while i + 2 < len(tokens) and tokens[i + 1] == "+" \
                        and tokens[i + 2] in {"place", "time"}:
                    current.append(tokens[i + 1])
                    current.append(tokens[i + 2])
                    i += 2
            entries.append(" ".join(current).strip())
            current = []
        i += 1
    # Anything left in `current` is trailing garbage (e.g., "x-ray n" split
    # across a page boundary); we ignore it here — it will appear on the next
    # page.
    return entries


_ENTRY_RE = re.compile(
    r"""^
    (?P<word>.+?)                          # word (non-greedy, may contain spaces)
    (?:\s*\((?P<paren>[^)]+)\))?           # optional parenthetical
    \s+
    (?P<pos>(?:adj|adv|conj|det|dis|excl|int|n|poss|prep|pron|v|title)
            (?:\s*\+\s*(?:adj|adv|conj|det|dis|excl|int|n|poss|prep|pron|v|title))*)
    (?:\s+(?P<tail>.+))?                   # optional level marker / trailing info
    $""",
    re.VERBOSE,
)


def _parse_entry(raw: str) -> Optional[Entry]:
    """Parse one already-tokenized entry string into an Entry.

    Handles patterns like:
        apple n
        bat (as sports equipment) n
        bounce v
        colour (US color) n + v
        fish (s + pl) n
        at prep of place
        lorry (US truck) n
        mouse/mice n
        sheep (s + pl) n
    """
    # Split off any leading parenthetical that should actually belong to the
    # previous entry (rare because _iter_entries_in_text cuts at POS).
    raw = raw.strip()
    # Some entries have parentheticals *after* the POS, like "at prep of place".
    # We handle those by matching POS first, then capturing the tail.

    # Try to find POS boundary manually: the word portion can contain `(...)`.
    # Walk forward and find the first POS token that is NOT inside parentheses.
    depth = 0
    tokens = raw.split(" ")
    pos_start: Optional[int] = None
    for idx, t in enumerate(tokens):
        depth += t.count("(") - t.count(")")
        if depth == 0 and t in VALID_POS and idx > 0:
            pos_start = idx
            break
    if pos_start is None:
        return None

    word_part = " ".join(tokens[:pos_start]).strip()
    rest = tokens[pos_start:]

    # Collect POS chain (pos, +, pos, +, pos, ...)
    pos_list: List[str] = []
    j = 0
    while j < len(rest):
        if rest[j] in VALID_POS:
            pos_list.append(rest[j])
            j += 1
            if j < len(rest) and rest[j] == "+":
                j += 1
                continue
            break
        else:
            break
    tail = " ".join(rest[j:]).strip() or None

    # Word may contain a parenthetical variant "(US xxx)" / "(UK xxx)" or a
    # "sense" like "(as in a ball)" / "(as sports equipment)" / "(computer)".
    variants: Dict[str, Optional[str]] = {"UK": None, "US": None}
    sense: Optional[str] = None
    base_word = word_part
    m = re.match(r"^(?P<base>[^()]+?)\s*\((?P<paren>[^)]+)\)\s*$", word_part)
    if m:
        base_word = m.group("base").strip()
        paren = m.group("paren").strip()
        mv = re.match(r"^(UK|US)\s+(.+)$", paren)
        if mv:
            variants[mv.group(1)] = mv.group(2).strip()
        elif paren in {"s + pl"}:
            # grammatical note, not a sense
            sense = None
        else:
            sense = paren

    # If the tail starts with "of place" / "of time" or similar, it's a sense
    # qualifier for prepositions.
    if tail and tail.startswith("of "):
        sense = tail

    return Entry(word=base_word, pos=pos_list, variants=variants, sense=sense)


def parse_level_pages(pdf: "pdfplumber.PDF", level: str) -> List[Entry]:
    start, end = LEVEL_PAGE_RANGES[level]
    entries: List[Entry] = []
    buffer: List[str] = []

    # The per-level pages can have entries that wrap across page boundaries —
    # we address this by concatenating all pages' text, stripping headers /
    # footers, then stripping letter-section headers, then parsing as one
    # stream.
    lines: List[str] = []
    for page_idx in range(start, end + 1):
        page_text = pdf.pages[page_idx].extract_text() or ""
        lines.extend(page_text.splitlines())

    lines = _strip_footer_and_headers(lines)
    # Remove single-letter section headers.
    lines = [ln for ln in lines if not LETTER_LINE_RE.match(ln)]
    # Also strip the 2-column "Grammatical key" table rows, which survive as
    # lines like "adj adjective int interrogative".  They would otherwise be
    # parsed as entries (e.g., "adjective" treated as a word).  Pattern:
    # starts with a POS key and contains another POS key.
    cleaned: List[str] = []
    for ln in lines:
        if re.match(
            r"^(adj|adv|conj|det|dis|excl|int|n|poss|prep|pron|v)\s+\w+\s+(adj|adv|conj|det|dis|excl|int|n|poss|prep|pron|v)\s+\w+",
            ln,
        ):
            continue
        cleaned.append(ln)
    big_text = " ".join(cleaned)
    raw_entries = _iter_entries_in_text(big_text)

    for raw in raw_entries:
        ent = _parse_entry(raw)
        if ent is None or not ent.pos:
            continue
        # Skip obvious junk from column-wrap fragments.
        if not re.search(r"[A-Za-z]", ent.word):
            continue
        if ent.word.startswith("(") or ent.word.endswith(")") and not ent.word.startswith("("):
            # parenthetical-only fragment that lost its head word
            if ent.word.startswith("("):
                continue
        if ent.word in {"adj +", "+", "adj", "n", "v"}:
            continue
        # Strip stray leading/trailing "+" tokens
        ent.word = ent.word.strip(" +")
        if not ent.word:
            continue
        ent.level = level
        entries.append(ent)

    return entries


# --------------------------------------------------------------------------
# Parsing: thematic list (pages 38-43)
# --------------------------------------------------------------------------


def parse_thematic_pages(pdf: "pdfplumber.PDF") -> Dict[str, Dict[str, List[str]]]:
    """Parse the thematic vocabulary list.

    Returns: theme -> level -> [words].  Level is one of
    "starters" / "movers" / "flyers".

    We rely on pdfplumber's word-level extraction so we can assign each word
    to the correct level column based on x-coordinate.  A new theme begins at
    any row whose leftmost non-word text is a theme label (leftmost column).
    """
    start, end = THEMATIC_PAGE_RANGE
    theme_map: Dict[str, Dict[str, List[str]]] = defaultdict(
        lambda: {"starters": [], "movers": [], "flyers": []}
    )

    for page_idx in range(start, end + 1):
        page = pdf.pages[page_idx]
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        if not words:
            continue

        # Column boundaries (x0) derived from inspection of the thematic pages:
        # each level has up to 2 sub-columns; we take the x0 of the leftmost
        # sub-column.  The theme label sits in a narrow left gutter at x~45.
        #
        #   theme label   ~  42-50
        #   starters col1 ~ 104.9   col2 ~ 179.5
        #   movers   col1 ~ 251.3   col2 ~ 325.x
        #   flyers   col1 ~ 397.8   col2 ~ 470.x
        col_xs: Dict[str, float] = {
            "starters": 100.0,
            "movers": 245.0,
            "flyers": 390.0,
        }
        THEME_MAX_X = 90.0

        # Group words into rows by y-coordinate (tolerance 3).
        rows: List[List[dict]] = []
        for w in sorted(words, key=lambda x: (round(x["top"], 0), x["x0"])):
            if rows and abs(w["top"] - rows[-1][0]["top"]) < 3.5:
                rows[-1].append(w)
            else:
                rows.append([w])

        current_theme: Optional[str] = None
        pending_label_tokens: List[str] = []
        # Tracks whether the last processed row had a theme-label fragment.
        # When we see a theme row following a pure-data row, we're starting a
        # new theme and must reset the accumulator.
        last_row_had_label = False

        def _is_noise_label(label: str) -> bool:
            if not label:
                return True
            if label in {
                "Pre", "A1", "A2",
                "Pre A1 Starters, A1 Movers and A2 Flyers",
                "thematic vocabulary list",
            }:
                return True
            if re.fullmatch(r"\d+", label):
                return True
            if label.startswith("Pre A1 Starters"):
                return True
            return False

        for row in rows:
            row.sort(key=lambda x: x["x0"])
            theme_tokens = [w["text"] for w in row if w["x0"] < THEME_MAX_X]
            data_tokens = [w for w in row if w["x0"] >= col_xs["starters"] - 2]

            if theme_tokens:
                if not last_row_had_label:
                    # New theme starts here; reset accumulator.
                    pending_label_tokens = []
                pending_label_tokens.extend(theme_tokens)
                last_row_had_label = True
            else:
                last_row_had_label = False

            if pending_label_tokens:
                candidate = " ".join(pending_label_tokens).strip()
                if not _is_noise_label(candidate):
                    # If this row has data tokens, lock in the accumulated
                    # label as the active theme; subsequent label fragments
                    # (on continuation rows that also have data) will extend
                    # it via the accumulator.
                    current_theme = candidate

            if current_theme is None:
                # Clear pending noise so we don't carry it forward.
                pending_label_tokens = []
                continue
            # Skip the header row itself.
            if any(t["text"] in {"Starters", "Movers", "Flyers"} for t in data_tokens):
                continue

            # Assign each data token to its column.  Each level has 2
            # sub-columns; we bucket by the midpoints between level starts.
            mid_sm = (col_xs["starters"] + col_xs["movers"]) / 2
            mid_mf = (col_xs["movers"] + col_xs["flyers"]) / 2

            # Within a level, the two sub-columns each hold a single word, so
            # we record each token as its own word.  Multi-word entries like
            # "polar bear" or "ice cream" sit in the SAME sub-column (same
            # x0) on the same row — pdfplumber returns each space-separated
            # piece as its own word object, so we need to stitch adjacent
            # tokens whose x0 is within a sub-column's gap.
            # Sub-column starts (x0) observed: each level has cols at roughly
            # level_x and level_x + 74.  A gap < 40 between adjacent tokens in
            # the same level means they are a single multi-word entry.
            by_level: Dict[str, List[List[dict]]] = {"starters": [], "movers": [], "flyers": []}
            for t in data_tokens:
                x = t["x0"]
                if x < mid_sm:
                    lvl = "starters"
                elif x < mid_mf:
                    lvl = "movers"
                else:
                    lvl = "flyers"
                bucket = by_level[lvl]
                if bucket and (t["x0"] - (bucket[-1][-1]["x0"] + bucket[-1][-1]["width"])) < 15:
                    bucket[-1].append(t)
                else:
                    bucket.append([t])
            for lvl, groups in by_level.items():
                for grp in groups:
                    theme_map[current_theme][lvl].append(" ".join(g["text"] for g in grp))

    # Post-process: merge theme labels where one is a prefix of another.
    # Wrap-over themes get locked in repeatedly as their label grows, so we
    # see e.g. "The body", "The body and the", "The body and the face" as
    # three sibling keys.  Collapse them into the longest.
    keys_by_len = sorted(theme_map.keys(), key=len)
    merged: Dict[str, Dict[str, List[str]]] = {}
    # Walk shortest → longest; for each key, find the longest other key that
    # has it as a prefix and merge into that.
    redirect: Dict[str, str] = {}
    for k in keys_by_len:
        target = k
        for other in keys_by_len:
            if other == k:
                continue
            if other.startswith(k + " ") and len(other) > len(target):
                target = other
        redirect[k] = target
    for k, by_level in theme_map.items():
        tgt = redirect[k]
        dest = merged.setdefault(tgt, {"starters": [], "movers": [], "flyers": []})
        for lvl, ws in by_level.items():
            dest[lvl].extend(ws)
    # Drop obvious noise keys.
    for noise in list(merged.keys()):
        if noise.startswith("Pre A1") or noise == "thematic vocabulary list":
            del merged[noise]
    return merged


# --------------------------------------------------------------------------
# Post-processing: merge thematic into per-level entries
# --------------------------------------------------------------------------


def _normalise_theme_word(raw: str) -> List[str]:
    """Split a thematic-cell raw string into one or more candidate words.

    The thematic list sometimes glues continuation fragments; we conservatively
    split on " / " and strip parentheticals.
    """
    out: List[str] = []
    # Tokens like "mouse/mice" are kept as-is; matches per-level form.
    candidate = raw.strip()
    if not candidate:
        return out
    # Strip trailing/leading parenthetical fragments (left-overs from wrap).
    candidate = re.sub(r"\s*\([^)]*\)\s*$", "", candidate).strip()
    out.append(candidate)
    return out


def attach_themes(entries: List[Entry], thematic: Dict[str, Dict[str, List[str]]]) -> None:
    # Build a lookup: lowercased word -> list of entries (we prefer same-level match).
    by_word: Dict[str, List[Entry]] = defaultdict(list)
    for e in entries:
        by_word[e.word.lower()].append(e)

    for theme, by_level in thematic.items():
        for lvl, words in by_level.items():
            for raw in words:
                for w in _normalise_theme_word(raw):
                    candidates = by_word.get(w.lower(), [])
                    if not candidates:
                        continue
                    # Prefer the same-level entry; else attach to all.
                    same_level = [c for c in candidates if c.level == lvl]
                    targets = same_level or candidates
                    for t in targets:
                        if theme not in t.themes:
                            t.themes.append(theme)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH}", file=sys.stderr)
        return 1

    with pdfplumber.open(str(PDF_PATH)) as pdf:
        all_entries: List[Entry] = []
        for level in ("starters", "movers", "flyers"):
            lvl_entries = parse_level_pages(pdf, level)
            print(f"{level}: {len(lvl_entries)} entries", file=sys.stderr)
            all_entries.extend(lvl_entries)

        thematic = parse_thematic_pages(pdf)
        print(f"themes: {len(thematic)}", file=sys.stderr)

    attach_themes(all_entries, thematic)

    # Build output JSON.
    by_level: Dict[str, List[str]] = {"starters": [], "movers": [], "flyers": []}
    for e in all_entries:
        by_level[e.level].append(e.word)

    # Dedupe within each level preserving order.
    for lvl, words in by_level.items():
        seen: Set[str] = set()
        uniq: List[str] = []
        for w in words:
            k = w.lower()
            if k in seen:
                continue
            seen.add(k)
            uniq.append(w)
        by_level[lvl] = uniq

    themes_out: Dict[str, List[str]] = {}
    for theme, by_l in thematic.items():
        flat: List[str] = []
        for lvl in ("starters", "movers", "flyers"):
            flat.extend(by_l.get(lvl, []))
        themes_out[theme] = flat

    out = {
        "source": str(PDF_PATH),
        "entries": [
            {
                "word": e.word,
                "pos": e.pos,
                "level": e.level,
                "variants": e.variants,
                "sense": e.sense,
                "themes": e.themes,
            }
            for e in all_entries
        ],
        "by_level": by_level,
        "themes": themes_out,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=False)
    print(f"wrote {OUT_PATH} ({len(all_entries)} entries)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
