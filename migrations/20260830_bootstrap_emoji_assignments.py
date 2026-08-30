#!/usr/bin/env python3
"""Bootstrap the unambiguous emoji assignments.

Every pairing here is one where the glyph is a picture of the lemma's concept,
which is the bar set by ``words.emoji.ASSIGNMENT_GUIDANCE``: a horse for
*horse*, not a snowflake for *cold*. Associations and conventional symbols are
deliberately absent -- the peace sign, the male/female signs, the warning
triangle and the zodiac Cancer all name a concept without depicting it, and the
astronomical Earth and Sun glyphs are symbols rather than pictures.

Senses matter as much as spellings. The catalog's TURKEY, CRICKET and FLY match
a lemma by text while meaning something else entirely (the country, the sport,
the verb), so they are not here either.

Pairs are keyed by GUID rather than lemma text or row id: the GUID is the
stable identity across a database rebuild, which renumbers ids, and several
lemma spellings are shared by two senses.

Rerunning is a no-op. A pair whose glyph is already attached to that same lemma
is left alone; one whose glyph is held by a *different* lemma is reported and
skipped rather than moved, because that is a decision a human made in the
review UI and this script must not silently overturn it. Assignments go through
``words.emoji.assign_emoji``, so the ``emoji`` table and the ``Lemma.emoji``
mirror that feeds ``data/release`` stay in step.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from typing import Dict, List, Optional, Sequence, Tuple

from constants import WORDFREQ_DB_PATH
from storage.backend import create_session
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.emoji import EMOJI_STATUS_ASSIGNED, Emoji
from storage.models.schema import Lemma
from words.emoji import EmojiConflictError, assign_emoji, emoji_values

# (glyph, lemma GUID). Ordered by GUID so the table reads like the vocabulary.
PAIRS: Sequence[Tuple[str, str]] = (
    # -- already assigned by hand in the review UI --
    ("🐎", "N02_004"),  # horse
    ("🐇", "N02_011"),  # rabbit
    ("🐳", "N02_012"),  # whale
    ("🦈", "N02_016"),  # shark
    ("🐏", "N02_028"),  # sheep
    ("🐝", "N02_039"),  # bee
    ("🍅", "N06_018"),  # tomato
    ("🍕", "N06_026"),  # pizza
    ("🌽", "N06_039"),  # corn
    ("🍋", "N06_042"),  # lemon
    ("🍇", "N06_044"),  # grape
    ("🍓", "N06_045"),  # strawberry
    ("🍐", "N06_050"),  # pear
    ("🍉", "N06_051"),  # watermelon
    ("🍍", "N06_053"),  # pineapple
    ("🦞", "N06_083"),  # lobster
    ("🌭", "N06_109"),  # hot dog
    ("🏀", "N41_027"),  # basketball
    # -- unambiguous name matches --
    ("🌋", "N11_019"),  # volcano
    ("🌠", "N11_075"),  # shooting star
    ("🌫", "N11_029"),  # fog
    ("🌹", "N05_005"),  # rose
    ("🍄", "N06_059"),  # mushroom
    ("🍈", "N06_052"),  # melon
    ("🍌", "N06_016"),  # banana
    ("🍑", "N06_049"),  # peach
    ("🍞", "N06_001"),  # bread
    ("🍟", "N06_110"),  # french fries
    ("🍨", "N06_104"),  # ice cream
    ("🎀", "N08_064"),  # ribbon
    ("🎢", "N10_012"),  # roller coaster
    ("🎤", "N57_015"),  # microphone
    ("🎫", "N50_028"),  # ticket
    ("🎸", "N41_026"),  # guitar
    ("🏐", "N41_029"),  # volleyball
    ("🏜", "N11_012"),  # desert
    ("🏟", "N07_057"),  # stadium
    ("🏢", "N07_075"),  # office building
    ("🏥", "N07_003"),  # hospital
    ("🏨", "N07_007"),  # hotel
    ("🏪", "N07_080"),  # convenience store
    ("🏬", "N07_079"),  # department store
    ("🏭", "N07_017"),  # factory
    ("🐄", "N02_005"),  # cow
    ("🐅", "N02_013"),  # tiger
    ("🐆", "N02_055"),  # leopard
    ("🐈", "N02_002"),  # cat
    ("🐉", "N02_029"),  # dragon
    ("🐊", "N02_045"),  # crocodile
    ("🐌", "N02_059"),  # snail
    ("🐍", "N02_014"),  # snake
    ("🐐", "N02_020"),  # goat
    ("🐒", "N02_036"),  # monkey
    ("🐓", "N02_061"),  # rooster
    ("🐔", "N02_007"),  # chicken
    ("🐕", "N02_001"),  # dog
    ("🐖", "N02_006"),  # pig
    ("🐘", "N02_015"),  # elephant
    ("🐙", "N02_057"),  # octopus
    ("🐜", "N02_040"),  # ant
    ("🐢", "N02_025"),  # turtle
    ("🐦", "N02_003"),  # bird
    ("🐧", "N02_042"),  # penguin
    ("🐬", "N02_041"),  # dolphin
    ("🐸", "N02_023"),  # frog
    ("🐺", "N02_010"),  # wolf
    ("🐻", "N02_009"),  # bear
    ("🐼", "N02_065"),  # panda
    ("👁", "N03_003"),  # eye
    ("👂", "N03_006"),  # ear
    ("👃", "N03_004"),  # nose
    ("👄", "N03_005"),  # mouth
    ("👅", "N03_008"),  # tongue
    ("👓", "N08_011"),  # eyeglasses
    ("👕", "N09_032"),  # t-shirt
    ("👖", "N09_021"),  # jeans
    ("👗", "N09_003"),  # dress
    ("👦", "N01_057"),  # boy
    ("👧", "N01_058"),  # girl
    ("👨", "N01_055"),  # man
    ("👩", "N01_056"),  # woman
    ("👪", "N35_031"),  # family
    ("👮", "N36_019"),  # police officer
    ("👶", "N01_076"),  # baby
    ("💀", "N03_063"),  # skull
    ("💣", "N44_010"),  # bomb
    ("💳", "N08_134"),  # credit card
    ("📦", "N08_040"),  # package
    ("📷", "N08_088"),  # camera
    ("📹", "N57_011"),  # video camera
    ("📺", "N57_003"),  # television
    ("📻", "N57_004"),  # radio
    ("🔋", "N57_008"),  # battery
    ("🔒", "N12_046"),  # lock
    ("🔔", "N08_077"),  # bell
    ("🔥", "N11_035"),  # fire
    ("🔧", "N12_050"),  # wrench
    ("🔨", "N12_047"),  # hammer
    ("🔫", "N44_013"),  # pistol
    ("🕌", "N07_053"),  # mosque
    ("🕮", "N08_005"),  # book
    ("🕯", "N08_025"),  # candle
    ("🕷", "N02_018"),  # spider
    ("🖥", "N57_026"),  # desktop computer
    ("🖨", "N57_001"),  # printer
    ("😌", "A19_028"),  # relieved
    ("😕", "A19_011"),  # confused
    ("😞", "A19_019"),  # disappointed
    ("😟", "A19_008"),  # worried
    ("😠", "A19_003"),  # angry
    ("😩", "A05_158"),  # weary
    ("😫", "A19_005"),  # tired
    ("🚁", "N40_013"),  # helicopter
    ("🚊", "N40_016"),  # tram
    ("🚌", "N40_002"),  # bus
    ("🚏", "N13_018"),  # bus stop
    ("🚑", "N40_018"),  # ambulance
    ("🚓", "N40_027"),  # police car
    ("🚕", "N40_010"),  # taxi
    ("🚜", "N40_019"),  # tractor
    ("🚢", "N40_009"),  # ship
    ("🚪", "N47_001"),  # door
    ("🚲", "N40_007"),  # bicycle
    ("🛏", "N39_005"),  # bed
    ("🛞", "N12_076"),  # wheel
    ("🛡", "N44_002"),  # shield
    ("🛴", "N40_020"),  # scooter
    ("🛻", "N40_029"),  # pickup truck
    ("🤴", "N01_088"),  # prince
    ("🥄", "N08_002"),  # spoon
    ("🥆", "N44_012"),  # rifle
    ("🥒", "N06_067"),  # cucumber
    ("🥓", "N06_074"),  # bacon
    ("🥔", "N06_014"),  # potato
    ("🥕", "N06_084"),  # carrot
    ("🥚", "N06_009"),  # egg
    ("🥢", "N08_037"),  # chopsticks
    ("🥥", "N06_055"),  # coconut
    ("🥦", "N06_064"),  # broccoli
    ("🥪", "N06_027"),  # sandwich
    ("🥭", "N06_054"),  # mango
    ("🦁", "N02_035"),  # lion
    ("🦅", "N02_027"),  # eagle
    ("🦆", "N02_022"),  # duck
    ("🦉", "N02_017"),  # owl
    ("🦊", "N02_038"),  # fox
    ("🦋", "N02_024"),  # butterfly
    ("🦌", "N02_037"),  # deer
    ("🦍", "N02_052"),  # gorilla
    ("🦏", "N02_054"),  # rhinoceros
    ("🦐", "N06_081"),  # shrimp
    ("🦒", "N02_043"),  # giraffe
    ("🦓", "N02_044"),  # zebra
    ("🦘", "N02_056"),  # kangaroo
    ("🦚", "N02_063"),  # peacock
    ("🦛", "N02_053"),  # hippopotamus
    ("🦜", "N02_048"),  # parrot
    ("🦟", "N02_058"),  # mosquito
    ("🦢", "N02_062"),  # swan
    ("🦩", "N02_064"),  # flamingo
    ("🦴", "N03_028"),  # bone
    ("🦵", "N03_020"),  # leg
    ("🦶", "N03_024"),  # foot
    ("🦷", "N03_007"),  # tooth
    ("🧄", "N06_060"),  # garlic
    ("🧅", "N06_019"),  # onion
    ("🧈", "N06_011"),  # butter
    ("🧠", "N03_032"),  # brain
    ("🧣", "N09_018"),  # scarf
    ("🧯", "N12_085"),  # fire extinguisher
    ("🧱", "N14_021"),  # brick
    ("🧺", "N08_052"),  # basket
    ("🧽", "N08_059"),  # sponge
    ("🧾", "N24_063"),  # receipt
    ("🩳", "N09_025"),  # shorts
    ("🪑", "N39_001"),  # chair
    ("🪒", "N08_034"),  # razor
    ("🪓", "N12_057"),  # axe
    ("🪙", "N08_061"),  # coin
    ("🪛", "N12_048"),  # screwdriver
    ("🪜", "N12_051"),  # ladder
    ("🪝", "N12_071"),  # hook
    ("🪞", "N08_016"),  # mirror
    ("🪟", "N47_002"),  # window
    ("🪢", "N08_111"),  # knot
    ("🪣", "N08_056"),  # bucket
    ("🪥", "N08_023"),  # toothbrush
    ("🪱", "N02_060"),  # worm
    ("🪵", "N14_001"),  # wood
    ("🪶", "N03_068"),  # feather
    ("🪽", "N03_044"),  # wing
    ("🪿", "N02_021"),  # goose
    ("🫏", "N02_046"),  # donkey
    ("🫑", "N06_093"),  # bell pepper
    ("🫙", "N08_054"),  # jar
    ("☁", "N11_024"),  # cloud
    ("☂", "N08_027"),  # umbrella
    ("⚾", "N41_028"),  # baseball
    ("⛆", "N11_025"),  # rain
    ("⛪", "N07_004"),  # church
    ("⛫", "N07_029"),  # castle
    ("⛰", "N11_001"),  # mountain
    ("⛴", "N40_017"),  # ferry
    ("⛵", "N40_021"),  # sailboat
    ("⛺", "N07_018"),  # tent
    ("✈", "N40_006"),  # airplane
    ("✉", "N08_053"),  # envelope
    ("✏", "N08_020"),  # pencil
)


def build_data_source_config(db_path: str, use_postgres: bool) -> DataSourceConfig:
    """Build the storage config for this migration."""
    if use_postgres:
        return DataSourceConfig(
            backend_type=BackendType.POSTGRES,
            postgres_url=DataSourceConfig.build_postgres_url(),
        )
    return DataSourceConfig(backend_type=BackendType.SQLITE, sqlite_path=db_path)


def apply_pairs(config: DataSourceConfig, *, dry_run: bool = False) -> Dict[str, int]:
    """Attach every pairing that is not already in place.

    Returns counts keyed ``assigned``/``already``/``conflict``/``missing``.
    """
    session = create_session(config)
    counts = {"assigned": 0, "already": 0, "conflict": 0, "missing": 0}
    try:
        guids = [guid for _, guid in PAIRS]
        # guid is nullable on the model, so the None case is filtered out
        # rather than assumed away; a lemma without one cannot be a target here.
        lemmas: Dict[str, Lemma] = {
            lemma.guid: lemma
            for lemma in session.query(Lemma).filter(Lemma.guid.in_(guids))
            if lemma.guid is not None
        }
        # Which lemma, if any, already holds each glyph. A glyph held by a
        # different lemma is a human decision, not a stale row.
        holders: Dict[str, Optional[int]] = {
            row.value: row.lemma_id
            for row in session.query(Emoji).filter(Emoji.status == EMOJI_STATUS_ASSIGNED)
        }

        for glyph, guid in PAIRS:
            lemma = lemmas.get(guid)
            if lemma is None:
                counts["missing"] += 1
                print(f"  missing lemma {guid} for {glyph}")
                continue

            holder = holders.get(glyph)
            if holder == lemma.id:
                counts["already"] += 1
                continue
            if holder is not None:
                counts["conflict"] += 1
                other = session.get(Lemma, holder)
                other_text = other.lemma_text if other else holder
                print(f"  {glyph} already held by {other_text!r}, not {guid}; left alone")
                continue

            counts["assigned"] += 1
            if dry_run:
                print(f"  would attach {glyph} to {lemma.lemma_text} ({guid})")
                continue

            # Carry the lemma's existing glyphs: assign_emoji replaces the whole
            # list, and a word may already hold one set in the review UI.
            values: List[str] = emoji_values(lemma)
            if glyph not in values:
                values.append(glyph)
            try:
                assign_emoji(session, lemma, [{"type": "unicode", "value": v} for v in values])
            except EmojiConflictError as conflict:
                session.rollback()
                counts["assigned"] -= 1
                counts["conflict"] += 1
                print(f"  {conflict}")
                continue
            session.commit()
            holders[glyph] = lemma.id
            print(f"  {glyph} -> {lemma.lemma_text} ({guid})")
    finally:
        session.close()
    return counts


def main() -> int:
    """Run the migration."""
    parser = argparse.ArgumentParser(description="Bootstrap unambiguous emoji assignments")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    parser.add_argument("--db-path", default=WORDFREQ_DB_PATH, help="SQLite database path")
    parser.add_argument("--postgres", action="store_true", help="Use PostgreSQL instead")
    args = parser.parse_args()

    config = build_data_source_config(args.db_path, args.postgres)
    print(f"Database: {config.postgres_url if args.postgres else config.sqlite_path}")
    print(f"Pairings: {len(PAIRS)}")
    print(f"Dry run: {args.dry_run}\n")

    counts = apply_pairs(config, dry_run=args.dry_run)
    print(
        f"\nassigned {counts['assigned']}, already set {counts['already']}, "
        f"conflicts {counts['conflict']}, missing lemma {counts['missing']}"
    )
    if args.dry_run:
        print("\n** DRY RUN - No changes were made **")
    return 0


if __name__ == "__main__":
    sys.exit(main())
