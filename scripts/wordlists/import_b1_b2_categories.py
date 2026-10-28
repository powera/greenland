#!/usr/bin/env python3
"""Preview the reviewed B1/B2 category additions; execution requires approval.

Uses the established Barsukas add_sense pipeline for sense matching, subtype
selection, translations, English seed forms and persistence. No translations
are guessed here. Without --execute this script only prints its curated plan:
it makes no HTTP requests and never opens or changes the local database.

With --execute, the existing helper makes live paid API calls and persists the
results through Barsukas. Do not run that flag without explicit approval. The
caller must arrange the normal server-side database backup before a live run.
--limit applies separately to each POS list, not to the whole run.

The eight category titles below are proposed metadata, not writes. This script
does not create/name levels. It lists exact existing-GUID moves separately, leaves
already placed prerequisite senses untouched and does not approve pending
relationship senses #10-13. The add_sense matcher preserves matched placement
(move=False); only the explicit EXISTING_MOVES list changes existing levels.
Re-review these GUIDs before a live run if placements have changed meanwhile.
Same-headword matching is not cross-headword synonym deduplication.

Numbers identify categories, not teaching order. Health uses the available
134 slot beside Health and Body (133), replacing the earlier proposed 451.

  GREENLAND_TEST_MODE=1 PYTHONPATH=src python scripts/wordlists/import_b1_b2_categories.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for import_path in (ROOT, ROOT / "src"):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from scripts.wordlists.wordlist_import_helper import (
    LevelMove,
    SenseEntry,
    SenseList,
    run_sense_import,
)

# Names supplied for review/metadata preparation only; the API import does not
# write curriculum_levels. Each POS list carries its own sense-specific tag.
LEVEL_NAMES: dict[int, str] = {
    134: "Health, Symptoms and Treatment",
    151: "Judgment and Communication Verbs",
    176: "Money, Payments and Agreements",
    216: "Scheduling and Service Terms",
    227: "Linking, Time and Degree Adverbs",
    296: "Employment Terms",
    312: "Social Relationships and Reactions",
    341: "Digital Information and Access",
}

# (level, POS, ((headword, intended sense), ...)). Fixed POS prevents, for
# example, payment bill from matching the existing performer-listing verb.
# Sense hints distinguish medical treatment from material processing, online
# account from bank account, and job resignation/promotion from game senses.
CATEGORY_SENSES: tuple[tuple[int, str, tuple[tuple[str, str], ...]], ...] = (
    (
        134,
        "noun",
        (
            ("symptom", "a bodily sign or experience indicating illness"),
            ("treatment", "care intended to improve a person's health"),
            ("recovery", "return to health after illness or injury"),
            ("side effect", "an unintended secondary effect of medicine"),
            ("patient", "a person receiving medical care"),
            ("checkup", "a routine medical examination"),
            ("bruise", "a discolored area caused by bleeding under the skin"),
            ("swelling", "an abnormal enlargement of a body part"),
            ("rash", "an area of irritated or inflamed skin"),
            ("nausea", "the feeling that one may vomit"),
            ("appetite", "the desire to eat"),
            ("vaccination", "administration of a vaccine to protect against disease"),
            ("emergency", "a serious unexpected situation needing immediate action"),
        ),
    ),
    (
        134,
        "verb",
        (
            ("recover", "to return to health after illness or injury"),
            ("diagnose", "to identify an illness from its signs and evidence"),
            ("heal", "to become healthy again after injury"),
            ("bleed", "to lose blood from the body"),
            ("faint", "to briefly lose consciousness"),
            ("vomit", "to expel stomach contents through the mouth"),
            ("prescribe", "to authorize a medicine or treatment for a patient"),
        ),
    ),
    (
        134,
        "adjective",
        (
            ("dizzy", "feeling unsteady or as though surroundings are spinning"),
            ("painful", "causing physical pain"),
            ("swollen", "enlarged because of injury or illness"),
            ("contagious", "able to spread an illness from person to person"),
            ("chronic", "persisting for a long time, especially of illness"),
            ("acute", "severe and developing suddenly, especially of illness"),
            ("mild", "not severe or intense, especially of illness"),
            ("unconscious", "not awake or aware of one's surroundings"),
        ),
    ),
    (
        151,
        "verb",
        (
            ("negotiate", "to discuss terms in order to reach an agreement"),
            ("suspect", "to think something is likely without proof"),
            ("propose", "to put forward a plan or idea"),
            ("acknowledge", "to recognize or accept a fact"),
            ("emphasize", "to give particular importance to something"),
            ("question", "to express doubt about the truth or value of something"),
            ("reconsider", "to think again about a decision"),
            ("weigh up", "to carefully compare advantages and disadvantages"),
        ),
    ),
    (
        176,
        "noun",
        (
            ("rent", "a regular payment for using someone else's property"),
            ("budget", "a plan for how available money will be spent"),
            ("deposit", "money held as security against damage or failure to meet an agreement"),
            ("bill", "a statement of money owed for goods or services"),
            ("charge", "an amount of money demanded for goods or services"),
            ("loan", "money lent with an obligation to repay it"),
            ("savings", "money kept rather than spent"),
            ("expense", "a cost incurred in obtaining something"),
            ("income", "money received regularly from work or investments"),
            ("discount", "a reduction in the usual selling price"),
            ("bargain", "something bought at a favorable low price"),
            ("installment", "one of several partial payments for a debt"),
            ("bank transfer", "movement of money between bank accounts"),
            ("landlord", "a person who rents property to a tenant"),
            ("tenant", "a person who pays to occupy rented property"),
        ),
    ),
    (
        176,
        "verb",
        (
            ("afford", "to have enough money to pay for something"),
            ("owe", "to be obliged to pay or return money"),
            ("repay", "to pay back borrowed money"),
            ("purchase", "to buy something"),
            ("invest", "to put money into something hoping for profit"),
            ("withdraw", "to take money out of a bank account"),
        ),
    ),
    (
        176,
        "adjective",
        (
            ("affordable", "inexpensive enough to be paid for"),
            ("costly", "costing a large amount of money"),
            ("financial", "relating to money or the management of money"),
        ),
    ),
    (
        216,
        "noun",
        (
            ("appointment", "an arrangement to meet or receive a service at a set time"),
            ("deadline", "the latest time by which something must be completed"),
            ("delay", "a period of waiting beyond the expected time"),
            ("refund", "money returned to someone who has paid for goods or services"),
            ("booking", "an arrangement reserving a service or place"),
            ("reservation", "an arrangement keeping a place or service available for someone"),
            ("queue", "a line of people waiting for a service"),
            ("request", "an act of asking for something"),
            ("confirmation", "a message stating that an arrangement is definite"),
            ("cancellation", "the act of calling off an arrangement"),
            ("enquiry", "a request for information"),
            ("assistance", "help provided to someone"),
            ("fault", "a defect that prevents something from working properly"),
            ("guarantee", "a promise to repair or replace a faulty product"),
            ("warranty", "a written promise about a product's condition and repairs"),
            ("replacement", "a thing supplied instead of another"),
            ("service charge", "an additional payment for a service"),
            ("opening hours", "the times when a business is open"),
        ),
    ),
    (
        216,
        "verb",
        (
            ("cancel", "to call off an arranged event or service"),
            ("reschedule", "to arrange a different time for an appointment"),
            ("postpone", "to arrange for something to happen later"),
            ("reserve", "to arrange to keep something for later use"),
            ("resolve", "to find a satisfactory solution to a problem"),
        ),
    ),
    (
        216,
        "adjective",
        (
            ("urgent", "requiring prompt attention or action"),
            ("convenient", "fitting a person's needs or plans"),
            ("flexible", "able to change to suit different circumstances"),
        ),
    ),
    (
        227,
        "adverb",
        (
            ("nevertheless", "despite what has just been said"),
            ("consequently", "as a result of what has just been stated"),
            ("moreover", "introducing an additional supporting point"),
            ("furthermore", "introducing additional information supporting an argument"),
            ("similarly", "in a comparable way"),
            ("specifically", "in a precise or particular way"),
            ("occasionally", "sometimes but not often"),
            ("currently", "at the present time"),
            ("initially", "at the beginning"),
            ("necessarily", "as an inevitable result or requirement"),
            ("equally", "to the same degree"),
            ("ultimately", "in the end after other events"),
            ("significantly", "to a degree that matters"),
            ("roughly", "approximately rather than exactly"),
            ("rarely", "not often"),
            ("normally", "under usual conditions"),
            ("increasingly", "to a growing extent"),
            ("formerly", "in the past but no longer"),
            ("subsequently", "after a previously mentioned event"),
            ("constantly", "continually or very frequently"),
            ("namely", "introducing a more exact identification"),
            ("essentially", "in the most important or basic respects"),
            ("afterwards", "at a later time"),
            ("notably", "especially or in a way worth mentioning"),
            ("readily", "easily and without difficulty"),
            ("effectively", "in a way that produces the intended result"),
            ("sufficiently", "to an adequate degree"),
            ("shortly", "soon or after a short time"),
            ("thoroughly", "completely and with great care"),
            ("literally", "in the exact basic meaning of the words"),
            ("partially", "to some extent but not completely"),
            ("precisely", "exactly and accurately"),
            ("regularly", "at repeated intervals or according to a pattern"),
            ("besides", "introducing an additional reason or consideration"),
            ("presumably", "according to what is reasonably supposed"),
            ("admittedly", "introducing a fact accepted despite weakening one's argument"),
        ),
    ),
    (
        296,
        "noun",
        (
            ("colleague", "a person with whom one works"),
            ("salary", "regular fixed payment for employment"),
            ("responsibility", "a duty or task one is expected to carry out"),
            ("shift", "a scheduled period of work"),
            ("unemployment", "the state of being without paid work while seeking employment"),
            ("promotion", "advancement to a higher position at work"),
            ("qualification", "a skill or credential making someone suitable for a job"),
            ("vacancy", "an unfilled job position"),
            ("staff", "the people employed by an organization"),
            ("workforce", "all the workers in an organization or country"),
            ("profession", "a type of skilled work requiring specialized training"),
            ("wage", "payment to a worker usually based on hours worked"),
            ("overtime", "time worked beyond normal working hours"),
            ("pension", "regular payment received after retirement"),
            ("retirement", "the period or act of leaving paid work permanently"),
            ("workload", "the amount of work someone is expected to do"),
            ("skill", "the ability to perform an activity well"),
            ("probation", "an initial employment period used to assess suitability"),
        ),
    ),
    (
        296,
        "verb",
        (
            ("resign", "to voluntarily leave one's employment position"),
            ("recruit", "to find and engage people for jobs"),
            ("retire", "to stop working permanently because of age or choice"),
            ("supervise", "to oversee someone's work"),
        ),
    ),
    (
        296,
        "adjective",
        (
            ("qualified", "having the skills or credentials required for a job"),
            ("professional", "showing competence and conduct expected in skilled work"),
            ("experienced", "having knowledge or skill from practice"),
            ("competent", "able to do something adequately"),
            ("permanent", "continuing indefinitely rather than temporary"),
            ("temporary", "lasting only for a limited period"),
        ),
    ),
    (
        312,
        "noun",
        (
            ("expectation", "a belief about what another person will or should do"),
            ("misunderstanding", "a failure to understand someone correctly"),
            ("apology", "an expression of regret for wrongdoing"),
            ("compromise", "an agreement reached through mutual concessions"),
            ("confidence", "trust in one's own abilities"),
            ("sympathy", "understanding or concern for another person's difficulties"),
            ("resentment", "bitterness about perceived unfair treatment"),
            ("conflict", "serious disagreement between people"),
            ("cooperation", "the act of working together"),
            ("commitment", "a firm promise or dedication to a person or purpose"),
            ("boundary", "a limit on acceptable personal behavior in a relationship"),
            ("rejection", "refusal to accept a person or their offer"),
            ("encouragement", "support that gives someone confidence"),
        ),
    ),
    (
        312,
        "verb",
        (
            ("apologize", "to express regret for something wrong one has done"),
            ("appreciate", "to recognize and value someone's help or qualities"),
            ("respect", "to consider another person's feelings or rights"),
            ("blame", "to hold someone responsible for a fault"),
            ("insult", "to speak or behave offensively toward someone"),
            ("comfort", "to ease another person's distress"),
        ),
    ),
    (
        312,
        "adjective",
        (
            ("considerate", "taking care not to inconvenience or hurt others"),
            ("thoughtful", "showing consideration for other people"),
            ("supportive", "giving help or encouragement"),
            ("sincere", "expressing feelings that are genuinely held"),
            ("awkward", "causing social discomfort or embarrassment"),
            ("sensitive", "easily affected emotionally"),
        ),
    ),
    (312, "adverb", (("politely", "in a respectful manner considering other people's feelings"),)),
    (
        341,
        "noun",
        (
            ("account", "registered access to an online service associated with a user"),
            ("password", "a secret sequence authenticating access to a system"),
            ("notification", "a digital alert informing a user of an event"),
            ("permission", "authorization to access a digital resource or device capability"),
            ("link", "a reference that opens another digital document or location"),
            ("attachment", "a file sent together with an electronic message"),
            ("folder", "a named location used to organize computer files"),
            ("backup", "a saved copy of data for use if the original is lost"),
            ("subscription", "an arrangement for recurring access to a service or content"),
            ("update", "a new version of software or information"),
            ("headline", "the title of a news report"),
            ("rumor", "an unverified story circulating among people"),
            ("misinformation", "false or inaccurate information"),
        ),
    ),
    (
        341,
        "verb",
        (
            ("download", "to transfer data from another system to one's device"),
            ("upload", "to transfer data from one's device to another system"),
            ("subscribe", "to sign up for recurring content or access to a service"),
            ("browse", "to look through online pages or information"),
            ("install", "to put software onto a device so it can be used"),
            ("delete", "to remove stored computer information"),
            ("log in", "to gain access to a computer system using credentials"),
            ("log out", "to end one's authenticated access to a computer system"),
            ("forward", "to send a received electronic message to another person"),
        ),
    ),
    (
        341,
        "adjective",
        (
            ("reliable", "consistently trustworthy as a source of information"),
            ("misleading", "giving an inaccurate impression"),
            ("secure", "protected against unauthorized access"),
            ("accurate", "correct and free from error"),
            ("relevant", "closely connected to the matter being considered"),
            ("electronic", "using electronic devices or systems"),
        ),
    ),
)

# Existing GUIDs and exact meanings reviewed against the local database.
# No prerequisite already below 999 is moved. Re-run after reviewing any
# intervening manual level changes: LevelMove checks headword, not old level.
EXISTING_MOVES: tuple[LevelMove, ...] = (
    LevelMove("V18_001", "prevent", 134),
    LevelMove("N16_019", "prescription", 134),
    LevelMove("N16_015", "dose", 134),
    LevelMove("V04_082", "disagree", 151),
    LevelMove("V09_122", "advise", 151),
    LevelMove("V09_121", "refuse", 151),
    LevelMove("V09_034", "justify", 151),
    LevelMove("V04_087", "intend", 151),
    LevelMove("V09_117", "predict", 151),
    LevelMove("V04_078", "conclude", 151),
    LevelMove("V04_092", "infer", 151),
    LevelMove("V04_096", "deduce", 151),
    LevelMove("V04_076", "contrast", 151),
    LevelMove("V09_107", "admit", 151),
    LevelMove("N59_064", "contract", 176),
    LevelMove("N55_051", "lease", 176),
    LevelMove("N24_301", "schedule", 216),
    LevelMove("N17_312", "requirement", 216),
    LevelMove("V09_162", "arrange", 216),
    LevelMove("C99_044", "whereas", 227),
    LevelMove("N36_107", "employee", 296),
    LevelMove("N36_153", "occupation", 296),
    LevelMove("N50_215", "reference", 296),
    LevelMove("V06_065", "employ", 296),
    LevelMove("V08_047", "dismiss", 296),
    LevelMove("N23_038", "loyalty", 312),
    LevelMove("N23_039", "relief", 312),
    LevelMove("N52_025", "browser", 341),
    LevelMove("N54_065", "privacy", 341),
    LevelMove("N17_316", "consent", 341),
)


def build_sense_lists() -> list[SenseList]:
    """Build POS-specific lists without remote requests or database access."""
    sense_lists: list[SenseList] = []
    for level, part_of_speech, senses in CATEGORY_SENSES:
        category_name = LEVEL_NAMES[level]
        entries = tuple(
            SenseEntry(term, hint=meaning, pos=part_of_speech, move=False, prominence="common")
            for term, meaning in senses
        )
        sense_lists.append(
            SenseList(
                level=level,
                domain=category_name,
                label=category_name.lower(),
                tags=("b1_b2_categories", f"b1_b2_{level}_{part_of_speech}"),
                entries=entries,
            )
        )
    return sense_lists


if __name__ == "__main__":
    raise SystemExit(run_sense_import(build_sense_lists(), __doc__ or "", moves=EXISTING_MOVES))
