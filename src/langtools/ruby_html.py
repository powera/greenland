#!/usr/bin/env python3
"""Shared helpers for building ruby-annotated HTML.

Chinese (pinyin) and Japanese (romaji) both render text as a run of <ruby>
elements. This module holds the pieces that must behave identically for both
so the two languages cannot drift apart.
"""


def wrap_unannotated_ruby(segment: str) -> str:
    """
    Wrap a segment that has no reading in a ruby element with an empty <rt>.

    A <ruby> element is pushed down to make room for its <rt> annotation, while
    a bare text node stays on the normal baseline. Mixing the two in one line
    makes unannotated runs (Latin names, digits, punctuation) float upward
    relative to their annotated neighbours. Giving every visible segment a ruby
    box - even an empty one - reserves the same annotation row for all of them,
    so they share a baseline.

    Pure whitespace is returned unchanged: it has no glyph to misalign, and
    wrapping it would pick up the inline-block margin that the ruby styling
    applies to real segments.

    Args:
        segment: Text segment with no reading to display above it

    Returns:
        The segment wrapped in <ruby>...<rt></rt></ruby>, or unchanged if it is
        empty or entirely whitespace
    """
    if not segment or not segment.strip():
        return segment
    return f"<ruby>{segment}<rt></rt></ruby>"
