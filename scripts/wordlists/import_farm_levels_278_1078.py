#!/usr/bin/env python3
"""Import farm and livestock vocabulary at 278, and the specialist remainder at 1078.

Started from "cattle" in the top unlinked tokens (2026-10-17).  "cow" (N02_005,
level 2) stays the early word: its definition already makes it the everyday
term regardless of sex, and that is the word a beginner needs.  "cattle" is a
lemma of its own rather than a form of cow, since several languages keep a
separate collective word (lt galvijai, de Rinder/Vieh, es ganado) and linking
the token to cow would teach the wrong one.

278 sits beside Food and Cooking 2 (279), where the meats already are; 1078
pairs with it as the topic-band list, following 231-233 / 1031-1033.  Neither
level row exists yet: name them on the Barsukas Levels page.  A few farm words
belong to existing cohorts instead: wheat at 28, the animal body parts at 160,
cud at 1010.  acre and hectare are left for a units list.

Every word goes through the add-sense path with domain "farming", which also
catches the headwords that already mean something else -- "calf" the leg,
"straw" for drinking, "steer" the verb -- and labels those.  New senses take
the level default prominence (uncommon at 278, rare at 1078); "lamb" the animal
is marked common, since only the meat sense exists today and the animal is the
everyday meaning.

The moves are lemmas the database already has with the right meaning, parked
at staging (1399); they change level only.  GUIDs are from the database on
2026-10-17, and each is checked against its headword before it moves.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlists.wordlist_import_helper import LevelMove
from scripts.wordlists.wordlist_import_helper import SenseEntry as S
from scripts.wordlists.wordlist_import_helper import SenseList, run_sense_import

GENERAL_LEVEL = 278
TOPIC_LEVEL = 1078
DOMAIN = "farming"
TAGS = ("farming",)

FARM_GENERAL = SenseList(
    level=GENERAL_LEVEL,
    domain=DOMAIN,
    label="farming",
    tags=TAGS,
    entries=(
        # Animals
        S("cattle", "cows and bulls kept as livestock, as a group", unique=True),
        S("bull", "an adult male of cattle", disambiguation="animal"),
        S("ox", "a castrated bull used to pull loads", unique=True),
        S("calf", "a young cow or bull", disambiguation="animal"),
        S("heifer", "a young female cow that has not had a calf", unique=True),
        S("hen", "an adult female chicken", unique=True),
        S("lamb", "a young sheep", disambiguation="animal", prominence="common"),
        S("ram", "an adult male sheep", disambiguation="animal"),
        S("ewe", "an adult female sheep", unique=True),
        S("piglet", "a young pig", unique=True),
        S("foal", "a young horse", unique=True),
        S("livestock", "farm animals kept for meat, milk, wool or work", unique=True),
        S("poultry", "chickens, ducks, geese and turkeys kept on a farm", unique=True),
        # Land, buildings and materials
        S("manure", "animal dung spread on fields as fertilizer", unique=True),
        S("fertilizer", "a substance added to soil to help plants grow", unique=True),
        S("hay", "grass cut and dried as animal feed", unique=True),
        S("straw", "dried stalks of grain used as bedding", disambiguation="dried stalks"),
        S("pasture", "land covered with grass where animals graze", unique=True),
        S("meadow", "a field of grass and wild flowers", unique=True),
        S("orchard", "a piece of land planted with fruit trees", unique=True),
        S("trough", "a long open container for animal feed or water", disambiguation="feeding"),
        S("henhouse", "a small building where hens are kept", unique=True),
        S("pigsty", "an enclosure where pigs are kept", unique=True),
        S("scarecrow", "a figure set up in a field to frighten birds", unique=True),
        S("agriculture", "the practice of farming: growing crops and raising animals", unique=True),
        S("greenhouse", "a glass building where plants are grown", unique=True),
        S(
            "mill",
            "a building with machinery for grinding grain into flour",
            disambiguation="grain",
        ),
        S("wagon", "a four-wheeled vehicle pulled by horses or oxen", unique=True),
        # People and work
        S("shepherd", "a person who looks after sheep", unique=True),
        S("graze", "of animals, to eat grass in a field", unique=True, pos="verb"),
        S("milk", "to take milk from a cow, goat or sheep", unique=True, pos="verb"),
        S("harvest", "to gather a crop when it is ripe", unique=True, pos="verb"),
        S("herd", "to drive or gather animals into a group", unique=True, pos="verb"),
    ),
)

FARM_TOPIC = SenseList(
    level=TOPIC_LEVEL,
    domain=DOMAIN,
    label="farming",
    tags=TAGS,
    entries=(
        # Animals
        S("steer", "a young castrated male of cattle raised for beef", disambiguation="animal"),
        S("bullock", "a young castrated bull", unique=True),
        S("sow", "an adult female pig", disambiguation="female pig", pos="noun"),
        S("boar", "an uncastrated male pig kept for breeding", disambiguation="male pig"),
        S("stallion", "an uncastrated adult male horse", unique=True),
        S("mare", "an adult female horse", unique=True),
        S("kid", "a young goat", disambiguation="young goat"),
        S("gelding", "a castrated male horse", unique=True),
        S("colt", "a young male horse", unique=True),
        S("filly", "a young female horse", unique=True),
        S("gilt", "a young female pig that has not had piglets", disambiguation="young pig"),
        S("drake", "a male duck", disambiguation="male duck"),
        S("gander", "a male goose", disambiguation="male goose"),
        S("pullet", "a young hen", unique=True),
        S("cockerel", "a young rooster", unique=True),
        S("sheepdog", "a dog trained to herd sheep", unique=True),
        S("fleece", "the wool coat of a sheep", disambiguation="sheep's wool"),
        # Crops
        S("barley", "a cereal grain grown for animal feed and brewing", unique=True),
        S("oats", "a cereal grain grown for animal feed and porridge", unique=True),
        S("rye", "a cereal grain grown for flour and animal feed", unique=True),
        S("stalk", "the main stem of a plant such as wheat or corn", unique=True, pos="noun"),
        S("husk", "the dry outer covering of a seed or grain", unique=True),
        S("chaff", "the husks separated from grain by threshing", unique=True),
        S("pesticide", "a chemical used to kill pests on crops", unique=True),
        S("herbicide", "a chemical used to kill weeds", unique=True),
        S("compost", "decayed plant matter used to enrich soil", unique=True, pos="noun"),
        S("topsoil", "the fertile upper layer of soil", unique=True),
        S("irrigation", "supplying water to crops through channels or pipes", unique=True),
        S("furrow", "a long trench cut in the soil by a plough", disambiguation="plough"),
        S("fallow", "of farmland, left unplanted for a season to recover", unique=True),
        S("arable", "of land, used or suitable for growing crops", unique=True),
        S("husbandry", "the care and breeding of farm animals and crops", unique=True),
        S("dung", "the solid waste of animals", unique=True),
        S("slurry", "liquid manure stored and spread on fields", disambiguation="manure"),
        # Land, buildings and materials
        S("fodder", "dried food such as hay given to livestock", unique=True),
        S(
            "silage",
            "grass or other green crops stored without drying to feed livestock",
            unique=True,
        ),
        S("silo", "a tall tower used to store grain or silage", unique=True),
        S("paddock", "a small field where horses are kept", unique=True),
        S("haystack", "a large pile of stored hay", unique=True),
        S("stall", "a compartment for one animal in a barn or stable", disambiguation="animal"),
        S("farmland", "land used for farming", unique=True),
        S("abattoir", "a place where animals are killed for meat", unique=True),
        S("grassland", "a large area of land covered with grass", unique=True),
        S("hedgerow", "a row of bushes forming a boundary between fields", unique=True),
        S("homestead", "a farmhouse with its land and outbuildings", unique=True),
        S("smallholding", "a small farm worked by one family", unique=True),
        S("plantation", "a large estate where one crop is grown", unique=True),
        S("vineyard", "a piece of land where grapevines are grown", unique=True),
        S("feedlot", "an area where cattle are fattened for slaughter", unique=True),
        S("corral", "a fenced pen for cattle or horses", unique=True),
        S("stockyard", "a large yard with pens where livestock are kept before sale", unique=True),
        S("granary", "a building for storing grain", unique=True),
        S("hayloft", "the upper floor of a barn where hay is stored", unique=True),
        S("cowshed", "a building where cows are kept", unique=True),
        S("manger", "a long open box from which horses or cattle eat", unique=True),
        S("hutch", "a wooden cage for rabbits", unique=True),
        S("beehive", "a structure in which bees are kept", unique=True),
        # Tools and equipment
        S("hoe", "a long-handled tool for weeding and loosening soil", unique=True),
        S("scythe", "a tool with a long curved blade for cutting grass or grain", unique=True),
        S("sickle", "a short-handled tool with a curved blade for cutting grain", unique=True),
        S("pitchfork", "a long-handled fork for lifting hay", unique=True),
        S("harrow", "a farm implement that breaks up and levels ploughed soil", unique=True),
        S("bale", "a large tightly bound bundle of hay or straw", unique=True),
        S("baler", "a machine that presses hay or straw into bales", unique=True),
        S("combine harvester", "a machine that cuts and threshes grain", unique=True),
        S("saddle", "a leather seat strapped to a horse's back", unique=True, pos="noun"),
        S("bridle", "the straps and bit put on a horse's head to control it", unique=True),
        S("harness", "the set of straps by which an animal pulls a cart or plough", unique=True),
        S("yoke", "a wooden bar joining two oxen so they can pull together", unique=True),
        S("stirrup", "a loop hanging from a saddle to support a rider's foot", unique=True),
        S("horseshoe", "a curved iron plate nailed to a horse's hoof", unique=True),
        # People and work
        S("ranch", "a large farm for raising cattle or horses", unique=True),
        S("rancher", "a person who owns or runs a ranch", unique=True),
        S("farmhand", "a person employed to work on a farm", unique=True),
        S("herdsman", "a person who looks after a herd of animals", unique=True),
        S("beekeeper", "a person who keeps bees for honey", unique=True),
        S("farrier", "a person who shoes horses", unique=True),
        S("sharecropper", "a tenant farmer who pays rent with part of the crop", unique=True),
        S("shear", "to cut the wool off a sheep", unique=True, pos="verb"),
        S("sow", "to plant seeds by scattering them on the ground", unique=True, pos="verb"),
        S("reap", "to cut and gather a crop", unique=True, pos="verb"),
        S("thresh", "to separate grain from the stalks", unique=True, pos="verb"),
        S("irrigate", "to supply water to land or crops", unique=True, pos="verb"),
        S("wean", "to stop a young animal feeding on its mother's milk", unique=True, pos="verb"),
        S("calve", "of a cow, to give birth to a calf", unique=True, pos="verb"),
        S("castrate", "to remove the testicles of a male animal", unique=True, pos="verb"),
        S("mow", "to cut grass or hay", unique=True, pos="verb"),
        S("prune", "to cut back branches of a tree or bush", unique=True, pos="verb"),
        S("slaughter", "to kill an animal for food", unique=True, pos="verb"),
        S("brand", "to mark livestock with a hot iron", disambiguation="livestock", pos="verb"),
    ),
)

# Farm words that belong to other cohorts: wheat beside the other staple foods
# and plants, the animal body parts beside horn, tail and fur, and cud in the
# advanced anatomy list.  Same domain and tag, so a re-run finds them.
WHEAT = SenseList(
    level=28,
    domain=DOMAIN,
    label="farming",
    tags=TAGS,
    entries=(S("wheat", "the cereal plant whose grain is ground into flour", unique=True),),
)

ANIMAL_BODY_PARTS = SenseList(
    level=160,
    domain=DOMAIN,
    label="farming",
    tags=TAGS,
    pos_subtype="body_part",
    entries=(
        S("hoof", "the hard covering on the foot of a horse, cow or sheep", unique=True),
        S("udder", "the bag-like milk gland of a cow, goat or sheep", unique=True),
        S("teat", "a nipple of a cow, goat or sheep, from which milk is drawn", unique=True),
    ),
)

ADVANCED_ANATOMY = SenseList(
    level=1010,
    domain=DOMAIN,
    label="farming",
    tags=TAGS,
    pos_subtype="body_part",
    entries=(
        S("cud", "partly digested food that cattle bring back up to chew again", unique=True),
    ),
)

MOVES = (
    LevelMove("N27_010", "herd", GENERAL_LEVEL),
    LevelMove("N27_009", "flock", GENERAL_LEVEL),
    LevelMove("N28_048", "harvest", GENERAL_LEVEL),
    LevelMove("V07_022", "breed", GENERAL_LEVEL),
    LevelMove("N36_161", "breeder", TOPIC_LEVEL),
)


if __name__ == "__main__":
    raise SystemExit(
        run_sense_import(
            (FARM_GENERAL, FARM_TOPIC, WHEAT, ANIMAL_BODY_PARTS, ADVANCED_ANATOMY),
            __doc__ or "",
            moves=MOVES,
        )
    )
