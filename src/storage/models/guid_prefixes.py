"""GUID prefix mappings and metadata for POS subtypes.

:data:`SUBTYPE_DEFS` is the single source of truth. A subtype is defined here
once -- its GUID prefix, what it means, and examples -- and everything else in
this module is derived from it: the prefix lookup callers have always used, the
inverted prefix->subtype map, and the ``*Subtype`` enums in
:mod:`storage.models.enums`.

Adding a subtype is therefore one edit here rather than four in sync. Two rules
the tests in ``src/tests/storage/test_pos_enum_helpers.py`` enforce:

* A new GUID prefix must be **greater than every prefix currently used for that
  POS**, never a gap left by a retired subtype. A reused number would collide
  with GUIDs already issued under the old meaning.
* A prefix is permanent. Renaming a subtype is fine; renumbering it is not.

``SubtypeDef.comment`` is for maintainers -- why a subtype exists, what it was
carved out of, what does *not* belong in it. It is deliberately excluded from
anything sent to an LLM; ``description`` and ``examples`` are the fields a
classification prompt is built from.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SubtypeDef:
    """One POS subtype: its GUID prefix and what it means.

    Args:
        prefix: GUID prefix, unique within the POS type (e.g. ``"N58"``).
        description: Short gloss, written to be read by a classifier. Empty
            where nobody has written one yet.
        examples: Representative words, also prompt-visible.
        comment: Maintainer note. Never sent to an LLM.
        member_name: Enum member name, when it is not ``subtype.upper()``.
            Only ``animal_grouping_term`` (``GROUP_ANIMAL``) needs this.
        group: Heading this subtype is displayed under on the category page,
            scoped to its POS -- a noun "Other" and a verb "Other" are separate
            headings. Grouping is presentation only: nothing derives a GUID or
            a prompt from it. It lives here so that adding a subtype makes it
            visible in the UI by the same edit that gives it a prefix; when it
            was a separate hand-written list, three subtypes had been defined
            here and rendered nowhere.
        deprecated: The subtype is no longer a valid choice for new words. It
            keeps its prefix and its enum member -- existing GUIDs and the code
            that names it must go on working -- but it is withheld from every
            classification prompt so nothing new is filed under it. The prefix
            is never reissued.
    """

    prefix: str
    description: str = ""
    examples: List[str] = field(default_factory=list)
    comment: str = ""
    member_name: Optional[str] = None
    group: str = "Other"
    deprecated: bool = False


SUBTYPE_DEFS: Dict[str, Dict[str, SubtypeDef]] = {
    "noun": {
        "human": SubtypeDef(
            prefix="N01",
            description="People and human roles not covered by a narrower subtype",
            examples=["person", "adult", "baby", "friend", "expert"],
            group="People and Living Things",
        ),
        "family_relation": SubtypeDef(
            prefix="N35",
            description="Family members",
            examples=["brother", "uncle", "cousin", "parent"],
            group="People and Living Things",
        ),
        "occupation": SubtypeDef(
            prefix="N36",
            description="Jobs and professions a person is employed in",
            examples=["teacher", "doctor", "accountant", "referee", "telephone lineman"],
            group="People and Living Things",
        ),
        "participant_role": SubtypeDef(
            prefix="N63",
            description=(
                "A slot a person fills inside a game, team, performance or event, "
                "not a job they are employed in"
            ),
            examples=["goalkeeper", "second baseman", "football lineman", "captain", "best man"],
            comment=(
                "The test against occupation is whether the word names a slot inside "
                "the activity or a job someone holds: second baseman is a slot, a "
                "referee or a card dealer is a job. Named for the sports and games "
                "wordlists, but meant for theater roles and ceremonies as well. It "
                "first shipped without a description, and the bare name drew referee "
                "and umpire into it; hence the description and the job examples on "
                "occupation."
            ),
            group="People and Living Things",
        ),
        "honorific": SubtypeDef(
            prefix="N48",
            description="Titles and forms of address",
            examples=["Sir", "Lord", "Mr.", "Mrs.", "Dr."],
            group="People and Living Things",
        ),
        "animal": SubtypeDef(
            prefix="N02",
            description="Animals",
            examples=["dog", "bird", "fish", "bee", "wolf"],
            group="People and Living Things",
        ),
        "body_part": SubtypeDef(
            prefix="N03",
            description="Parts of a human or animal body",
            examples=["arm", "eye", "heart", "muscle", "bone"],
            group="People and Living Things",
        ),
        "disease_condition": SubtypeDef(
            prefix="N04",
            description="Illnesses, injuries and medical conditions",
            examples=["cancer", "fever", "allergy", "infection", "broken bone"],
            group="People and Living Things",
        ),
        "plant": SubtypeDef(
            prefix="N05",
            description="Whole plants",
            examples=["rose", "oak", "bush", "moss", "weed"],
            group="People and Living Things",
        ),
        "plant_part": SubtypeDef(
            prefix="N38",
            description="Parts of plants",
            examples=["leaf", "root", "seed", "petal", "bark"],
            group="People and Living Things",
        ),
        "food": SubtypeDef(
            prefix="N06",
            description="Solid consumables",
            examples=["bread", "apple", "rice", "meat"],
            group="Food and Consumables",
        ),
        "beverage": SubtypeDef(
            prefix="N42",
            description="Liquid consumables",
            examples=["water", "coffee", "tea", "juice"],
            group="Food and Consumables",
        ),
        "building_structure": SubtypeDef(
            prefix="N07",
            description="Buildings and built structures",
            examples=["house", "hospital", "fire station", "library", "stadium"],
            comment=(
                "bridge is path_infrastructure, and a room is building_part. The line "
                "against place_name is open: a zoo, airport, campsite or cemetery is "
                "land with buildings on it, and has not been settled either way."
            ),
            group="Physical Objects and Structures",
        ),
        "building_part": SubtypeDef(
            prefix="N47",
            description="Parts of buildings, including rooms",
            examples=["door", "window", "wall", "stairs", "room", "kitchen", "classroom"],
            comment=(
                "Rooms had been split between building_structure (bedroom, kitchen) "
                "and place_name, whose examples named room; every room is filed here."
            ),
            group="Physical Objects and Structures",
        ),
        "furniture": SubtypeDef(
            prefix="N39",
            description="Furniture items",
            examples=["table", "chair", "desk", "sofa", "bed"],
            group="Physical Objects and Structures",
        ),
        "small_movable_object": SubtypeDef(
            prefix="N08",
            description="Portable physical objects with no narrower subtype",
            examples=["book", "key", "bag", "box", "candle"],
            comment=(
                "The catch-all for concrete objects, as concept_idea is for "
                "abstractions; noun_other mixes the two and is worse. It was "
                "'portable everyday objects', which overlapped tool and drew in "
                "kitchenware, sports and game equipment and machine parts, all of "
                "which now have subtypes of their own. A personal_item subtype "
                "(wallet, comb, toothbrush, soap, shampoo) is planned for a later round."
            ),
            group="Physical Objects and Structures",
        ),
        "clothing_accessory": SubtypeDef(
            prefix="N09",
            description="Clothing and things worn",
            examples=["shirt", "shoe", "hat", "glove", "ring"],
            group="Physical Objects and Structures",
        ),
        "artwork_artifact": SubtypeDef(
            prefix="N10",
            description=(
                "Physical objects made as art or for cultural use: artworks, crafts "
                "and musical instruments"
            ),
            examples=["statue", "painting", "pottery", "violin", "drum"],
            comment=(
                "Musical instruments had no subtype and were spread across tool, "
                "appliance, activity and this one. A work or genre that is not a "
                "physical object (novel, sonnet, opera, comedy) is creative_work."
            ),
            group="Physical Objects and Structures",
        ),
        "creative_work": SubtypeDef(
            prefix="N69",
            description=(
                "A kind of work of literature, music, film, broadcasting or "
                "performance, or a genre of one, as distinct from a physical object"
            ),
            examples=["novel", "sonnet", "symphony", "opera", "comedy"],
            comment=(
                "Carved out of artwork_artifact, which had held both statues and "
                "sonatas. A painting or photograph as an object stays artwork_artifact; "
                "the field of study (literature, musicology) is knowledge_domain."
            ),
            group="Abstract Concepts and Ideas",
        ),
        "legal_document": SubtypeDef(
            prefix="N58",
            description="Documents with legal force",
            examples=["will", "deed", "passport", "subpoena"],
            group="Abstract Concepts and Ideas",
        ),
        "natural_feature": SubtypeDef(
            prefix="N11",
            description=(
                "Kinds of landform, body of water and natural area, and natural "
                "phenomena such as weather"
            ),
            examples=["river", "island", "cloud", "beach", "volcano"],
            comment=(
                "Generic kinds only: a named river or mountain range (Nile, Alps) is "
                "named_geographic_feature."
            ),
            group="Places and Geography",
        ),
        "celestial_object": SubtypeDef(
            prefix="N64",
            description=(
                "Anything in the sky beyond the atmosphere, as a kind or by name, "
                "including constellations"
            ),
            examples=["star", "planet", "comet", "galaxy", "Mars", "Orion"],
            comment=(
                "Anything in the sky beyond the atmosphere, as a kind or by name: star, "
                "planet, moon, asteroid, comet, galaxy, nebula, and Sirius, Mars, "
                "Halley's Comet. Constellations are filed here too although strictly "
                "they are regions of the sky, not objects -- a learner files Orion with "
                "the stars that make it. Weather (cloud, rainbow, aurora) stays "
                "natural_feature. Carved out of natural_feature, whose examples named "
                "star; sun, moon, planet and star were stored there before this "
                "existed."
            ),
            group="Physical Objects and Structures",
        ),
        "tool": SubtypeDef(
            prefix="N12",
            description=(
                "Implements held in the hand and used on a material or object to do a "
                "job such as cutting, fastening, digging, measuring or shaping, and "
                "fastening hardware"
            ),
            examples=["hammer", "saw", "screwdriver", "shovel", "nail"],
            comment=(
                "Was 'hand tools and generic tools', which took anything used for a "
                "purpose: musical instruments, rackets, pans and engines. Those are "
                "artwork_artifact, sports_game_equipment, kitchenware and machine_part."
            ),
            group="Physical Objects and Structures",
        ),
        "sports_game_equipment": SubtypeDef(
            prefix="N70",
            description=(
                "Equipment and pieces used to play a sport or game: balls, bats, "
                "rackets, sticks, apparatus, goals, boards, pieces, cards, tiles and dice"
            ),
            examples=["ball", "tennis racket", "puck", "pawn", "domino"],
            comment=(
                "Rackets, clubs and gymnastics apparatus had been tool; balls, chess "
                "pieces, cards and mahjong tiles small_movable_object. Gear that is "
                "worn as clothing (glove, gi, helmet) stays clothing_accessory; skis "
                "and skates are this. A playing area is place_name, its lines "
                "spatial_division."
            ),
            group="Physical Objects and Structures",
        ),
        "kitchenware": SubtypeDef(
            prefix="N71",
            description=(
                "Unpowered things for preparing, cooking, serving or eating food: "
                "cookware, utensils and tableware"
            ),
            examples=["frying pan", "spatula", "plate", "fork", "cutting board"],
            comment=(
                "Anything powered (oven, toaster, kettle) is appliance. These had "
                "been split between small_movable_object, tool and appliance."
            ),
            group="Physical Objects and Structures",
        ),
        "machine_part": SubtypeDef(
            prefix="N72",
            description="A component of a machine, vehicle or device, named for its job in it",
            examples=["engine", "gear", "brake", "steering wheel", "button"],
            comment=(
                "Had been split between tool, small_movable_object and vehicle, which "
                "kept trading them. Fasteners (screw, bolt) stay tool; batteries, "
                "plugs and cables stay electronic_device. button is the push-button "
                "sense; the clothing button is clothing_accessory."
            ),
            group="Physical Objects and Structures",
        ),
        "electronic_device": SubtypeDef(
            prefix="N57",
            description="Devices that run on electricity to compute, communicate or record",
            examples=["computer", "telephone", "television", "radio", "camera"],
            group="Physical Objects and Structures",
        ),
        "appliance": SubtypeDef(
            prefix="N43",
            description="Kitchen and household appliances",
            examples=["blender", "microwave", "toaster"],
            group="Physical Objects and Structures",
        ),
        "weapon": SubtypeDef(
            prefix="N44",
            description="Weapons and arms",
            examples=["sword", "gun", "bow", "shield"],
            group="Physical Objects and Structures",
        ),
        "vehicle": SubtypeDef(
            prefix="N40",
            description="Transportation",
            examples=["car", "truck", "bicycle", "boat", "airplane"],
            group="Physical Objects and Structures",
        ),
        "path_infrastructure": SubtypeDef(
            prefix="N13",
            description="Ways through a place and the infrastructure of routes",
            examples=["road", "bridge", "sidewalk", "intersection", "bus stop"],
            group="Physical Objects and Structures",
        ),
        "material_substance": SubtypeDef(
            prefix="N14",
            description="Materials and stuff things are made of",
            examples=["wood", "metal", "glass", "oil", "brick"],
            group="Materials and Substances",
        ),
        "chemical_compound": SubtypeDef(
            prefix="N15",
            description="Chemical elements and compounds",
            examples=["oxygen", "lithium", "carbon dioxide"],
            group="Materials and Substances",
        ),
        "medication_remedy": SubtypeDef(
            prefix="N16",
            description="Medicines and treatments",
            examples=["aspirin", "vaccine", "antibiotic", "ointment", "painkiller"],
            group="Materials and Substances",
        ),
        "concept_idea": SubtypeDef(
            prefix="N17",
            description="General abstractions with no narrower subtype",
            examples=["fact", "effect", "type", "case", "way"],
            group="Abstract Concepts and Ideas",
        ),
        "communication_information": SubtypeDef(
            prefix="N50",
            description="Language, messages, information",
            examples=["word", "language", "message", "news"],
            group="Abstract Concepts and Ideas",
        ),
        "technology_digital": SubtypeDef(
            prefix="N52",
            description="Digital/computing concepts",
            examples=["internet", "email", "website", "data"],
            group="Abstract Concepts and Ideas",
        ),
        "abstract_condition": SubtypeDef(
            prefix="N54",
            description="Abstract conditions, situations",
            examples=["peace", "danger", "luck", "fate"],
            group="Abstract Concepts and Ideas",
        ),
        "social_institution": SubtypeDef(
            prefix="N55",
            description="Organizations, collective structures",
            examples=["government", "army", "company"],
            group="Abstract Concepts and Ideas",
        ),
        "activity": SubtypeDef(
            prefix="N41",
            description="Activities and hobbies",
            examples=["reading", "cooking", "sports", "dancing", "hiking"],
            group="Abstract Concepts and Ideas",
        ),
        "performance_technique": SubtypeDef(
            prefix="N61",
            description=(
                "A named way of carrying out an action, defined by its form, such as a "
                "kind of stroke, shot, kick or stitch"
            ),
            examples=["layup", "volley", "topspin", "uppercut", "backstitch"],
            comment=(
                "A named way of carrying out an action, defined by its form: layup, "
                "bicycle kick, uppercut, axel, backstitch, plie, julienne. The test "
                "against strategic_tactic is form against aim -- a layup is how the "
                "shot is made, a pick and roll is what the play is for. activity is a "
                "pursuit (reading, hiking), not one named way of doing something."
            ),
            group="Abstract Concepts and Ideas",
        ),
        "strategic_tactic": SubtypeDef(
            prefix="N62",
            description=(
                "A named move, play or plan defined by what it is meant to achieve, "
                "not by any rules"
            ),
            examples=["fork", "gambit", "pick and roll", "bluff", "pincer movement"],
            comment=("A move the rules define (castling) is rule_defined_event instead."),
            group="Abstract Concepts and Ideas",
        ),
        "symbolic_element": SubtypeDef(
            prefix="N18",
            description="Symbols, marks and notational elements",
            examples=["digit", "numeral", "graph", "motif", "license plate"],
            group="Abstract Concepts and Ideas",
        ),
        "quality_attribute": SubtypeDef(
            prefix="N19",
            description="A named property something has, treated as a thing",
            examples=["importance", "efficiency", "durability", "reputation", "hardness"],
            group="Abstract Concepts and Ideas",
        ),
        "mental_construct": SubtypeDef(
            prefix="N20",
            description="Products of thought: ideas held, formed or believed",
            examples=["idea", "belief", "theory", "decision", "doubt"],
            group="Abstract Concepts and Ideas",
        ),
        "legal_concept": SubtypeDef(
            prefix="N59",
            description="Legal doctrines and standards",
            examples=["stare decisis", "probable cause"],
            group="Abstract Concepts and Ideas",
        ),
        "knowledge_domain": SubtypeDef(
            prefix="N21",
            description="Broad fields of study and bodies of knowledge",
            examples=["biology", "history", "philosophy", "mathematics", "machine learning"],
            group="Abstract Concepts and Ideas",
        ),
        "quantitative_concept": SubtypeDef(
            prefix="N22",
            description="Amounts, measures and magnitudes as concepts",
            examples=["number", "distance", "size", "level", "half"],
            group="Abstract Concepts and Ideas",
        ),
        "mathematical_concept": SubtypeDef(
            prefix="N66",
            description=(
                "Constructs and terms of mathematics: equations, functions, operations, "
                "theorems and the objects they act on"
            ),
            examples=["equation", "polynomial", "sine", "theorem", "matrix"],
            comment=(
                "Math terms had been scattered across knowledge_domain (polynomial, "
                "sine), quantitative_concept (logarithm, quotient) and concept_idea "
                "(axiom), none of which fits. The field is still knowledge_domain "
                "(mathematics, algebra), a plain amount is still quantitative_concept "
                "(number, half), and a figure keeps shape (parabola). Numbers "
                "themselves are numerals: Z01 cardinals, Z02 ordinals."
            ),
            group="Abstract Concepts and Ideas",
        ),
        "linguistic_concept": SubtypeDef(
            prefix="N67",
            description=(
                "Technical terms for the units, categories and features of language: "
                "word classes, grammatical categories, sound classes, word parts, "
                "relations between words, and language varieties"
            ),
            examples=["noun", "tense", "morpheme", "suffix", "dialect"],
            comment=(
                "Linguistics terms had been scattered across knowledge_domain (noun, "
                "dative, dialect), concept_idea (tense, vocative), "
                "communication_information (morpheme, plosive) and symbolic_element "
                "(affix, suffix). The fields stay knowledge_domain (grammar, phonology, "
                "semantics); everyday language things stay communication_information "
                "(word, sentence, question); written marks stay symbolic_element "
                "(comma, grapheme). vowel, consonant and syllable were left where "
                "they were for now."
            ),
            group="Abstract Concepts and Ideas",
        ),
        "emotion_feeling": SubtypeDef(
            prefix="N23",
            description="Emotions and felt states",
            examples=["fear", "joy", "anger", "pride", "shame"],
            group="Abstract Concepts and Ideas",
        ),
        "shape": SubtypeDef(
            prefix="N37",
            description="Geometric shapes",
            examples=["circle", "triangle", "square", "rectangle", "etc."],
            group="Abstract Concepts and Ideas",
        ),
        "process_event": SubtypeDef(
            prefix="N24",
            description="Things that happen or unfold over time",
            examples=["war", "flight", "development", "process", "attempt"],
            group="Processes and Time",
        ),
        "rule_defined_event": SubtypeDef(
            prefix="N60",
            description=(
                "A move, outcome, state or violation that the rules of a game or "
                "procedure themselves define and name"
            ),
            examples=["checkmate", "castling", "strikeout", "offside", "quorum"],
            comment=(
                "A move, outcome, state or violation that the formal rules of a game "
                "or procedure define and name: checkmate, castling, strikeout, "
                "offside, deuce, quorum, point of order. The test is whether the rules "
                "themselves use the term; a named plan the rules do not mention is "
                "strategic_tactic. Carved out of process_event, which had taken "
                "checkmate and double play for want of anything closer."
            ),
            group="Processes and Time",
        ),
        "time_period": SubtypeDef(
            prefix="N25",
            description="Spans and points of time",
            examples=["year", "hour", "century", "night", "autumn"],
            group="Processes and Time",
        ),
        "group_people": SubtypeDef(
            prefix="N26",
            description="Organized or recognizable groups of people",
            examples=["team", "audience", "orchestra", "clan", "working class"],
            group="Groups and Collections",
        ),
        "animal_grouping_term": SubtypeDef(
            prefix="N27",
            description="Measure words for animals",
            examples=["flock", "herd", "head"],
            member_name="GROUP_ANIMAL",
            group="Groups and Collections",
        ),
        "collection_things": SubtypeDef(
            prefix="N28",
            description="Sets and aggregations of things",
            examples=["collection", "equipment", "goods", "edition", "first aid kit"],
            group="Groups and Collections",
        ),
        "personal_name": SubtypeDef(
            prefix="N29",
            description="Given or full names of individuals",
            deprecated=True,
            comment=(
                "Deprecated: personal names live in the names table under the "
                "E* prefixes, not as lemmas, and no lemma has carried this "
                "subtype for some time. The member and prefix stay because "
                "words.term_age and a sentence pattern still name it, and N29 "
                "must never be reissued. Stage a name as a pending import with "
                "target_kind='name' instead."
            ),
            group="Named Entities",
        ),
        "place_name": SubtypeDef(
            prefix="N30",
            description=(
                "An area of land laid out or kept for a use: parks, gardens, yards, "
                "farms and playing areas"
            ),
            examples=["park", "garden", "playground", "farm", "tennis court"],
            comment=(
                "Not proper names, despite the name; renaming it (the prefix stays) is "
                "deferred until the line against building_structure is settled. A zoo, "
                "airport, campsite or cemetery is land with buildings on it, and could "
                "go either way: one option is building vs site (one building is "
                "building_structure, an area of land is this), another is a single "
                "subtype for every place one goes to for a purpose. A playing surface "
                "(court, rink) is this even when indoors. It used to hold compass "
                "points and inside/outside (now spatial_division), country and state "
                "(geographic_place) and rooms (building_part)."
            ),
            group="Places and Geography",
        ),
        "region": SubtypeDef(
            prefix="N45",
            description=(
                "Proper names of countries, states, provinces, continents, and named "
                "cultural or historical regions"
            ),
            examples=["Italy", "California", "Europe", "Scandinavia"],
            comment=(
                "Proper names only. The generic words (kingdom, province, region) are "
                "geographic_place."
            ),
            group="Named Entities",
        ),
        "spatial_division": SubtypeDef(
            prefix="N65",
            description=(
                "A part of a space or surface named by its position, a direction, or a "
                "rule or convention: a compass direction or the part of a region lying "
                "in it, a side or part of a thing, or a line, row, cell or zone"
            ),
            examples=["north", "northeast", "top", "border", "equator", "goal line"],
            comment=(
                "Compass points and relative positions (north, inside, top, middle) "
                "were added later: they had sat in place_name and concept_idea, and a "
                "description that named only divisions by rule left the review calling "
                "them borderline. "
                "A named division of a laid-out space: equator, time zone, border, "
                "lane, aisle, margin, row, column, goal line, penalty area, and the "
                "file, rank, diagonal and square of a game board. The test is that it "
                "names a division of a space, not the space and not a thing in it: "
                "the court is place_name and its baseline is this; a country is "
                "region and the border between two is this; a net or a curb keeps "
                "its object subtype. Marks on paper are symbolic_element instead "
                "(a musical staff). Carved out of place_name, path_infrastructure, "
                "symbolic_element and concept_idea, which had each taken some of "
                "these for want of anything closer."
            ),
            group="Places and Geography",
        ),
        "city": SubtypeDef(
            prefix="N46",
            description="Proper names of cities and towns",
            examples=["Vilnius", "Paris", "Tokyo"],
            comment="The generic words (capital, borough, metropolis) are geographic_place.",
            group="Named Entities",
        ),
        "geographic_place": SubtypeDef(
            prefix="N56",
            description=(
                "Kinds of area defined by people: settlements, parts of a town, "
                "political and administrative divisions, and general words for an area"
            ),
            examples=["village", "suburb", "district", "province", "area"],
            comment=(
                "Was 'named geographic features' with ocean examples, though most of "
                "its words were already generic (village, downtown, countryside). The "
                "proper names went to named_geographic_feature. The test against "
                "place_name is whether the area is defined by settlement or "
                "administration (here) or by what the land is used for (place_name); "
                "against natural_feature, by people or by nature."
            ),
            group="Places and Geography",
        ),
        "named_geographic_feature": SubtypeDef(
            prefix="N68",
            description=(
                "Proper names of landforms and bodies of water: oceans, seas, rivers, "
                "lakes, mountains and ranges, deserts and islands"
            ),
            examples=["Atlantic Ocean", "Nile", "Alps", "Sahara", "Baltic Sea"],
            comment=(
                "Split out of geographic_place, which was described as named features "
                "but mostly held generic words. Countries, continents and named "
                "cultural regions are region; cities are city; a named body in the sky "
                "is celestial_object."
            ),
            group="Named Entities",
        ),
        "organization_name": SubtypeDef(
            prefix="N31",
            description="Named organizations and companies",
            examples=["Coca-Cola", "agency", "small business"],
            group="Named Entities",
        ),
        "language_name": SubtypeDef(
            prefix="N73",
            description="Proper names of languages",
            examples=["English", "Lithuanian", "Chinese", "Swahili"],
            comment=(
                "Language names had been filed under communication_information "
                "beside word and message. The generic words stay where they were: "
                "language is communication_information, and dialect, creole and "
                "pidgin are linguistic_concept. A person of a nationality is "
                "nationality."
            ),
            group="Named Entities",
        ),
        "temporal_name": SubtypeDef(
            prefix="N32",
            description="Named days of the week, months and holidays",
            examples=["Monday", "January", "Christmas", "New Year"],
            group="Other Categories",
        ),
        "nationality": SubtypeDef(
            prefix="N33",
            description="A person of a nationality or origin",
            examples=["American", "Lithuanian", "Finn", "Englishman", "Pole"],
            group="Other Categories",
        ),
        "unit_of_measurement": SubtypeDef(
            prefix="N34",
            description="Units things are measured in",
            examples=["meter", "kilogram", "liter", "degree", "mile"],
            group="Other Categories",
        ),
        "noun_other": SubtypeDef(
            prefix="N99",
            member_name="OTHER",
            group="Other Categories",
        ),
    },
    "verb": {
        "physical_action": SubtypeDef(
            prefix="V01",
            description="Physical actions",
            examples=["push", "pull", "lift", "eat", "drink"],
            group="Physical Actions",
        ),
        "creation_action": SubtypeDef(
            prefix="V02",
            description="Creating things",
            examples=["make", "create", "build"],
            group="Physical Actions",
        ),
        "destruction_action": SubtypeDef(
            prefix="V03",
            description="Destroying",
            examples=["break", "destroy", "demolish"],
            group="Physical Actions",
        ),
        "mental_state": SubtypeDef(
            prefix="V04",
            description="Cognition",
            examples=["know", "believe", "understand", "think"],
            group="Mental and Emotional",
        ),
        "emotional_state": SubtypeDef(
            prefix="V05",
            description="Feelings",
            examples=["love", "hate", "fear", "enjoy"],
            group="Mental and Emotional",
        ),
        "perception": SubtypeDef(
            prefix="V10",
            description="Sensory verbs",
            examples=["see", "hear", "smell", "taste", "feel", "touch"],
            group="Mental and Emotional",
        ),
        "communication": SubtypeDef(
            prefix="V09",
            description="Speaking and writing",
            examples=["say", "tell", "speak", "write", "read"],
            group="Communication and Possession",
        ),
        "possession": SubtypeDef(
            prefix="V06",
            description="Having/owning",
            examples=["have", "own", "possess", "give", "take"],
            group="Communication and Possession",
        ),
        "existence": SubtypeDef(
            prefix="V11",
            description="Living/existing",
            examples=["live", "exist", "die", "survive", "stay", "remain"],
            group="Existence and Change",
        ),
        "development": SubtypeDef(
            prefix="V07",
            description="Growing/evolving",
            examples=["grow", "develop", "evolve", "mature"],
            group="Existence and Change",
        ),
        "change": SubtypeDef(
            prefix="V08",
            description="Transforming",
            examples=["become", "transform", "change", "turn"],
            group="Existence and Change",
        ),
        "directional_movement": SubtypeDef(
            prefix="V12",
            description="Moving with direction",
            examples=["go", "come", "enter", "leave"],
            group="Movement",
        ),
        "manner_movement": SubtypeDef(
            prefix="V13",
            description="Way of moving",
            examples=["walk", "run", "swim", "fly", "crawl"],
            group="Movement",
        ),
        "rule_defined_action": SubtypeDef(
            prefix="V14",
            description="Actions or concessions defined by the rules of a game or procedure",
            examples=["castle", "fold", "call", "forfeit", "resign"],
            comment=(
                "Use for a verb sense whose named action depends on formal rules. "
                "Ordinary physical actions such as kick remain physical_action; "
                "the corresponding moves, outcomes and violations as nouns belong "
                "under rule_defined_event."
            ),
            group="Rule-Defined Actions",
        ),
        "verb_other": SubtypeDef(prefix="V99", member_name="OTHER"),
    },
    "adjective": {
        "size": SubtypeDef(
            prefix="A01",
            description="Size descriptions",
            examples=["big", "small", "huge", "tiny"],
            group="Physical Properties",
        ),
        "color": SubtypeDef(
            prefix="A02",
            description="Color descriptions",
            examples=["red", "blue", "green", "yellow"],
            group="Physical Properties",
        ),
        "shape": SubtypeDef(
            prefix="A03",
            description="Shape descriptions",
            examples=["round", "square", "triangular", "oval"],
            group="Physical Properties",
        ),
        "pattern_texture": SubtypeDef(
            prefix="A04",
            description="Surface patterns and textures",
            examples=["striped", "spotted", "smooth", "rough", "silky", "ribbed"],
            group="Physical Properties",
        ),
        "personal_quality": SubtypeDef(
            prefix="A16",
            description="Character/personality traits",
            examples=["honest", "kind", "brave", "lazy", "clever", "polite"],
            group="Personal and Emotional",
        ),
        "physical_property": SubtypeDef(
            prefix="A18",
            description="Physical properties and states",
            examples=[
                "dimensions",
                "weight",
                "temperature",
                "condition: high",
                "low",
                "heavy",
                "light",
                "cold",
                "hot",
                "wet",
                "dry",
                "open",
                "closed",
            ],
            group="Physical Properties",
        ),
        "condition": SubtypeDef(
            prefix="A17",
            description="Physical/temporal state",
            examples=[
                "hot",
                "cold",
                "wet",
                "dry",
                "clean",
                "dirty",
                "new",
                "old",
                "fresh",
            ],
            group="Personal and Emotional",
        ),
        "emotion": SubtypeDef(
            prefix="A19",
            description="Emotional states",
            examples=["happy", "sad", "angry", "excited", "tired", "scared"],
            group="Personal and Emotional",
        ),
        "quality": SubtypeDef(
            prefix="A05",
            description="Evaluative and abstract properties",
            examples=[
                "good",
                "bad",
                "excellent",
                "important",
                "possible",
                "necessary",
                "real",
                "clear",
                "simple",
            ],
            group="Evaluative",
        ),
        "aesthetic": SubtypeDef(
            prefix="A06",
            description="Beauty or appearance",
            examples=["beautiful", "ugly", "pretty", "handsome"],
            group="Evaluative",
        ),
        "importance": SubtypeDef(
            prefix="A07",
            description="Importance or priority",
            examples=["important", "essential", "trivial", "critical"],
            group="Evaluative",
        ),
        "origin": SubtypeDef(
            prefix="A08",
            description="Origin or source",
            examples=["American", "Chinese", "domestic", "foreign"],
            group="Origin and Material",
        ),
        "location": SubtypeDef(
            prefix="A20",
            description="Where a thing is situated",
            examples=["northern", "coastal", "inland", "urban", "rural"],
            group="Origin and Material",
        ),
        "purpose": SubtypeDef(
            prefix="A09",
            description="Purpose or function",
            examples=["educational", "medical", "industrial", "recreational"],
            group="Origin and Material",
        ),
        "material": SubtypeDef(
            prefix="A10",
            description="Material composition",
            examples=["wooden", "metal", "plastic", "cotton"],
            group="Origin and Material",
        ),
        "indefinite_quantity": SubtypeDef(
            prefix="A12",
            description="Inexact amounts",
            examples=["many", "few", "some", "several"],
            group="Quantity and Time",
        ),
        "duration": SubtypeDef(
            prefix="A13",
            description="Time duration",
            examples=["brief", "long", "eternal", "temporary"],
            group="Quantity and Time",
        ),
        "frequency": SubtypeDef(
            prefix="A14",
            description="Frequency of occurrence",
            examples=["daily", "occasional", "rare", "frequent"],
            group="Quantity and Time",
        ),
        "sequence": SubtypeDef(
            prefix="A15",
            description="Order or sequence",
            examples=["first", "last", "next", "previous"],
            group="Quantity and Time",
        ),
        "spatial_orientation": SubtypeDef(
            prefix="A21",
            description="Anatomical or geometric position and direction",
            examples=[
                "dorsal",
                "ventral",
                "apical",
                "lateral",
                "orthogonal",
                "diagonal",
            ],
            group="Technical and Domain",
        ),
        "chemical_physical": SubtypeDef(
            prefix="A22",
            description="Chemical composition or physical behavior",
            examples=[
                "radioactive",
                "ionic",
                "covalent",
                "alkaline",
                "magnetic",
                "igneous",
            ],
            group="Technical and Domain",
        ),
        "biological_type": SubtypeDef(
            prefix="A23",
            description="Taxonomic or life-process classification",
            examples=[
                "carnivorous",
                "parasitic",
                "perennial",
                "larval",
                "arboreal",
                "venomous",
            ],
            group="Technical and Domain",
        ),
        "belief_cultural": SubtypeDef(
            prefix="A24",
            description="Religious, philosophical or cultural tradition",
            examples=["liturgical", "monastic", "monotheistic", "rabbinic", "mystical"],
            group="Technical and Domain",
        ),
        "temporal_status": SubtypeDef(
            prefix="A25",
            description="Standing in time rather than duration",
            examples=["archaic", "posthumous", "retroactive", "extant", "obsolete"],
            group="Quantity and Time",
        ),
        "mathematical": SubtypeDef(
            prefix="A26",
            description="Mathematical structure or property",
            examples=[
                "quadratic",
                "exponential",
                "commutative",
                "countable",
                "orthogonal",
            ],
            group="Technical and Domain",
        ),
        "legal": SubtypeDef(
            prefix="A27",
            description="Legal standing, right or duty",
            examples=["statutory", "constitutional", "liable", "lawful", "permissible"],
            group="Technical and Domain",
        ),
        "adjective_other": SubtypeDef(prefix="A99", member_name="OTHER"),
    },
    "adverb": {
        "style": SubtypeDef(
            prefix="D01",
            description="Manner or style of action",
            examples=["quickly", "carefully", "well", "slowly", "badly", "easily"],
            group="Manner",
        ),
        "attitude": SubtypeDef(
            prefix="D02",
            description="Attitude or approach",
            examples=["eagerly", "reluctantly", "willingly", "gladly", "sadly"],
            group="Manner",
        ),
        "specific_time": SubtypeDef(
            prefix="D03",
            description="Specific time references",
            examples=["now", "today", "yesterday", "tomorrow", "tonight"],
            group="Temporal",
        ),
        "relative_time": SubtypeDef(
            prefix="D04",
            description="Relative time references",
            examples=["already", "soon", "recently", "lately", "previously"],
            group="Temporal",
        ),
        "duration": SubtypeDef(
            prefix="D05",
            description="Duration of time",
            examples=[
                "briefly",
                "temporarily",
                "permanently",
                "forever",
                "momentarily",
            ],
            group="Temporal",
        ),
        "direction": SubtypeDef(
            prefix="D06",
            description="Directional movement",
            examples=["up", "down", "forward", "backward", "left", "right", "north"],
            group="Spatial",
        ),
        "location": SubtypeDef(
            prefix="D07",
            description="Position or place",
            examples=[
                "here",
                "there",
                "everywhere",
                "nowhere",
                "somewhere",
                "inside",
                "outside",
            ],
            group="Spatial",
        ),
        "distance": SubtypeDef(
            prefix="D08",
            description="Distance references",
            examples=["nearby", "far", "close", "away", "afar"],
            group="Spatial",
        ),
        "intensity": SubtypeDef(
            prefix="D09",
            description="Intensity or degree",
            examples=[
                "very",
                "extremely",
                "slightly",
                "quite",
                "rather",
                "too",
                "enough",
            ],
            group="Degree",
        ),
        "completeness": SubtypeDef(
            prefix="D10",
            description="Degree of completeness",
            examples=[
                "entirely",
                "partly",
                "completely",
                "fully",
                "partially",
                "halfway",
            ],
            group="Degree",
        ),
        "approximation": SubtypeDef(
            prefix="D11",
            description="Approximation",
            examples=[
                "almost",
                "nearly",
                "exactly",
                "approximately",
                "precisely",
                "roughly",
            ],
            group="Degree",
        ),
        "definite_frequency": SubtypeDef(
            prefix="D12",
            description="Specific frequency",
            examples=["daily", "weekly", "monthly", "yearly", "hourly"],
            group="Temporal",
        ),
        "indefinite_frequency": SubtypeDef(
            prefix="D13",
            description="Inexact frequency",
            examples=["often", "sometimes", "rarely", "seldom", "always", "never"],
            group="Temporal",
        ),
        "adverb_other": SubtypeDef(prefix="D99", member_name="OTHER"),
    },
    "conjunction": {
        "conjunction_other": SubtypeDef(prefix="C99"),
    },
    "pronoun": {
        "pronoun_other": SubtypeDef(prefix="P99"),
    },
    "preposition": {
        "preposition_other": SubtypeDef(prefix="R99"),
    },
    "interjection": {
        "interjection_other": SubtypeDef(prefix="I99"),
    },
    "determiner": {
        "determiner_other": SubtypeDef(prefix="T99"),
    },
    "article": {
        "article_other": SubtypeDef(prefix="L99"),
    },
    "numeral": {
        "cardinal": SubtypeDef(
            prefix="Z01",
            description="Cardinal numbers",
            examples=["one", "two", "three", "100"],
            group="Numerals",
        ),
        "ordinal": SubtypeDef(
            prefix="Z02",
            description="Ordinal numbers",
            examples=["first", "second", "third", "100th"],
            group="Numerals",
        ),
    },
}


# ---------------------------------------------------------------------------
# Derived views. None of these is edited by hand.
# ---------------------------------------------------------------------------

#: ``{pos_type: {subtype: prefix}}`` -- the shape this module has always
#: exposed, kept so existing callers need no change.
SUBTYPE_GUID_PREFIXES: Dict[str, Dict[str, str]] = {
    pos_type: {subtype: spec.prefix for subtype, spec in subtypes.items()}
    for pos_type, subtypes in SUBTYPE_DEFS.items()
}

#: ``{prefix: (pos_type, subtype)}`` -- the inverse. A bare GUID prefix says
#: what kind of thing it names, so this answers that without scanning.
#: Prefixes are unique across POS types as well as within them, which the test
#: suite enforces.
PREFIX_TO_SUBTYPE: Dict[str, tuple[str, str]] = {
    spec.prefix: (pos_type, subtype)
    for pos_type, subtypes in SUBTYPE_DEFS.items()
    for subtype, spec in subtypes.items()
}


def get_subtype_def(pos_type: str, subtype: str) -> Optional[SubtypeDef]:
    """The definition for one subtype, or None if the pair is unknown."""
    return SUBTYPE_DEFS.get(pos_type, {}).get(subtype)


def subtype_for_prefix(prefix: str) -> Optional[tuple[str, str]]:
    """The ``(pos_type, subtype)`` a GUID prefix belongs to, or None."""
    return PREFIX_TO_SUBTYPE.get(prefix)


def classifiable_subtypes(pos_type: str) -> List[str]:
    """Subtypes a classifier may choose for ``pos_type``, deprecated ones excluded.

    Use this anywhere a list of choices is offered to a model or a person, so a
    deprecated subtype is retired in one place rather than in each prompt.
    ``SUBTYPE_DEFS`` itself still holds it: a GUID already issued under a
    retired subtype has to keep resolving.
    """
    return [
        subtype for subtype, spec in SUBTYPE_DEFS.get(pos_type, {}).items() if not spec.deprecated
    ]


def subtype_groups(pos_type: str) -> Dict[str, List[str]]:
    """One POS type's live subtypes, bucketed by ``group`` for display.

    Subtypes are ordered by GUID prefix within each group, and the groups by
    their lowest prefix. Nothing depends on a hand-chosen order, and since a
    prefix is only ever issued above the current maximum, a newly added subtype
    sorts to the end of its group rather than into the middle of a list.

    Deprecated subtypes are omitted: the page offers these as live categories to
    browse, so it wants the same filter ``classifiable_subtypes`` applies.

    Returns the catch-all under the bare enum name ("other"), matching how
    callers key it, not the ``<pos>_other`` key used in the table.
    """
    buckets: Dict[str, List[tuple[str, str]]] = {}
    for subtype, spec in SUBTYPE_DEFS.get(pos_type, {}).items():
        if spec.deprecated:
            continue
        name = "other" if subtype == f"{pos_type}_other" else subtype
        buckets.setdefault(spec.group, []).append((spec.prefix, name))
    ordered = sorted(buckets.items(), key=lambda kv: min(prefix for prefix, _ in kv[1]))
    return {group: [name for _, name in sorted(entries)] for group, entries in ordered}


# GUID prefixes for phrase subtypes. Phrases (fixed traveler/greeting
# expressions, e.g. "Where is the toilet?") live in their own ``phrases`` table
# rather than ``lemmas``, so they are not part of SUBTYPE_GUID_PREFIXES above.
PHRASE_SUBTYPE_GUID_PREFIXES = {
    "greetings": "F01",
    "traveler": "F02",
}

# GUID prefix for idioms. Idioms (figurative expressions whose meaning is not
# compositional, e.g. "kick the bucket") live in their own ``idioms`` table, so
# like phrases they are not part of SUBTYPE_GUID_PREFIXES above. Idioms are not
# subtyped, so this is a single prefix rather than a mapping.
IDIOM_GUID_PREFIX = "M01"

# GUID prefixes for name kinds. Names ("George", "Fresh Mart") live in their own
# ``names`` table and are exported to ``data/release/names`` because their
# per-language renderings - Džordžas, 乔治, ジョージ - have to stay stable across
# every text that uses them. The kind is encoded in the prefix, mirroring how a
# lemma's subtype is, so a bare GUID says what it names. Keys are
# ``storage.models.name_entity.NAME_KINDS`` entries; the "E" family (entity) is
# reserved for names.
NAME_KIND_GUID_PREFIXES = {
    "given_name": "E01",
    "family_name": "E02",
    "full_name": "E03",
    "place": "E04",
    "organization": "E05",
    "brand": "E06",
    "animal": "E07",
    "other": "E99",
}

# GUID prefix for sentences. Sentences are not subtyped and are numbered in one
# flat sequence across the whole corpus (``S_00077``), so like idioms this is a
# single prefix rather than a mapping. The sequence is five digits wide, not the
# three used by lemmas, because there are far more sentences than words.
SENTENCE_GUID_PREFIX = "S"


def render_subtype_list(pos_type: str, include_catch_all: bool = True) -> str:
    """Render one POS type's subtypes as the bullet list a prompt shows an LLM.

    ``include_catch_all=False`` leaves out the ``<pos>_other`` line, for a
    caller (add_sense) whose schema does not offer the catch-all.

    The classification schema's enum already comes from this table
    (``get_subtype_values_for_pos``). Rendering the prompt's descriptions from
    it too is what keeps the two in agreement: before this, the prompt was a
    hand-maintained file that had drifted badly -- it offered a dozen subtypes
    with no GUID prefix at all, while never mentioning thirty-odd real ones, so
    the model was asked to choose from one vocabulary and validated against
    another.

    ``comment`` is deliberately not rendered. It is the maintainer's note about
    why a subtype exists, which is not classification guidance and would only
    mislead a model reading it as such.

    A subtype with no description yet is still listed by name: it is a valid
    choice and omitting it would recreate the drift this function exists to
    prevent.
    """
    lines = []
    for subtype, spec in SUBTYPE_DEFS[pos_type].items():
        # A deprecated subtype keeps its prefix and enum member but is not a
        # choice any more, so offering it would invite new words into it.
        if spec.deprecated:
            continue
        if not include_catch_all and subtype == f"{pos_type}_other":
            continue
        # The prompt offers the catch-all under the bare name the enum uses.
        name = "other" if subtype == f"{pos_type}_other" else subtype
        text = spec.description
        if spec.examples:
            examples = ", ".join(spec.examples)
            text = f"{text} ({examples})" if text else f"e.g. {examples}"
        # No description written yet: render the bare name rather than filler.
        # The identifier itself ("body_part", "disease_condition") carries more
        # signal than a placeholder gloss would, and a blank entry makes the
        # gap visible to whoever fills these in.
        if not text:
            text = name.replace("_", " ")
        if name == "other":
            text = f"Any {pos_type} that doesn't fit the above categories"
        lines.append(f"- {name}: {text}")
    return "\n".join(lines)
