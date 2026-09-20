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
            description="Professions and roles",
            examples=["teacher", "doctor", "accountant"],
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
            examples=["house", "hospital", "bridge", "library", "port"],
            group="Physical Objects and Structures",
        ),
        "building_part": SubtypeDef(
            prefix="N47",
            description="Parts of buildings",
            examples=["door", "window", "wall", "floor", "ceiling", "roof", "stairs"],
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
            description="Portable everyday objects",
            examples=["cup", "key", "book", "bottle", "wallet"],
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
            description="Made works and cultural artifacts",
            examples=["statue", "photograph", "mural", "comic book", "crossword puzzle"],
            group="Physical Objects and Structures",
        ),
        "legal_document": SubtypeDef(
            prefix="N58",
            description="Documents with legal force",
            examples=["will", "deed", "passport", "subpoena"],
            group="Abstract Concepts and Ideas",
        ),
        "natural_feature": SubtypeDef(
            prefix="N11",
            description="Natural formations and phenomena",
            examples=["river", "island", "cloud", "beach", "star"],
            group="Physical Objects and Structures",
        ),
        "tool": SubtypeDef(
            prefix="N12",
            description="Hand tools and generic tools",
            examples=["hammer", "saw", "wrench", "screwdriver"],
            group="Physical Objects and Structures",
        ),
        "electronic_device": SubtypeDef(
            prefix="N57",
            description="Computers, phones, TVs, radios, cameras",
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
            description="Fields of study and bodies of knowledge",
            examples=["biology", "history", "philosophy", "mathematics", "machine learning"],
            group="Abstract Concepts and Ideas",
        ),
        "quantitative_concept": SubtypeDef(
            prefix="N22",
            description="Amounts, measures and magnitudes as concepts",
            examples=["number", "distance", "size", "level", "half"],
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
            description="Generic place nouns",
            examples=["room", "street", "etc."],
            group="Named Entities",
        ),
        "region": SubtypeDef(
            prefix="N45",
            description="Countries, states, and similar political regions",
            group="Named Entities",
        ),
        "city": SubtypeDef(
            prefix="N46",
            description="Cities",
            examples=["Vilnius", "Paris", "Tokyo"],
            group="Named Entities",
        ),
        "geographic_place": SubtypeDef(
            prefix="N56",
            description="Named geographic features",
            examples=["Atlantic Ocean", "Pacific Ocean", "Indian Ocean"],
            group="Named Entities",
        ),
        "organization_name": SubtypeDef(
            prefix="N31",
            description="Named organizations and companies",
            examples=["Coca-Cola", "agency", "small business"],
            group="Named Entities",
        ),
        "temporal_name": SubtypeDef(
            prefix="N32",
            description="Days of week, months, etc.",
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
        "texture": SubtypeDef(
            prefix="A04",
            description="Texture descriptions",
            examples=["soft", "hard", "smooth", "rough"],
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


def render_subtype_list(pos_type: str) -> str:
    """Render one POS type's subtypes as the bullet list a prompt shows an LLM.

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
