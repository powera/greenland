#!/usr/bin/env python3
"""Import animal species: named units at 126-127 and 331-334, species at 1250-1258.

The early animal units (2, 28, 125, 130) hold the basic animals and 1078 the
farm ones, but most other species were nowhere -- muskrat, flounder, tsetse fly
-- and a survey on 2026-11-19 found the gap reached everyday words too: the
insect "fly", the bird "turkey", wasp, otter, caterpillar and starfish had no
animal sense at all.  So the list has three tiers:

* 126 and 127 are named-band units beside More Animals (125) and Wild and
  Domestic Animals (130), roughly B1: the animals a children's picture book has.
* 331-333 are the same shape one step up, roughly B2: well-known species a
  reader meets in nature writing and documentaries (meerkat, heron, iguana,
  swordfish, termite), split by group as 1250-1255 are.  They open the free
  run 331-339 between Arts and Creative Works (330) and Biology and Living
  Things (340); 334-339 are kept for later B2 animal units.
  334 is the B2 unit for the kinds of animal (reptile, rodent, carnivore),
  none of which existed.
* 1250-1255 are topic levels, one per animal group: mammals, birds, reptiles
  and amphibians, fish, insects, and the other invertebrates.  The range starts
  a natural-world block after the sports units (1200-1249).  1256 holds the
  dinosaurs and other extinct animals, 1257 the dog breeds and 1258 the cat,
  horse and livestock breeds; 1259 is left for a later animal list.  A breed
  is its own sense and does not replace the species word: "Holstein" is a
  cow, and cow (N02_005) stays the word a learner uses for it.  The farm terms
  for animals by age and sex (heifer, mare) are at 278 and 1078, not here.
  The zoology terms for groups (arthropod, cetacean)
  join mammal and vertebrate at Animals and Zoology (1013).

The topic lists were extended from the animal articles of the wiki_biology
corpus (``src/wordfreq/corpora/wikipedia/lists/biology.yaml``, "Organisms:
Animals"): every article there is either in the database already, in this
script, or deliberately left out.  Left out are the Latin orders and families
with no English common noun (Perciformes, Hymenoptera, Salmonidae), families
whose member is already listed under its own name (Coccinellidae is the
ladybug), scientific species names where the common name is listed (Bombyx mori
is the silkworm), descriptive titles (coral reef fish, deep-sea fish), and the
human articles other than the Neanderthal and Australopithecus.

A species makes the topic list only if it has a settled common name in most of
the course languages, so regional names (katydid, bluegill, chickadee) are
left out; where English has two names for one animal the more international
one is used (reindeer, not caribou; mountain lion stays the only puma/cougar).
Each entry's hint describes the animal, so the translation is the species'
name rather than a word for the group it belongs to.

Every word goes through the add-sense path with the subtype fixed to
``animal``; the model is not asked for one.  Headwords that already mean
something else -- "fly" the verb, "Turkey" the country, "pike" the dive, "mole"
on the skin -- carry a label.  New senses take the level default prominence
(uncommon below 1000, rare from 1000), except "fly" and "turkey", whose animal
senses are everyday meanings.

The moves are species the database already has at another level, which
change level only: cod and crane were filed at Music and the Arts (1000), the
cardinal is parked at staging (1399), and the specialist species at Animals
and Zoology (1013) join their group.  1013 keeps the zoology words (mammal,
vertebrate, plumage) and the common animals filed there.  GUIDs are from the
database on 2026-11-19, and each is checked against its headword before it
moves.

After the words, an ``--execute`` run names each level that now has words and
no name yet, writing ``curriculum_levels`` directly: Barsukas has no API for
level names.  A level somebody already named keeps its name.

Running without ``--execute`` only prints the plan and makes no HTTP requests
or database writes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Mapping, NamedTuple

ROOT = Path(__file__).resolve().parent.parent.parent
for import_path in (ROOT, ROOT / "src"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from scripts.wordlists.wordlist_import_helper import LevelMove
from scripts.wordlists.wordlist_import_helper import SenseEntry as S
from scripts.wordlists.wordlist_import_helper import SenseList, run_sense_import
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.crud.curriculum_level import get_curriculum_level, set_curriculum_level
from storage.models.schema import Lemma

DOMAIN = "zoology"
SUBTYPE = "animal"
THEME_TAG = "animals"
SOURCE = "scripts/import_animal_species_levels"


class LevelName(NamedTuple):
    name: str
    cefr: str


LEVEL_NAMES: Mapping[int, LevelName] = {
    126: LevelName("Wild Animals and Birds", "B1"),
    127: LevelName("Insects, Reptiles and Sea Animals", "B1"),
    331: LevelName("Wild Mammals", "B2"),
    332: LevelName("Birds, Reptiles and Amphibians", "B2"),
    333: LevelName("Fish, Insects and Sea Creatures", "B2"),
    334: LevelName("Kinds of Animals", "B2"),
    1250: LevelName("Mammals", "C1"),
    1251: LevelName("Birds", "C1"),
    1252: LevelName("Reptiles and Amphibians", "C1"),
    1253: LevelName("Fish", "C1"),
    1254: LevelName("Insects", "C1"),
    1255: LevelName("Spiders, Molluscs and Other Invertebrates", "C1"),
    1256: LevelName("Dinosaurs and Extinct Animals", "C1"),
    1257: LevelName("Dog Breeds", "C1"),
    1258: LevelName("Cat, Horse and Livestock Breeds", "C1"),
}


def U(term: str, hint: str) -> S:
    """A headword with no other meaning in English, stored without a label."""
    return S(term, hint, unique=True)


def species_list(level: int, group: str, label: str, entries: tuple[S, ...]) -> SenseList:
    """One group's list: tagged with the theme and the group, subtype fixed."""
    return SenseList(
        level=level,
        domain=DOMAIN,
        label=label,
        tags=(THEME_TAG, group),
        pos_subtype=SUBTYPE,
        entries=entries,
    )


EVERYDAY_WILD = species_list(
    126,
    "everyday_animals",
    "animal",
    (
        U("beaver", "a large rodent with a flat tail that builds dams across rivers"),
        U("otter", "a playful furry animal that swims in rivers and eats fish"),
        U("hedgehog", "a small animal covered in spines that rolls into a ball"),
        U("raccoon", "a grey furry animal with a black mask and a ringed tail"),
        U("cheetah", "a spotted big cat, the fastest land animal"),
        U("koala", "an Australian animal that lives in trees and eats eucalyptus"),
        U("hamster", "a small rodent with cheek pouches, often kept as a pet"),
        U("reindeer", "a deer of the far north with large antlers, used to pull sledges"),
        U("skunk", "a black and white animal that sprays a bad smell"),
        S("badger", "a grey burrowing animal with a black and white striped face"),
        U("chimpanzee", "an African ape, the closest living relative of humans"),
        U("hyena", "a doglike African animal known for its laughing call"),
        U("jaguar", "a large spotted big cat of Central and South America"),
        U("llama", "a woolly South American animal related to the camel"),
        U("walrus", "a large Arctic sea animal with long tusks"),
        U("antelope", "a fast, slender, horned grazing animal of Africa and Asia"),
        U("porcupine", "a rodent covered in long sharp quills"),
        S("mole", "a small burrowing animal with dark fur and tiny eyes"),
        S("sloth", "a slow-moving animal that hangs upside down in tropical trees"),
        S("lynx", "a wild cat with tufted ears and a short tail"),
        U("ostrich", "a very large African bird that cannot fly but runs fast"),
        S("robin", "a small songbird with a red-orange breast", disambiguation="bird"),
        S(
            "turkey",
            "a large bird raised for its meat, eaten at festive meals",
            disambiguation="bird",
            prominence="common",
        ),
        U("pelican", "a large water bird with a pouch under its beak for catching fish"),
        U("woodpecker", "a bird that pecks holes in tree trunks"),
        U("vulture", "a large bird with a bare head that feeds on dead animals"),
        U("falcon", "a fast bird of prey with long pointed wings"),
        U("canary", "a small yellow songbird often kept as a pet"),
        U("hummingbird", "a tiny bird that hovers while feeding on flower nectar"),
        U("stork", "a tall white bird with long legs and a long red beak"),
    ),
)

EVERYDAY_SMALL_AND_SEA = species_list(
    127,
    "everyday_animals",
    "animal",
    (
        S(
            "fly",
            "a common flying insect with two wings, such as the housefly",
            disambiguation="insect",
            pos="noun",
            prominence="common",
        ),
        U("wasp", "a yellow and black flying insect that can sting"),
        U("caterpillar", "the long, soft larva of a butterfly or moth"),
        U("ladybug", "a small round beetle, usually red with black spots"),
        U("grasshopper", "a jumping insect with long back legs that chirps"),
        U("dragonfly", "an insect with a long thin body and four clear wings"),
        U("cockroach", "a brown insect that lives in dirty buildings"),
        U("flea", "a tiny jumping insect that bites animals and people"),
        U("toad", "an animal like a frog with dry, bumpy skin"),
        U("tadpole", "the young of a frog or toad, living in water with a tail"),
        U("alligator", "a large reptile like a crocodile with a broad snout"),
        U("cobra", "a poisonous snake that spreads its neck into a hood"),
        S("python", "a very large snake that kills by squeezing", disambiguation="snake"),
        U("chameleon", "a lizard that can change the colour of its skin"),
        U("eel", "a long, snakelike fish"),
        S("salmon", "a large fish that swims up rivers to lay its eggs", disambiguation="fish"),
        U("goldfish", "a small orange fish often kept in a bowl"),
        U("seahorse", "a small fish that swims upright and has a head like a horse"),
        U("starfish", "a sea animal shaped like a star with five arms"),
        U("squid", "a sea animal with a long body and ten arms"),
        S("slug", "a slimy animal like a snail without a shell", disambiguation="animal"),
        U("scorpion", "an animal related to spiders with a poisonous sting in its tail"),
        U("centipede", "a long, thin crawling animal with many legs"),
        U("earthworm", "a worm that lives in soil"),
    ),
)

WILD_MAMMALS = species_list(
    331,
    "intermediate_animals",
    "animal",
    (
        U("armadillo", "an American mammal covered in bony armour plates"),
        U("anteater", "a Central and South American mammal with a long snout that eats ants"),
        U("baboon", "a large African monkey with a doglike face"),
        U("chipmunk", "a small striped squirrel that lives on the ground"),
        U("coyote", "a wild dog of North America, smaller than a wolf"),
        U("elk", "a very large deer"),
        U("ferret", "a small domesticated relative of the weasel"),
        U("gazelle", "a small, graceful antelope of Africa and Asia"),
        U("gerbil", "a small desert rodent often kept as a pet"),
        U("lemur", "a tree-living primate with a long tail, found only in Madagascar"),
        U("alpaca", "a South American animal like a small llama, kept for its wool"),
        U("meerkat", "a small African mongoose that stands upright to keep watch"),
        U("mongoose", "a small African and Asian predator known for killing snakes"),
        U("orangutan", "a red-haired ape of the rainforests of Borneo and Sumatra"),
        U("panther", "a big cat with a black coat, especially a black leopard"),
        U("porpoise", "a small toothed whale with a blunt snout"),
        U("weasel", "a small, slender predator with brown fur"),
        U("wolverine", "a strong, fierce animal of the northern forests in the weasel family"),
        U("yak", "a large, long-haired ox of the Himalayas"),
        U("wombat", "a burrowing Australian marsupial with short legs"),
        U("wallaby", "an Australian marsupial like a small kangaroo"),
        U("blue whale", "the largest animal that has ever lived"),
        U("sea otter", "an otter of the North Pacific that floats on its back"),
        U("jackal", "a wild dog of Africa and Asia that scavenges"),
        S("wild boar", "the wild pig of European and Asian forests", unique=True),
    ),
)

BIRDS_REPTILES = species_list(
    332,
    "intermediate_animals",
    "bird",
    (
        U("blackbird", "a songbird whose male is black with a yellow beak"),
        U("cuckoo", "a bird that lays its eggs in other birds' nests"),
        U("finch", "a small seed-eating songbird with a short thick beak"),
        U("heron", "a tall grey wading bird with long legs and a long neck"),
        U("kingfisher", "a small, brightly coloured bird that dives for fish"),
        U("magpie", "a black and white bird of the crow family with a long tail"),
        U("nightingale", "a small brown bird famous for singing at night"),
        U("pheasant", "a game bird whose male has a long tail and bright feathers"),
        U("puffin", "a black and white seabird with a large, colourful beak"),
        U("toucan", "a tropical American bird with a huge, colourful beak"),
        U("emu", "a large Australian bird that cannot fly"),
        U("wren", "a tiny brown songbird with an upright tail"),
        U("macaw", "a large, brightly coloured parrot of Central and South America"),
        U("condor", "a very large South American vulture"),
        U("iguana", "a large tropical American lizard with a crest along its back"),
        U("gecko", "a small lizard that can climb walls"),
        S("viper", "a poisonous snake with long fangs", disambiguation="snake"),
        U("anaconda", "a very large South American snake that lives near water"),
        U("salamander", "an amphibian like a lizard with smooth, moist skin"),
        U("newt", "a small amphibian that lives partly in water"),
    ),
)

FISH_INSECTS_SEA = species_list(
    333,
    "intermediate_animals",
    "animal",
    (
        U("sardine", "a small sea fish of the herring family"),
        U("mackerel", "a sea fish with a striped blue-green back"),
        S("carp", "a large freshwater fish often raised in ponds", disambiguation="fish"),
        S("tuna", "a large, fast ocean fish", disambiguation="fish"),
        U("swordfish", "a large ocean fish with a long, flat, swordlike snout"),
        U("stingray", "a flat fish with a poisonous spine on its tail"),
        U("piranha", "a small South American river fish with sharp teeth"),
        U("clownfish", "a small orange and white fish that lives among sea anemones"),
        U("hornet", "a large wasp"),
        U("bumblebee", "a large, hairy bee"),
        S("cricket", "a jumping insect that chirps at night", disambiguation="insect"),
        U("locust", "a grasshopper that travels in huge swarms and destroys crops"),
        U("termite", "an insect that lives in colonies and eats wood"),
        U("firefly", "a beetle that gives off light at night"),
        U("praying mantis", "an insect that holds its front legs together as if praying"),
        U("tarantula", "a large hairy spider"),
        S("shrimp", "a small sea animal with a long body and ten legs"),
        U("prawn", "a sea animal like a large shrimp"),
        U("mussel", "a shellfish with a dark blue-black shell"),
        U("leech", "a worm that sucks blood"),
        U("millipede", "a long crawling animal with very many legs"),
        U("sea urchin", "a round sea animal covered in spines"),
    ),
)

KINDS_OF_ANIMALS = species_list(
    334,
    "intermediate_animals",
    "animal",
    (
        U("reptile", "a cold-blooded animal with scales, such as a snake, lizard or turtle"),
        U("amphibian", "a cold-blooded animal such as a frog that lives on land and in water"),
        U("rodent", "a small mammal with sharp front teeth for gnawing, such as a mouse"),
        U("primate", "a mammal of the group that includes monkeys, apes and humans"),
        U("marsupial", "a mammal such as a kangaroo whose young grow in a pouch"),
        U("crustacean", "an animal with a hard shell and jointed legs, such as a crab"),
        U("arachnid", "an eight-legged animal such as a spider or scorpion"),
        U("mollusc", "a soft-bodied animal, often with a shell, such as a snail or clam"),
        U("carnivore", "an animal that eats meat"),
        U("herbivore", "an animal that eats only plants"),
        U("omnivore", "an animal that eats both plants and meat"),
        U("songbird", "a bird with a musical call"),
        U("seabird", "a bird that lives on the coast and feeds at sea"),
        U("bird of prey", "a bird such as an eagle or hawk that hunts other animals"),
    ),
)

ZOOLOGY_TERMS = species_list(
    1013,
    "zoology_terms",
    "animal",
    (
        U("invertebrate", "an animal without a backbone"),
        U("chordate", "an animal of the phylum that includes the vertebrates"),
        U("arthropod", "an invertebrate with jointed legs and a hard outer skeleton"),
        U("myriapod", "an arthropod with many legs, such as a centipede or millipede"),
        U("decapod", "a crustacean with ten legs, such as a crab, lobster or shrimp"),
        U("cnidarian", "a simple sea animal with stinging cells, such as a jellyfish"),
        U("echinoderm", "a spiny-skinned sea animal such as a starfish or sea urchin"),
        U("bivalve", "a mollusc with a hinged two-part shell, such as a clam or oyster"),
        U("gastropod", "a mollusc such as a snail or slug"),
        U("cephalopod", "a mollusc with tentacles, such as an octopus or squid"),
        U("annelid", "a segmented worm, such as an earthworm or leech"),
        U("nematode", "a roundworm"),
        U("tetrapod", "a vertebrate with four limbs"),
        U("cetacean", "a whale, dolphin or porpoise"),
        U("pinniped", "a seal, sea lion or walrus"),
        U("ungulate", "a mammal with hooves"),
        U("ruminant", "a hoofed mammal that chews the cud, such as a cow or deer"),
        U("monotreme", "an egg-laying mammal, such as the platypus"),
        U("lagomorph", "a rabbit, hare or pika"),
        U("hominid", "a member of the family of great apes and humans"),
        U("passerine", "a perching bird, the order that includes most songbirds"),
        U("sirenian", "a manatee or dugong"),
        U("bryozoan", "a tiny water animal that lives in colonies, also called a moss animal"),
    ),
)

MAMMALS = species_list(
    1250,
    "mammals",
    "animal",
    (
        U("aardvark", "an African burrowing mammal with a long snout that eats termites"),
        U("bobcat", "a North American wild cat with a short tail"),
        U("chinchilla", "a small South American rodent with very soft fur"),
        U("dingo", "the wild dog of Australia"),
        U("dormouse", "a small rodent with a bushy tail that hibernates"),
        U("ermine", "a stoat in its white winter coat"),
        U("gibbon", "a small ape with very long arms that swings through trees"),
        U("wildebeest", "a large African antelope that migrates in huge herds"),
        U("ibex", "a wild mountain goat with long curved horns"),
        U("impala", "a medium-sized African antelope that leaps high"),
        U("manatee", "a large, slow plant-eating mammal of warm coastal waters"),
        U("marmot", "a large ground squirrel of mountain regions"),
        U("mink", "a small, weasel-like animal valued for its fur"),
        U("muskrat", "a large North American water rodent"),
        U("narwhal", "an Arctic whale whose male has a long spiral tusk"),
        U("ocelot", "a spotted wild cat of Central and South America"),
        U("opossum", "an American marsupial that pretends to be dead when threatened"),
        U("shrew", "a tiny mouselike mammal with a long pointed snout"),
        U("stoat", "a small brown predator of the weasel family with a black-tipped tail"),
        U("tapir", "a hoofed mammal of tropical forests with a short flexible snout"),
        U("vole", "a small rodent like a mouse with a short tail"),
        U("warthog", "an African wild pig with tusks and warts on its face"),
        S("beluga", "a white Arctic whale", disambiguation="whale"),
        U("humpback whale", "a large whale known for its long fins and songs"),
        U("sperm whale", "a large whale with a huge square head"),
        U("echidna", "a spiny Australian mammal that lays eggs"),
        U("okapi", "an African forest animal related to the giraffe, with striped legs"),
        S("chamois", "a goatlike antelope of European mountains", disambiguation="animal"),
        U("lemming", "a small Arctic rodent"),
        U("pangolin", "a mammal covered in hard scales that eats ants"),
        U("capybara", "a South American rodent, the largest in the world"),
        U("bonobo", "an African ape closely related to the chimpanzee"),
        U("mandrill", "a large African monkey with a red and blue face"),
        U("marmoset", "a very small South American monkey"),
        U("macaque", "a monkey of Asia and North Africa"),
        U("dugong", "a sea mammal like a manatee, found in the Indian and Pacific Oceans"),
        U("Tasmanian devil", "a fierce meat-eating marsupial of Tasmania"),
        U("hyrax", "a small, furry African mammal distantly related to the elephant"),
        U("fruit bat", "a large bat that eats fruit"),
        U("vampire bat", "a Central and South American bat that feeds on blood"),
        U("brown bear", "a large bear of northern forests, including the grizzly"),
        U("snow leopard", "a big cat with thick grey fur, living in the mountains of Asia"),
        U("honey badger", "a fierce African and Asian animal of the weasel family"),
        U("marten", "a tree-climbing animal of the weasel family"),
        U("gaur", "a very large wild ox of South and Southeast Asia"),
        U("muskox", "a shaggy Arctic animal related to goats and sheep"),
        U("water buffalo", "a large Asian buffalo used to work in rice fields"),
        U("dromedary", "the camel with one hump"),
        U("Bactrian camel", "the camel with two humps"),
        U("red deer", "a large deer of Europe and Asia with a reddish coat"),
        U("guanaco", "a wild South American animal related to the llama"),
        U("peccary", "a piglike animal of the Americas"),
        U("pronghorn", "a fast, deerlike animal of North American grasslands"),
        U("vicuña", "a wild South American animal related to the llama, with fine wool"),
        U("nutria", "a large South American water rodent, also called the coypu"),
        U("slow loris", "a small, slow-moving primate of Southeast Asia with large eyes"),
        U("galago", "a small African primate with large eyes that leaps between trees"),
        U("tarsier", "a tiny Southeast Asian primate with huge eyes"),
        U("capuchin monkey", "a small, clever South American monkey"),
        U("spider monkey", "a South American monkey with long limbs and tail"),
    ),
)

BIRDS = species_list(
    1251,
    "birds",
    "bird",
    (
        S("albatross", "a very large seabird with long narrow wings"),
        U("budgerigar", "a small Australian parrot often kept as a pet"),
        U("buzzard", "a large bird of prey with broad wings"),
        U("cockatoo", "a parrot with a crest of feathers on its head"),
        U("cormorant", "a dark seabird that dives to catch fish"),
        U("curlew", "a wading bird with a long down-curved beak"),
        U("goldfinch", "a small finch with yellow on its wings"),
        U("grouse", "a plump game bird of moors and forests"),
        U("ibis", "a wading bird with a long down-curved beak, sacred in ancient Egypt"),
        S("jay", "a noisy, brightly coloured bird of the crow family"),
        U("kestrel", "a small falcon that hovers while hunting"),
        S("lark", "a brown songbird that sings while flying high"),
        U("mallard", "the common wild duck, whose male has a green head"),
        U("oriole", "a songbird whose male is bright yellow or orange and black"),
        U("osprey", "a large bird of prey that catches fish"),
        U("partridge", "a plump game bird with a short tail"),
        U("plover", "a short-billed wading bird of shores and fields"),
        S("rook", "a black bird of the crow family that nests in colonies"),
        U("sandpiper", "a small wading bird of beaches and mudflats"),
        S("starling", "a dark songbird with glossy, speckled feathers"),
        S("swift", "a fast-flying bird with long curved wings", pos="noun"),
        U("tern", "a slender white seabird with a forked tail"),
        U("thrush", "a songbird with a speckled breast"),
        U("wagtail", "a small bird that constantly wags its long tail"),
        U("warbler", "a small, active songbird of woods and gardens"),
        U("cockatiel", "a small crested Australian parrot often kept as a pet"),
        U("egret", "a white heron"),
        U("jackdaw", "a small grey-headed bird of the crow family"),
        U("bullfinch", "a finch whose male has a pink-red breast"),
        U("chaffinch", "a common European finch"),
        U("lapwing", "a plover with a crest that lives in fields"),
        U("woodcock", "a wading bird of woodland with a long straight beak"),
        U("hoopoe", "a bird with a fanlike crest and a long curved beak"),
        U("mynah", "an Asian starling that can imitate speech"),
        U("golden eagle", "a large dark-brown eagle of mountains and open country"),
        U("peregrine falcon", "a falcon that dives at great speed to catch birds"),
        U("secretary bird", "a long-legged African bird of prey that hunts on foot"),
        U("nightjar", "a bird that hunts insects at dusk and rests on the ground by day"),
        U("auk", "a black and white diving seabird of northern seas"),
        U("hornbill", "a tropical bird with a very large curved beak"),
        U("hoatzin", "a South American bird whose chicks have claws on their wings"),
        U("turaco", "a brightly coloured African bird of forests"),
        U("guineafowl", "an African game bird with spotted grey feathers"),
        U("loon", "a large diving bird of northern lakes with a haunting call"),
        U("bustard", "a large, heavy bird of open grasslands"),
        S("rail", "a small, secretive marsh bird with long toes"),
        U("bird of paradise", "a bird of New Guinea whose males have spectacular feathers"),
        U("lyrebird", "an Australian bird that imitates sounds"),
        U("shrike", "a songbird that impales its prey on thorns"),
        U("bulbul", "a songbird of Africa and Asia"),
        U("mockingbird", "a songbird that imitates the songs of other birds"),
        U("flycatcher", "a small bird that catches insects in flight"),
        U("weaverbird", "a small bird that weaves elaborate nests"),
        U("sunbird", "a small, brightly coloured bird of Africa and Asia that feeds on nectar"),
        U("titmouse", "a small, active songbird of the tit family"),
        U("frigatebird", "a large seabird with long wings whose male has a red throat pouch"),
        U("shoebill", "a large African wading bird with a huge shoe-shaped beak"),
        U("gannet", "a large white seabird that dives into the sea for fish"),
        U("honeyguide", "an African bird that leads people and animals to bees' nests"),
        U("petrel", "a seabird that flies far out over the open ocean"),
        U("cassowary", "a large flightless bird of New Guinea and Australia"),
        S("rhea", "a large flightless South American bird"),
        U("quetzal", "a Central American bird with bright green feathers and a long tail"),
        U("barn owl", "a pale owl with a heart-shaped face"),
        U("eagle owl", "a very large owl with ear tufts"),
        U("honeyeater", "an Australasian songbird that feeds on nectar"),
        U("tinamou", "a ground-dwelling bird of Central and South America"),
        U("trogon", "a tropical forest bird with bright, soft feathers"),
        U("antbird", "a tropical American bird that follows army ants"),
    ),
)

REPTILES_AMPHIBIANS = species_list(
    1252,
    "reptiles_amphibians",
    "animal",
    (
        U("boa constrictor", "a large snake of tropical America that kills by squeezing"),
        U("Komodo dragon", "the largest lizard, found on islands in Indonesia"),
        U("monitor lizard", "a large lizard of Africa, Asia and Australia"),
        S("adder", "a small poisonous snake of Europe", disambiguation="snake"),
        U("mamba", "a fast, very poisonous African snake"),
        U("king cobra", "the longest poisonous snake"),
        U("terrapin", "a small turtle that lives in fresh water"),
        U("caiman", "a Central and South American reptile related to the alligator"),
        U("sea turtle", "a large turtle that lives in the sea"),
        U("skink", "a smooth, shiny lizard with short legs"),
        U("axolotl", "a Mexican salamander that keeps its gills as an adult"),
        U("bullfrog", "a large frog with a deep call"),
        U("tree frog", "a small frog that climbs trees"),
        U("cane toad", "a large poisonous toad"),
        U("caecilian", "a legless amphibian that looks like a worm"),
        U("Gila monster", "a poisonous lizard of the deserts of the southwestern United States"),
        U("horned lizard", "a flat, spiky desert lizard"),
        S("copperhead", "a poisonous North American snake with a copper-coloured head"),
        U("cottonmouth", "a poisonous water snake of the southeastern United States"),
        U("coral snake", "a brightly banded poisonous snake"),
        U("garter snake", "a harmless striped North American snake"),
        U("sea snake", "a poisonous snake that lives in the sea"),
        U("tuatara", "a lizardlike reptile of New Zealand"),
        U("snapping turtle", "a large freshwater turtle with powerful jaws"),
        U("box turtle", "a turtle that can close its shell completely"),
        U("painted turtle", "a North American turtle with red and yellow markings"),
        U("red-eared slider", "a turtle with a red stripe behind each eye, often kept as a pet"),
        U("giant tortoise", "a very large tortoise of the Galápagos and Aldabra islands"),
    ),
)

FISH = species_list(
    1253,
    "fish",
    "fish",
    (
        U("flounder", "a flat sea fish with both eyes on one side"),
        S("pike", "a long freshwater fish with sharp teeth"),
        U("sturgeon", "a large fish whose eggs are eaten as caviar"),
        S("ray", "a flat sea fish with wide fins like wings"),
        U("manta ray", "a very large ray of tropical seas"),
        U("barracuda", "a long, fierce fish of warm seas with sharp teeth"),
        U("guppy", "a small, brightly coloured freshwater fish often kept in tanks"),
        U("minnow", "a very small freshwater fish"),
        U("angelfish", "a brightly coloured tropical fish with a tall flat body"),
        U("pufferfish", "a fish that puffs up into a ball when threatened"),
        U("haddock", "a North Atlantic sea fish of the cod family"),
        U("plaice", "a flat European sea fish with orange spots"),
        S("sole", "a flat sea fish with an oval body"),
        U("turbot", "a large European flatfish"),
        U("hake", "a sea fish of the cod family"),
        U("pollock", "a North Atlantic sea fish of the cod family"),
        S("mullet", "a sea fish with a thick body, living in coastal waters"),
        U("tilapia", "a freshwater fish widely farmed for food"),
        S("snapper", "a reddish fish of warm seas"),
        U("grouper", "a large, heavy fish of warm seas"),
        U("bream", "a deep-bodied freshwater fish"),
        U("lamprey", "an eel-like jawless fish with a sucking mouth"),
        U("hammerhead", "a shark with a wide, flat, hammer-shaped head"),
        U("great white shark", "a very large and dangerous shark"),
        U("whale shark", "the largest fish, a shark that eats plankton"),
        U("marlin", "a large ocean fish with a long pointed snout"),
        U("flying fish", "a fish that glides above the water on wide fins"),
        U("lionfish", "a striped fish with poisonous spines"),
        U("koi", "a large, colourful carp kept in ponds"),
        U("monkfish", "a large sea fish with a huge head and mouth"),
        U("dogfish", "a small shark"),
        S("skate", "a flat sea fish like a ray"),
        U("stickleback", "a small fish with spines on its back"),
        U("sprat", "a small sea fish of the herring family"),
        U("coelacanth", "a rare deep-sea fish once thought to be extinct"),
        U("anglerfish", "a deep-sea fish that lures prey with a glowing growth on its head"),
        U("electric eel", "a South American fish that gives electric shocks"),
        U("moray eel", "a large eel of warm seas that hides in rocks"),
        U("parrotfish", "a brightly coloured tropical fish with a beaklike mouth"),
        U("arapaima", "a huge freshwater fish of the Amazon"),
        S("chimaera", "a deep-sea fish related to sharks, with a long thin tail"),
        U("milkfish", "a silvery fish farmed for food in Southeast Asia"),
        U("oarfish", "a very long, ribbonlike deep-sea fish"),
        U("scorpionfish", "a fish with poisonous spines that lies hidden on the sea floor"),
        U("sawfish", "a ray with a long, flat, toothed snout like a saw"),
        U("electric ray", "a ray that stuns its prey with electric shocks"),
        U("cichlid", "a freshwater fish of Africa and the Americas, often kept in aquariums"),
        U("killifish", "a small freshwater fish, often brightly coloured"),
        U("flatfish", "a fish with a flat body that lies on one side, such as a flounder"),
        U("goby", "a small fish of shallow coastal waters"),
        U("mahi-mahi", "a brightly coloured fish of warm seas, also called the dolphinfish"),
        U("sea bass", "a sea fish caught and farmed for food"),
        U("betta", "a small, brightly coloured fish, also called the Siamese fighting fish"),
        U("remora", "a fish that attaches itself to sharks and whales with a sucker"),
        U("sunfish", "the ocean sunfish, a huge, round, flat fish"),
        U("wrasse", "a brightly coloured fish of coral reefs"),
        S("tetra", "a small, colourful freshwater fish kept in aquariums"),
        U("bichir", "an African freshwater fish with a row of small fins on its back"),
        U("hilsa", "a fish of the herring family, prized as food in South Asia"),
        S("smelt", "a small silvery fish of coastal waters and lakes"),
        U("tiger shark", "a large shark with dark stripes"),
        U("nurse shark", "a slow-moving shark that rests on the sea floor"),
    ),
)

INSECTS = species_list(
    1254,
    "insects",
    "insect",
    (
        U("tsetse fly", "an African fly that spreads sleeping sickness"),
        U("housefly", "the common fly found in houses"),
        U("cicada", "an insect that makes a loud buzzing sound in summer"),
        S("louse", "a small insect that lives in hair and feathers"),
        U("bedbug", "a small insect that lives in beds and bites people"),
        U("mayfly", "an insect whose adult lives only a day or two"),
        U("stick insect", "an insect that looks like a twig"),
        U("earwig", "an insect with pincers at the end of its body"),
        U("aphid", "a tiny insect that sucks the juice of plants"),
        U("weevil", "a small beetle with a long snout that damages crops"),
        U("maggot", "the soft, legless larva of a fly"),
        U("gnat", "a small biting fly"),
        U("midge", "a tiny fly that flies in swarms"),
        U("horsefly", "a large fly that bites horses and people"),
        U("fruit fly", "a tiny fly attracted to ripe fruit"),
        U("scarab beetle", "a beetle sacred in ancient Egypt"),
        U("stag beetle", "a large beetle with antler-like jaws"),
        U("dung beetle", "a beetle that rolls balls of dung"),
        U("silkworm", "a caterpillar that spins silk"),
        U("monarch butterfly", "a large orange and black migrating butterfly"),
        U("fire ant", "a red ant with a painful sting"),
        U("black fly", "a small biting fly that breeds in running water"),
        U("botfly", "a fly whose larvae live as parasites inside animals"),
        U("crane fly", "a fly with very long legs"),
        U("blowfly", "a large, shiny fly that lays its eggs on meat"),
        U("leafhopper", "a small jumping insect that sucks plant juices"),
        U("scale insect", "a tiny insect that clings to plants under a waxy shell"),
        U("whitefly", "a tiny white insect that damages plants"),
        U("carpenter ant", "a large ant that nests in wood"),
        U("killer bee", "an aggressive hybrid honey bee of the Americas"),
        U("cabbage white", "a white butterfly whose caterpillars eat cabbages"),
        U("swallowtail", "a large butterfly with tail-like points on its back wings"),
        U("damselfly", "a slender insect like a small dragonfly"),
        U("mole cricket", "a burrowing insect with large front legs for digging"),
        U("katydid", "a green insect like a grasshopper with long antennae"),
    ),
)

OTHER_INVERTEBRATES = species_list(
    1255,
    "invertebrates",
    "animal",
    (
        S("black widow", "a poisonous black spider with a red mark", disambiguation="spider"),
        S("mite", "a tiny animal related to spiders"),
        U("barnacle", "a small shelled sea animal that sticks to rocks and ships"),
        U("krill", "tiny shrimplike sea animals eaten by whales"),
        U("woodlouse", "a small grey animal with a jointed shell that rolls into a ball"),
        U("hermit crab", "a crab that lives in an empty shell"),
        U("cuttlefish", "a sea animal related to the squid with a broad body"),
        U("scallop", "a shellfish with a fan-shaped shell"),
        U("cockle", "a small shellfish with a ribbed shell"),
        U("whelk", "a sea snail with a pointed shell"),
        U("limpet", "a sea snail with a cone-shaped shell that clings to rocks"),
        U("nautilus", "a sea animal related to the octopus with a coiled shell"),
        U("sea slug", "a soft, often brightly coloured sea animal without a shell"),
        U("tapeworm", "a long, flat worm that lives in the intestines"),
        U("roundworm", "a worm with a round body, often living as a parasite"),
        U("sea anemone", "a sea animal with a ring of stinging tentacles"),
        U("sea cucumber", "a long, soft-bodied sea animal on the sea floor"),
        U("sand dollar", "a flat, round sea urchin"),
        S("sponge", "a simple sea animal with a body full of holes"),
        U("Portuguese man o' war", "a floating sea animal with long stinging tentacles"),
        U("pseudoscorpion", "a tiny arachnid like a scorpion without a tail"),
        U("jumping spider", "a small spider that leaps on its prey"),
        U("ostracod", "a tiny crustacean with a two-part shell"),
        U("springtail", "a tiny wingless animal that jumps with a tail-like organ"),
        U("horseshoe crab", "a sea animal with a horseshoe-shaped shell, related to spiders"),
        U("tardigrade", "a tiny eight-legged water animal that can survive extreme conditions"),
        U("bristle worm", "a sea worm with bristles along its sides"),
        U("flatworm", "a simple worm with a flat body"),
    ),
)

EXTINCT_ANIMALS = species_list(
    1256,
    "extinct_animals",
    "animal",
    (
        U("tyrannosaurus", "a huge meat-eating dinosaur that walked on two legs"),
        U("triceratops", "a plant-eating dinosaur with three horns and a bony frill"),
        U("stegosaurus", "a plant-eating dinosaur with bony plates along its back"),
        U("velociraptor", "a small, fast, meat-eating dinosaur"),
        U("diplodocus", "a very long plant-eating dinosaur with a long neck and tail"),
        U("iguanodon", "a large plant-eating dinosaur with spiked thumbs"),
        U("allosaurus", "a large meat-eating dinosaur"),
        U("sauropod", "a huge plant-eating dinosaur with a long neck and tail"),
        U("theropod", "a meat-eating dinosaur that walked on two legs"),
        U("pterosaur", "a flying reptile of the age of the dinosaurs"),
        U("pterodactyl", "a flying reptile of the age of the dinosaurs"),
        U("plesiosaur", "a large sea reptile of the age of the dinosaurs with a long neck"),
        U("archaeopteryx", "the earliest known bird, with teeth and a bony tail"),
        U("dimetrodon", "a prehistoric animal with a large sail on its back"),
        U("trilobite", "an extinct sea arthropod with a three-part body"),
        U("sea scorpion", "a giant extinct sea arthropod, the eurypterid"),
        S("mammoth", "an extinct hairy elephant with long curved tusks", pos="noun"),
        U("mastodon", "an extinct animal like an elephant"),
        U("aurochs", "an extinct wild ox, the ancestor of cattle"),
        U("dodo", "a large flightless bird of Mauritius, now extinct"),
        U("moa", "a giant flightless bird of New Zealand, now extinct"),
        U("passenger pigeon", "a North American pigeon, once very common, now extinct"),
        U("Neanderthal", "an extinct human species of Ice Age Europe and Asia"),
        U("australopithecus", "an early human ancestor of Africa"),
    ),
)

DOG_BREEDS = species_list(
    1257,
    "breeds",
    "dog",
    (
        U("terrier", "a small, lively dog originally bred to hunt animals in burrows"),
        U("mastiff", "a very large, powerful dog bred as a guard dog"),
        S("spitz", "a dog with a thick coat, pointed ears and a curled tail"),
        U("gun dog", "a dog trained to find and bring back birds that hunters shoot"),
        U("poodle", "a dog with a thick curly coat, often clipped into shapes"),
        U("bulldog", "a muscular dog with a large head, short legs and a flat face"),
        S("Labrador", "a friendly retriever with a short yellow, black or brown coat"),
        U("golden retriever", "a friendly dog with a long golden coat"),
        U("German shepherd", "a large, intelligent dog used by police and as a guard dog"),
        U("beagle", "a small hound with long ears, used for hunting hares"),
        U("dachshund", "a dog with a long body and very short legs"),
        U("chihuahua", "a very small dog from Mexico with large ears"),
        U("rottweiler", "a large, strong black and tan guard dog"),
        S("boxer", "a medium-sized, muscular dog with a short square muzzle"),
        U("Dalmatian", "a white dog with black or brown spots"),
        U("greyhound", "a slim, very fast dog used for racing"),
        S("husky", "a strong dog with a thick coat, used to pull sledges", pos="noun"),
        U("collie", "a long-haired dog bred for herding sheep"),
        U("pug", "a small dog with a wrinkled flat face and a curled tail"),
        U("Great Dane", "a very tall, large dog with a short coat"),
        U("Doberman", "a tall, sleek black and tan guard dog"),
        U("Pomeranian", "a tiny dog with a thick, fluffy coat"),
        U("corgi", "a small herding dog with short legs and a long body"),
        U("bloodhound", "a large hound with a very keen sense of smell"),
        U("Saint Bernard", "a very large mountain dog known for rescuing travellers"),
        U("schnauzer", "a dog with a wiry coat, bushy eyebrows and a beard"),
        U("cocker spaniel", "a small spaniel with long silky ears"),
        U("shih tzu", "a small dog from China with long, silky hair"),
        U("basset hound", "a hound with short legs, a long body and droopy ears"),
        U("Shiba Inu", "a small Japanese dog with a curled tail, like a fox"),
        U("spaniel", "a dog with long drooping ears and a silky coat"),
        U("retriever", "a dog bred to bring back game that hunters have shot"),
        U("mongrel", "a dog of no particular breed, or of mixed breeds"),
    ),
)

OTHER_BREEDS = species_list(
    1258,
    "breeds",
    "breed",
    (
        # Cats
        U("Siamese cat", "a short-haired cat with blue eyes and a pale body"),
        U("Persian cat", "a cat with long fluffy fur and a flat face"),
        U("Maine Coon", "a very large, long-haired cat from North America"),
        S("Sphynx", "a hairless breed of cat", disambiguation="cat"),
        U("Bengal cat", "a cat with a spotted coat like a leopard"),
        S("ragdoll", "a large, calm cat with blue eyes that goes limp when held"),
        U("British Shorthair", "a sturdy cat with a dense grey-blue coat"),
        S("Abyssinian", "a slender cat with a short, ticked golden-brown coat"),
        S("Burmese", "a short-haired cat with a glossy brown coat", disambiguation="cat"),
        U("Russian Blue", "a cat with a short silvery-blue coat and green eyes"),
        U("Scottish Fold", "a cat whose ears fold forward"),
        S("Manx", "a cat with no tail", disambiguation="cat"),
        S("tabby", "a cat with a striped coat", disambiguation="cat"),
        # Horses
        S("thoroughbred", "a horse of the breed used for racing", pos="noun"),
        U("Arabian horse", "a graceful horse breed from the Arabian Peninsula"),
        U("Andalusian horse", "a strong horse breed from Spain"),
        U("Friesian horse", "a large black horse breed from the Netherlands"),
        U("Shetland pony", "a small, strong pony with a thick coat"),
        U("Clydesdale", "a large Scottish draught horse with long hair on its lower legs"),
        U("Shire horse", "a very large English draught horse"),
        S("mustang", "a wild horse of the American West", disambiguation="horse"),
        U("Appaloosa", "a horse with a spotted coat"),
        U("quarter horse", "an American horse breed that is very fast over short distances"),
        U("Lipizzaner", "a white horse breed famous for classical riding displays"),
        S("palomino", "a horse with a golden coat and a white mane and tail"),
        U("Percheron", "a large French draught horse, usually grey or black"),
        U("draught horse", "a large, strong horse bred to pull heavy loads"),
        # Cattle
        S("Hereford", "a red and white breed of beef cattle", disambiguation="cattle"),
        S("Holstein", "a black and white breed of dairy cattle", disambiguation="cattle"),
        S("Brahman", "a humped breed of cattle from India", disambiguation="cattle"),
        S("Angus", "a black, hornless breed of beef cattle", disambiguation="cattle"),
        S("Jersey", "a small brown breed of dairy cattle", disambiguation="cattle"),
        S("Guernsey", "a fawn and white breed of dairy cattle", disambiguation="cattle"),
        U("Highland cattle", "a Scottish breed of cattle with long horns and a shaggy coat"),
        U("Texas Longhorn", "an American breed of cattle with very long horns"),
        S("Charolais", "a large white breed of beef cattle from France"),
        S("Wagyu", "a Japanese breed of beef cattle", disambiguation="cattle"),
        # Sheep, goats, pigs and poultry
        S("merino", "a breed of sheep with very fine wool", disambiguation="sheep"),
        S("Suffolk", "a breed of sheep with a black face and legs", disambiguation="sheep"),
        U("Angora goat", "a goat whose long silky hair gives mohair"),
        U("cashmere goat", "a goat whose fine undercoat gives cashmere wool"),
        U("Angora rabbit", "a rabbit with long, soft wool"),
        S("Berkshire", "a black breed of pig with white markings", disambiguation="pig"),
        U("pot-bellied pig", "a small pig with a sagging belly, often kept as a pet"),
        S("Leghorn", "a breed of chicken known for laying many white eggs"),
        U("Rhode Island Red", "a reddish-brown breed of chicken"),
        S("bantam", "a small breed of chicken", disambiguation="chicken"),
    ),
)

MOVES = (
    LevelMove("N02_098", "platypus", 331),
    LevelMove("N02_091", "bison", 331),
    LevelMove("N02_164", "crane", 332),
    LevelMove("N02_162", "cod", 333),
    LevelMove("N02_095", "catfish", 333),
    LevelMove("N02_156", "cardinal", 1251),
    LevelMove("N02_088", "kite", 1251),
    LevelMove("N02_170", "quail", 1251),
    LevelMove("N02_094", "hagfish", 1253),
    LevelMove("N02_097", "lungfish", 1253),
    LevelMove("N02_115", "bass", 1253),
    LevelMove("N02_166", "herring", 1253),
    LevelMove("N02_096", "crayfish", 1255),
)

SENSE_LISTS = (
    EVERYDAY_WILD,
    EVERYDAY_SMALL_AND_SEA,
    WILD_MAMMALS,
    BIRDS_REPTILES,
    FISH_INSECTS_SEA,
    KINDS_OF_ANIMALS,
    ZOOLOGY_TERMS,
    MAMMALS,
    BIRDS,
    REPTILES_AMPHIBIANS,
    FISH,
    INSECTS,
    OTHER_INVERTEBRATES,
    EXTINCT_ANIMALS,
    DOG_BREEDS,
    OTHER_BREEDS,
)


def print_level_names() -> None:
    print("Level names (set after an --execute run, where unnamed and holding words):")
    for level, level_name in LEVEL_NAMES.items():
        print(f"  {level}: {level_name.name} ({level_name.cefr})")
    print()


def name_levels(config: DataSourceConfig) -> None:
    """Name each level that has words and no name; a name already given is kept."""
    session = create_session(config)
    try:
        for level, level_name in LEVEL_NAMES.items():
            existing = get_curriculum_level(session, level)
            if existing is not None and (existing.name or "").strip():
                print(f"  {level}: keeps its name {existing.name!r}")
                continue
            word_count = session.query(Lemma).filter(Lemma.difficulty_level == level).count()
            if not word_count:
                print(f"  {level}: no words, left unnamed")
                continue
            set_curriculum_level(
                session, level, level_name.name, cefr=level_name.cefr, source=SOURCE
            )
            print(f"  {level}: named {level_name.name!r}")
        session.commit()
    finally:
        session.close()


def main() -> int:
    print_level_names()
    status = run_sense_import(SENSE_LISTS, __doc__ or "", moves=MOVES)
    if "--execute" in sys.argv[1:]:
        print("Naming levels:")
        name_levels(DataSourceConfig())
    return status


if __name__ == "__main__":
    raise SystemExit(main())
