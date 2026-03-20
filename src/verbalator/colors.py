"""Color group definitions for verbalator actions.

Codeword colors follow the atacama color system (see atacama-powera repo,
aml_parser/colorblocks.py).  Each entry maps a codeword to its display
name, CSS background, CSS border, CSS text color (for result card headers),
and a short description of what the color group represents.
"""

from typing import Dict, NamedTuple


class ColorDef(NamedTuple):
    display_name: str
    background: str
    border: str
    text: str
    description: str


# Ordered by spectrum position: infrared → red → ... → violet.
COLORS: Dict[str, ColorDef] = {
    "xantham": ColorDef(
        display_name="Xantham",
        background="#fce8e0",
        border="#a0522d",
        text="#8b3a1a",
        description="sarcasm / tone",
    ),
    "red": ColorDef(
        display_name="Red",
        background="#fce8e8",
        border="#d93025",
        text="#b31412",
        description="editorial / critique / review",
    ),
    "orange": ColorDef(
        display_name="Orange",
        background="#fef0e1",
        border="#e8710a",
        text="#c25e00",
        description="vocabulary / pronunciation difficulty",
    ),
    "yellow": ColorDef(
        display_name="Yellow",
        background="#fef7e0",
        border="#f9ab00",
        text="#b06000",
        description="quotation / attribution / rhetoric / structure",
    ),
    "green": ColorDef(
        display_name="Green",
        background="#e6f4ea",
        border="#34a853",
        text="#137333",
        description="technical / structural / knowledge",
    ),
    "blue": ColorDef(
        display_name="Blue",
        background="#e8f0fe",
        border="#4285f4",
        text="#1a73e8",
        description="analysis / metadata",
    ),
    "violet": ColorDef(
        display_name="Violet",
        background="#f3e8fd",
        border="#673ab7",
        text="#4a148c",
        description="content filters / sensitivity",
    ),
    "color-pending": ColorDef(
        display_name="Pending",
        background="#f0f0f0",
        border="#999999",
        text="#555555",
        description="color not yet assigned",
    ),
}

# The UI iterates over this list to group action checkboxes.
COLOR_ORDER = list(COLORS.keys())
