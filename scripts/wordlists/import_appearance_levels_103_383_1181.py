#!/usr/bin/env python3
"""Import words for describing how people look: 103 (B1), 383 (B2) and 1181 (C1).

Describing People (16) is all character -- kind, shy, lazy -- and nothing
gathered the words for appearance.  A survey on 2026-11-19 found the common
ones missing (brunette, redhead, freckles, skinny, tattoo) and the ones that
did exist scattered: blond at Size and Patterns (101), bald for a head
with no hair at 1310, handsome for a good-looking person at 320 while its
"generous amount" sense sat at 101.

* 103 sits beside Size and Patterns (101) and Describing and Qualifying
  Words (106): hair colour and style, build, and the face and skin words a
  learner needs to describe someone.
* 383 is the same field one step up: finer distinctions of build (stocky,
  lanky, petite), facial hair, and colour words for hair and eyes (auburn,
  hazel).
* 1181 is the topic-band list beside Advanced Description, Appearance and
  Degree (1180): the literary vocabulary of novels and character sketches
  (gaunt, sallow, wizened, disheveled), and the face and posture words that
  were mixed into 1180's two hundred.

Every word goes through the add-sense path with domain "physical appearance";
the subtype is left to the model, since the lists mix nouns and adjectives,
and each entry fixes its part of speech.  Headwords that already mean
something else -- "fair" the just, "build" the verb, "glasses" for drinking,
"hazel" the tree -- carry a label.

The moves are senses the database already has with the right meaning, which
change level only.  GUIDs are from the database on 2026-11-19, and each is
checked against its headword before it moves.

"blonde" is not a lemma of its own: an ``--execute`` run records it as an
English spelling variant of both blond senses, the adjective (blonde, blonder,
blondest) and the person (blonde, blondes), stored as grey is for gray.  The
same run then names each level that has words and no name yet, writing
``curriculum_levels`` directly: Barsukas has no API for either step.  A level
somebody already named keeps its name.

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

from sqlalchemy.orm import Session

from scripts.wordlists.wordlist_import_helper import LevelMove
from scripts.wordlists.wordlist_import_helper import SenseEntry as S
from scripts.wordlists.wordlist_import_helper import SenseList, run_sense_import
from storage.backend import create_session
from storage.backend.config import DataSourceConfig
from storage.crud.curriculum_level import get_curriculum_level, set_curriculum_level
from storage.crud.variant_form import add_variant_form
from storage.models.schema import Lemma
from storage.models.variant_form import VARIANT_KIND_SPELLING

DOMAIN = "physical appearance"
TAGS = ("appearance",)
SOURCE = "scripts/import_appearance_levels"


class LevelName(NamedTuple):
    name: str
    cefr: str


LEVEL_NAMES: Mapping[int, LevelName] = {
    103: LevelName("Describing Appearance", "B1"),
    383: LevelName("Describing Appearance 2", "B2"),
    1181: LevelName("Advanced Physical Appearance", "C1"),
}


class SpellingVariant(NamedTuple):
    """One form of a spelling variant, attached to an existing lemma by GUID."""

    guid: str
    headword: str
    form_text: str
    grammatical_form: str
    is_base_form: bool


# blonde is the variant's own base form, so it is the variant_key of every row.
BLONDE_KEY = "blonde"
BLONDE_FORMS = (
    SpellingVariant("A18_146", "blond", "blonde", "adjective/en_positive", True),
    SpellingVariant("A18_146", "blond", "blonder", "adjective/en_comparative", False),
    SpellingVariant("A18_146", "blond", "blondest", "adjective/en_superlative", False),
    SpellingVariant("N01_230", "blond", "blonde", "noun/en_singular", True),
    SpellingVariant("N01_230", "blond", "blondes", "noun/en_plural", False),
)


def U(term: str, hint: str, pos: str) -> S:
    """A headword with no other meaning in English, stored without a label."""
    return S(term, hint, unique=True, pos=pos)


APPEARANCE = SenseList(
    level=103,
    domain=DOMAIN,
    label="appearance",
    tags=TAGS,
    entries=(
        # Hair
        U("brunette", "a woman or girl with dark brown hair", "noun"),
        U("redhead", "a person with red hair", "noun"),
        U("wavy", "of hair, curving gently rather than straight or curly", "adjective"),
        U("dark-haired", "having dark hair", "adjective"),
        U("fair-haired", "having light-coloured, blond hair", "adjective"),
        U("gray-haired", "having gray or white hair", "adjective"),
        S(
            "fair",
            "of hair or skin, light in colour",
            disambiguation="light in colour",
            pos="adjective",
        ),
        U("ponytail", "hair tied at the back of the head so it hangs down", "noun"),
        S("braid", "hair divided into strands and woven together", pos="noun"),
        U("bangs", "hair cut straight across the forehead", "noun"),
        # Build
        U("overweight", "heavier than is healthy or usual", "adjective"),
        U("skinny", "very thin", "adjective"),
        # Face and skin
        U("freckle", "a small light-brown spot on the skin", "noun"),
        S(
            "glasses",
            "a pair of lenses in a frame worn to help a person see",
            disambiguation="spectacles",
            pos="noun",
        ),
        S("tattoo", "a picture or design marked permanently on the skin", pos="noun"),
        S("scar", "a mark left on the skin after a wound has healed", pos="noun"),
        # General
        U("eyelash", "one of the short hairs growing on the edge of the eyelid", "noun"),
        U("haircut", "the style in which someone's hair has been cut", "noun"),
        U("hairstyle", "the way in which someone's hair is arranged", "noun"),
        # General
        U("cute", "attractive in a sweet or charming way", "adjective"),
        U("teenage", "aged between thirteen and nineteen", "adjective"),
        S("looks", "a person's appearance, especially how attractive they are", pos="noun"),
        S(
            "figure",
            "the shape of a person's body, especially a woman's",
            disambiguation="body shape",
            pos="noun",
        ),
        S("fit", "healthy and strong, especially from exercise", pos="adjective"),
    ),
)

APPEARANCE_2 = SenseList(
    level=383,
    domain=DOMAIN,
    label="appearance",
    tags=TAGS,
    entries=(
        # Hair
        U("auburn", "of hair, reddish-brown", "adjective"),
        U("balding", "starting to lose the hair on the head", "adjective"),
        S("hairline", "the edge of the hair along the forehead", pos="noun"),
        S("pigtail", "a length of hair tied or braided at each side of the head", pos="noun"),
        U("dreadlocks", "hair twisted into long, thick, ropelike strands", "noun"),
        U("wig", "a covering of false hair worn on the head", "noun"),
        U("sideburns", "hair grown down the sides of a man's face in front of the ears", "noun"),
        S("stubble", "short hairs growing on a man's face after he has not shaved", pos="noun"),
        U("clean-shaven", "having no beard or moustache", "adjective"),
        S("bushy", "of hair or eyebrows, thick and growing densely", pos="adjective"),
        # Eyes, face and skin
        S("hazel", "of eyes, greenish-brown", disambiguation="eye colour", pos="adjective"),
        U("dimple", "a small hollow in the cheek or chin, seen especially when smiling", "noun"),
        S("wrinkle", "a line or fold in the skin, especially from age", pos="noun"),
        U("freckled", "covered in freckles", "adjective"),
        U("birthmark", "a coloured mark on the skin that a person is born with", "noun"),
        U("tanned", "having skin made brown by the sun", "adjective"),
        # Build
        S("build", "the size and shape of a person's body", disambiguation="physique", pos="noun"),
        U("chubby", "slightly fat, in a rounded and pleasant way", "adjective"),
        U("stocky", "short and solidly built", "adjective"),
        U("petite", "of a woman, small and slim", "adjective"),
        U("lanky", "tall and thin in an awkward way", "adjective"),
        U("curvy", "of a woman, having a shapely, rounded figure", "adjective"),
        U("well-built", "having a strong, muscular body", "adjective"),
        U("obese", "very fat, in a way that is unhealthy", "adjective"),
        U("broad-shouldered", "having wide shoulders", "adjective"),
        U("physique", "the form, size and strength of a person's body", "noun"),
        U("burly", "large, strong and heavy", "adjective"),
        U("heavyset", "having a large, solid, heavy body", "adjective"),
        U("scrawny", "unattractively thin and bony", "adjective"),
        U("hunched", "with the back and shoulders bent forward", "adjective"),
        U("double chin", "a fold of fat under the chin", "noun"),
        U("potbelly", "a large, round stomach that sticks out", "noun"),
        # More hair
        U("frizzy", "of hair, in tight, wiry curls", "adjective"),
        S("spiky", "of hair, standing up in stiff points", pos="adjective"),
        U("shoulder-length", "of hair, reaching down to the shoulders", "adjective"),
        S("bun", "hair twisted into a round knot at the back of the head", pos="noun"),
        S("bob", "a short haircut of equal length all round", disambiguation="haircut"),
        U("perm", "a treatment that gives hair long-lasting curls", "noun"),
        U("afro", "hair worn in a thick, rounded mass of tight curls", "noun"),
        U("goatee", "a small pointed beard on the chin", "noun"),
        S("dyed", "of hair, coloured artificially", pos="adjective"),
        # More face, eyes and skin
        U("cheekbone", "the bone below the eye that shapes the cheek", "noun"),
        U("pimple", "a small, red, swollen spot on the skin", "noun"),
        U("blue-eyed", "having blue eyes", "adjective"),
        U("fair-skinned", "having pale skin", "adjective"),
        U("dark-skinned", "having dark skin", "adjective"),
        U("olive-skinned", "having skin with a light brownish tone", "adjective"),
        U("short-sighted", "able to see near things clearly but not distant ones", "adjective"),
        # Overall impression
        S(
            "plain",
            "of a person, not beautiful or attractive",
            disambiguation="unattractive",
            pos="adjective",
        ),
        U("stunning", "extremely attractive or impressive", "adjective"),
        U("glamorous", "attractive in an exciting, stylish way", "adjective"),
        U("scruffy", "untidy and dirty in appearance", "adjective"),
        U("well-dressed", "wearing attractive, good-quality clothes", "adjective"),
        U("well-groomed", "having a neat, clean, carefully cared-for appearance", "adjective"),
    ),
)

ADVANCED_APPEARANCE = SenseList(
    level=1181,
    domain=DOMAIN,
    label="appearance",
    tags=TAGS,
    entries=(
        # Build
        U("gaunt", "very thin and bony, especially from illness or hunger", "adjective"),
        U("emaciated", "abnormally thin and weak from hunger or illness", "adjective"),
        S("wiry", "thin but strong and tough", pos="adjective"),
        S("sinewy", "lean and muscular", pos="adjective"),
        U("brawny", "physically strong and muscular", "adjective"),
        U("strapping", "big, strong and healthy", "adjective"),
        U("corpulent", "fat", "adjective"),
        U("rotund", "plump and round", "adjective"),
        S("portly", "of a man, rather fat", pos="adjective"),
        U("svelte", "slender and elegant", "adjective"),
        U("willowy", "tall, slim and graceful", "adjective"),
        U("lithe", "slim, supple and graceful", "adjective"),
        U("statuesque", "tall and dignified, like a statue", "adjective"),
        U("gangly", "tall, thin and awkward in movement", "adjective"),
        U("gawky", "awkward and clumsy, especially from being tall and young", "adjective"),
        U("bow-legged", "having legs that curve outward at the knees", "adjective"),
        U("knock-kneed", "having legs that curve inward so the knees touch", "adjective"),
        # Face and skin
        U("pallid", "pale, especially from poor health", "adjective"),
        U("sallow", "of skin, an unhealthy yellowish colour", "adjective"),
        U("swarthy", "of skin, dark", "adjective"),
        S("florid", "of a face, red and flushed", pos="adjective"),
        U("haggard", "looking tired and unwell, especially from worry", "adjective"),
        U("careworn", "looking tired and worried from years of trouble", "adjective"),
        U("wizened", "shrivelled and wrinkled with age", "adjective"),
        U("pockmarked", "of skin, covered in small hollow scars", "adjective"),
        U("aquiline", "of a nose, curved like an eagle's beak", "adjective"),
        U("snub-nosed", "having a short, turned-up nose", "adjective"),
        U("buck-toothed", "having upper front teeth that stick out", "adjective"),
        U("jowls", "the loose, sagging flesh of the lower cheeks", "noun"),
        U("crow's feet", "fine wrinkles at the outer corners of the eyes", "noun"),
        U("doe-eyed", "having large, gentle, innocent-looking eyes", "adjective"),
        U("bleary-eyed", "having eyes that are tired and unfocused", "adjective"),
        U("chiseled", "of a face, having strong, clear-cut features", "adjective"),
        U("bespectacled", "wearing glasses", "adjective"),
        # Hair
        U("hirsute", "hairy", "adjective"),
        U("grizzled", "having gray or partly gray hair", "adjective"),
        S("hoary", "gray or white with age", pos="adjective"),
        U("tousled", "of hair, untidy as if ruffled", "adjective"),
        S("mousy", "of hair, a dull light brown", pos="adjective"),
        U("jet-black", "of hair, deep shiny black", "adjective"),
        U("strawberry blonde", "of hair, light reddish-blond", "adjective"),
        U("coiffure", "a person's hairstyle, especially an elaborate one", "noun"),
        U("comb-over", "long hair combed across a bald patch", "noun"),
        U("widow's peak", "a V-shaped point of hair on the forehead", "noun"),
        U("crew cut", "a very short haircut for men", "noun"),
        U("mohawk", "a hairstyle with a central strip of hair and shaved sides", "noun"),
        U("cornrows", "hair braided in tight rows close to the scalp", "noun"),
        # Overall impression
        U("unkempt", "untidy and not cared for", "adjective"),
        U("disheveled", "of hair or clothes, very untidy", "adjective"),
        U("bedraggled", "wet, dirty and untidy", "adjective"),
        U("dapper", "of a man, neat and stylishly dressed", "adjective"),
        U("dowdy", "unfashionable and dull in appearance", "adjective"),
        U("frumpy", "dowdy and unattractive in dress", "adjective"),
        U("comely", "pleasant to look at; attractive", "adjective"),
        S("homely", "of a person, not attractive", disambiguation="unattractive", pos="adjective"),
        U("clean-cut", "neat and tidy in appearance, in a wholesome way", "adjective"),
    ),
)

MOVES = (
    # To 103: the everyday senses of these were filed late or with clothing.
    LevelMove("A18_146", "blond", 103),
    LevelMove("N01_230", "blond", 103),
    LevelMove("A18_241", "bald", 103),
    LevelMove("A04_003", "curly", 103),
    LevelMove("A06_076", "handsome", 103),
    LevelMove("A06_097", "attractive", 103),
    LevelMove("A06_034", "good-looking", 103),
    LevelMove("A06_038", "ugly", 103),
    LevelMove("A18_094", "muscular", 103),
    LevelMove("N03_164", "moustache", 103),
    LevelMove("A18_211", "bearded", 103),
    LevelMove("N03_169", "curl", 103),
    LevelMove("A13_022", "middle-aged", 103),
    LevelMove("N19_022", "appearance", 103),
    # To 383: description of build, skin and age, from 1180, 1300 and 1305.
    LevelMove("A01_030", "slender", 383),
    LevelMove("A01_034", "plump", 383),
    LevelMove("A01_028", "stout", 383),
    LevelMove("A18_186", "frail", 383),
    LevelMove("A02_024", "ginger", 383),
    LevelMove("N19_155", "complexion", 383),
    LevelMove("A04_028", "wrinkled", 383),
    LevelMove("N19_121", "tan", 383),
    LevelMove("A06_105", "youthful", 383),
    LevelMove("A06_054", "elegant", 383),
    LevelMove("A06_072", "radiant", 383),
    LevelMove("A06_100", "striking", 383),
    LevelMove("A18_218", "sturdy", 383),
    # To 1181: the literary descriptions of face and posture in 1180, 1310 and 1311.
    LevelMove("A02_049", "wan", 1181),
    LevelMove("A29_025", "rosy", 1181),
    LevelMove("A02_031", "flushed", 1181),
    LevelMove("A18_192", "stooped", 1181),
    LevelMove("A06_059", "rugged", 1181),
)


def print_extra_plan() -> None:
    print("Level names (set after an --execute run, where unnamed and holding words):")
    for level, level_name in LEVEL_NAMES.items():
        print(f"  {level}: {level_name.name} ({level_name.cefr})")
    print(f"Spelling variant {BLONDE_KEY!r} (added after an --execute run):")
    for form in BLONDE_FORMS:
        print(f"  {form.guid} {form.headword}: {form.form_text} [{form.grammatical_form}]")
    print()


def add_blonde_variant(session: Session) -> None:
    """Record blonde as a spelling variant of each blond sense; safe to rerun."""
    for form in BLONDE_FORMS:
        lemma = session.query(Lemma).filter(Lemma.guid == form.guid).one_or_none()
        if lemma is None or lemma.lemma_text != form.headword:
            found = lemma.lemma_text if lemma is not None else "missing"
            raise RuntimeError(f"{form.guid} is {found!r}, not {form.headword!r}")
        add_variant_form(
            session,
            lemma,
            form.form_text,
            "en",
            BLONDE_KEY,
            form.grammatical_form,
            variant_kind=VARIANT_KIND_SPELLING,
            is_base_form=form.is_base_form,
            source=SOURCE,
        )
        print(f"  {form.guid} {form.headword}: {form.form_text} [{form.grammatical_form}]")


def name_levels(session: Session) -> None:
    """Name each level that has words and no name; a name already given is kept."""
    for level, level_name in LEVEL_NAMES.items():
        existing = get_curriculum_level(session, level)
        if existing is not None and (existing.name or "").strip():
            print(f"  {level}: keeps its name {existing.name!r}")
            continue
        word_count = session.query(Lemma).filter(Lemma.difficulty_level == level).count()
        if not word_count:
            print(f"  {level}: no words, left unnamed")
            continue
        set_curriculum_level(session, level, level_name.name, cefr=level_name.cefr, source=SOURCE)
        print(f"  {level}: named {level_name.name!r}")


def finish(config: DataSourceConfig) -> None:
    """The two direct database steps, committed together."""
    session = create_session(config)
    try:
        print("Adding the blonde spelling variant:")
        add_blonde_variant(session)
        print("Naming levels:")
        name_levels(session)
        session.commit()
    finally:
        session.close()


def main() -> int:
    print_extra_plan()
    status = run_sense_import(
        (APPEARANCE, APPEARANCE_2, ADVANCED_APPEARANCE), __doc__ or "", moves=MOVES
    )
    if "--execute" in sys.argv[1:]:
        finish(DataSourceConfig())
    return status


if __name__ == "__main__":
    raise SystemExit(main())
