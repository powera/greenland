#!/usr/bin/env python3
"""Import the 88 IAU constellations at topic level 1055, and "constellation" at 135.

A closed set, placed as the ``constellations`` cohort (``wordfreq.data.cohorts``)
beside ``physical_science`` at 1050.  Every name goes through the add-sense path
with the subtype fixed to ``celestial_object``, which the cohort requires all of
its members to share; the model is not asked for one.

The headwords are the Latin IAU names -- Orion, Ursa Major, Camelopardalis --
since that is what English uses for them.  Each hint gives the English meaning
("the Hunter", "the Giraffe"), so the translations are each language's name for
the constellation rather than a folk name or an asterism: the Big Dipper is a
pattern inside Ursa Major, not another name for it.  Every name carries the
"constellation" label, even ones with no other English meaning today:
Camelopardalis could still gain its "Latin for giraffe" sense.

The zodiac constellations are here under their IAU names (Scorpius,
Capricornus).  The astrology signs are different senses and a separate set.

The common noun "constellation" is general vocabulary at 135, beside star and
planet.  It cannot sit at 1055, which the cohort owns.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlists.wordlist_import_helper import SenseEntry as S
from scripts.wordlists.wordlist_import_helper import SenseList, run_sense_import

SUBTYPE = "celestial_object"

CONSTELLATIONS = SenseList(
    level=1055,
    domain="astronomy",
    label="constellation",
    tags=("constellations",),
    pos_subtype=SUBTYPE,
    entries=(
        S("Andromeda", "the constellation of the Chained Princess"),
        S("Antlia", "the constellation of the Air Pump"),
        S("Apus", "the constellation of the Bird of Paradise"),
        S("Aquarius", "the constellation of the Water-Bearer"),
        S("Aquila", "the constellation of the Eagle"),
        S("Ara", "the constellation of the Altar"),
        S("Aries", "the constellation of the Ram"),
        S("Auriga", "the constellation of the Charioteer"),
        S("Boötes", "the constellation of the Herdsman"),
        S("Caelum", "the constellation of the Chisel"),
        S("Camelopardalis", "the constellation of the Giraffe"),
        S("Cancer", "the constellation of the Crab"),
        S("Canes Venatici", "the constellation of the Hunting Dogs"),
        S("Canis Major", "the constellation of the Great Dog"),
        S("Canis Minor", "the constellation of the Lesser Dog"),
        S("Capricornus", "the constellation of the Sea Goat"),
        S("Carina", "the constellation of the Keel of the ship Argo"),
        S("Cassiopeia", "the constellation of the Seated Queen"),
        S("Centaurus", "the constellation of the Centaur"),
        S("Cepheus", "the constellation of the King"),
        S("Cetus", "the constellation of the Sea Monster, or Whale"),
        S("Chamaeleon", "the constellation of the Chameleon"),
        S("Circinus", "the constellation of the Drawing Compass"),
        S("Columba", "the constellation of the Dove"),
        S("Coma Berenices", "the constellation of Berenice's Hair"),
        S("Corona Australis", "the constellation of the Southern Crown"),
        S("Corona Borealis", "the constellation of the Northern Crown"),
        S("Corvus", "the constellation of the Crow"),
        S("Crater", "the constellation of the Cup"),
        S("Crux", "the constellation of the Southern Cross"),
        S("Cygnus", "the constellation of the Swan"),
        S("Delphinus", "the constellation of the Dolphin"),
        S("Dorado", "the constellation of the Dolphinfish"),
        S("Draco", "the constellation of the Dragon"),
        S("Equuleus", "the constellation of the Little Horse"),
        S("Eridanus", "the constellation of the River Eridanus"),
        S("Fornax", "the constellation of the Furnace"),
        S("Gemini", "the constellation of the Twins"),
        S("Grus", "the constellation of the Crane"),
        S("Hercules", "the constellation of the hero Hercules"),
        S("Horologium", "the constellation of the Pendulum Clock"),
        S("Hydra", "the constellation of the Water Snake"),
        S("Hydrus", "the constellation of the Lesser Water Snake"),
        S("Indus", "the constellation of the Indian"),
        S("Lacerta", "the constellation of the Lizard"),
        S("Leo", "the constellation of the Lion"),
        S("Leo Minor", "the constellation of the Lesser Lion"),
        S("Lepus", "the constellation of the Hare"),
        S("Libra", "the constellation of the Scales"),
        S("Lupus", "the constellation of the Wolf"),
        S("Lynx", "the constellation of the Lynx"),
        S("Lyra", "the constellation of the Lyre"),
        S("Mensa", "the constellation of the Table Mountain"),
        S("Microscopium", "the constellation of the Microscope"),
        S("Monoceros", "the constellation of the Unicorn"),
        S("Musca", "the constellation of the Fly"),
        S("Norma", "the constellation of the Carpenter's Square"),
        S("Octans", "the constellation of the Octant"),
        S("Ophiuchus", "the constellation of the Serpent-Bearer"),
        S("Orion", "the constellation of the Hunter"),
        S("Pavo", "the constellation of the Peacock"),
        S("Pegasus", "the constellation of the Winged Horse"),
        S("Perseus", "the constellation of the hero Perseus"),
        S("Phoenix", "the constellation of the Phoenix"),
        S("Pictor", "the constellation of the Painter's Easel"),
        S("Pisces", "the constellation of the Fishes"),
        S("Piscis Austrinus", "the constellation of the Southern Fish"),
        S("Puppis", "the constellation of the Stern of the ship Argo"),
        S("Pyxis", "the constellation of the Mariner's Compass"),
        S("Reticulum", "the constellation of the Reticle"),
        S("Sagitta", "the constellation of the Arrow"),
        S("Sagittarius", "the constellation of the Archer"),
        S("Scorpius", "the constellation of the Scorpion"),
        S("Sculptor", "the constellation of the Sculptor"),
        S("Scutum", "the constellation of the Shield"),
        S("Serpens", "the constellation of the Serpent"),
        S("Sextans", "the constellation of the Sextant"),
        S("Taurus", "the constellation of the Bull"),
        S("Telescopium", "the constellation of the Telescope"),
        S("Triangulum", "the constellation of the Triangle"),
        S("Triangulum Australe", "the constellation of the Southern Triangle"),
        S("Tucana", "the constellation of the Toucan"),
        S("Ursa Major", "the constellation of the Great Bear"),
        S("Ursa Minor", "the constellation of the Little Bear"),
        S("Vela", "the constellation of the Sails of the ship Argo"),
        S("Virgo", "the constellation of the Maiden"),
        S("Volans", "the constellation of the Flying Fish"),
        S("Vulpecula", "the constellation of the Little Fox"),
    ),
)

CONSTELLATION_WORD = SenseList(
    level=135,
    domain="astronomy",
    label="stars",
    tags=(),
    pos_subtype=SUBTYPE,
    entries=(S("constellation", "a named group of stars forming a pattern in the night sky"),),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import([CONSTELLATIONS, CONSTELLATION_WORD], __doc__ or ""))
