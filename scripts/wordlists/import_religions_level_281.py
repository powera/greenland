#!/usr/bin/env python3
"""Import the names of the world religions and their followers at 281.

Started from "Christian" and "Islamic" in the top unlinked tokens (2026-10-28).
None of the major religions or their followers was in the database: "religion"
itself sits at 299 and the tradition-specific vocabulary -- dharma, hadith,
rabbi, liturgy, halal -- at 1060.  281 is a new level beside Ideas, Rights and
Beliefs (280) and holds only the names, a closed set comparable to the
nationalities at 232.  Its row does not exist yet: name it on the Barsukas
Levels page.  Practice words -- prayer, priest, monk, heaven, the scriptures --
stay out of it; the scriptures may become a 282 list of their own.

Each follower word is split the way the nationalities are, into the person
("he is a Christian", subtype human) and the attribute ("Christian imagery",
belief_cultural).  Words that are only one of the two carry no label: "Jew" is
only the person, "Jewish" and "Islamic" only the attribute.  The religions are
pinned to social_institution, beside "religion" and "denomination".

Taoism, Confucianism and Shinto are here rather than at 1060 for the zh and ja
learners.  Seven Christian denominations follow the same person/attribute split,
except that "Orthodox" is the attribute only ("an Orthodox" for the person is
rare).  It is a new sense, since the existing "orthodox" (A24_050, 1060) is the
generic conforming-to-standards one.  Pentecostal is left out as finer than
this level needs.

The headwords are spelled with the capital they always take: add_sense stores
the text as given and matches existing senses case-insensitively, so
"Orthodox" and "Catholic" are compared against the lowercase generic senses
and stored capitalized.  "evangelical" is the exception, lowercase as A24_059
already is.

Only "evangelical" moves: A24_059 at 1060 already is the denominational sense.
Otherwise "religion" stays at 299, "god" at 310, and the 1060 vocabulary where
it is.

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

LEVEL = 281
DOMAIN = "religion"
TAGS = ("religion",)

RELIGIONS = SenseList(
    level=LEVEL,
    domain=DOMAIN,
    label="religion",
    tags=TAGS,
    pos_subtype="social_institution",
    entries=(
        S("Christianity", "the religion based on the life and teachings of Jesus", unique=True),
        S("Islam", "the religion based on the teachings of the prophet Muhammad", unique=True),
        S("Judaism", "the religion of the Jewish people, based on the Torah", unique=True),
        S("Hinduism", "the main religion of India, with many gods and traditions", unique=True),
        S("Buddhism", "the religion based on the teachings of the Buddha", unique=True),
        S("Sikhism", "the religion founded in the Punjab by Guru Nanak", unique=True),
        S("Catholicism", "the faith and practice of the Roman Catholic Church", unique=True),
        S("Protestantism", "the forms of Christianity that separated from Rome", unique=True),
        S(
            "Taoism",
            "the Chinese religion and philosophy based on the teachings of Laozi",
            unique=True,
        ),
        S(
            "Confucianism",
            "the Chinese system of ethics and belief based on Confucius",
            unique=True,
        ),
        S(
            "Shinto",
            "the native religion of Japan, centred on worship of kami",
            unique=True,
            pos="noun",
        ),
    ),
)

FOLLOWERS = SenseList(
    level=LEVEL,
    domain=DOMAIN,
    label="person",
    tags=TAGS,
    pos_subtype="human",
    entries=(
        S("Christian", "a person who follows Christianity", pos="noun"),
        S("Muslim", "a person who follows Islam", pos="noun"),
        S("Jew", "a person who is Jewish by religion or descent", unique=True, pos="noun"),
        S("Hindu", "a person who follows Hinduism", pos="noun"),
        S("Buddhist", "a person who follows Buddhism", pos="noun"),
        S("Sikh", "a person who follows Sikhism", pos="noun"),
        S("Catholic", "a member of the Roman Catholic Church", pos="noun"),
        S("Protestant", "a member of a Protestant church", pos="noun"),
        S("Taoist", "a person who follows Taoism", pos="noun"),
        S("Confucian", "a person who follows Confucianism", pos="noun"),
        # Christian denominations
        S("Lutheran", "a member of a Lutheran church", pos="noun"),
        S("Anglican", "a member of the Church of England or a related church", pos="noun"),
        S("Baptist", "a member of a Baptist church", pos="noun"),
        S("Mormon", "a member of the Church of Jesus Christ of Latter-day Saints", pos="noun"),
        S("Methodist", "a member of a Methodist church", pos="noun"),
        S("Evangelical", "a member of an evangelical Protestant church", pos="noun"),
    ),
)

ATTRIBUTES = SenseList(
    level=LEVEL,
    domain=DOMAIN,
    label="religious",
    tags=TAGS,
    pos_subtype="belief_cultural",
    entries=(
        S("Christian", "of or relating to Christianity", pos="adjective"),
        S("Muslim", "of or relating to Muslims or Islam", pos="adjective"),
        S("Islamic", "of or relating to Islam", unique=True, pos="adjective"),
        S("Jewish", "of or relating to Jews or Judaism", unique=True, pos="adjective"),
        S("Hindu", "of or relating to Hinduism", pos="adjective"),
        S("Buddhist", "of or relating to Buddhism", pos="adjective"),
        S("Sikh", "of or relating to Sikhism", pos="adjective"),
        S("Catholic", "of or relating to the Roman Catholic Church", pos="adjective"),
        S("Protestant", "of or relating to Protestantism", pos="adjective"),
        S("Taoist", "of or relating to Taoism", pos="adjective"),
        S("Confucian", "of or relating to Confucius or Confucianism", pos="adjective"),
        S("Shinto", "of or relating to Shinto", pos="adjective"),
        # Christian denominations
        S(
            "Orthodox",
            "of or relating to the Eastern Orthodox Church",
            disambiguation="Christian denomination",
            pos="adjective",
        ),
        S("Lutheran", "of or relating to the Lutheran church", pos="adjective"),
        S("Anglican", "of or relating to the Church of England", pos="adjective"),
        S("Baptist", "of or relating to the Baptist church", pos="adjective"),
        S("Mormon", "of or relating to the Latter-day Saint movement", pos="adjective"),
        S("Methodist", "of or relating to the Methodist church", pos="adjective"),
        S(
            "evangelical",
            "of or relating to evangelical Protestant churches",
            move=True,
            pos="adjective",
        ),
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_sense_import((RELIGIONS, FOLLOWERS, ATTRIBUTES), __doc__ or ""))
