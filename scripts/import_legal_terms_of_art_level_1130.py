#!/usr/bin/env python3
"""Import the legal terms of art -- the multi-word phrases of the law.

Levels 400 and 1070 take single words from the legal_scotus corpus, by Zipf skew
and by corpus exclusivity respectively. Both miss the vocabulary that carries
the most legal meaning per token, because a frequency list over whitespace
tokens cannot see it: "ex post facto" is three ordinary words, "voir dire" is
two words that are not English at all, and "res ipsa loquitur" is Latin whose
parts mean nothing to a reader who does not already know the doctrine.  This
list is assembled from the standard terminology rather than mined from a corpus.

Most entries are Latin or Law French; the rest are English phrases fixed enough
that their meaning is not the sum of their parts ("fruit of the poisonous tree",
"void for vagueness").

These are wanted primarily for **tokenizing**: the point is that the database
knows "habeas corpus" is one lexical unit rather than two words, so a sentence
containing it segments correctly.

This script drives ``api.lemmas.add_term``, not ``add_word``, and that is the
whole reason it is shaped differently from its siblings. ``add_word`` asks the
LLM what a word's senses are and which part of speech each takes. For a
borrowed term there is no such answer to find: asked about "ex post facto" the
model looks for a native English headword, and invents one. So the POS, subtype
and definition are supplied here -- they are facts about the terminology that a
curated list already knows -- and the server's LLM is asked for the
translations alone.

No untranslatability marking is involved. A term that Romance and Baltic legal
writing borrows unchanged comes back as itself in each language, which is a
correct translation rather than an absent one; the prompt says so explicitly.
Entries whose translations come back incomplete are named in the run summary.

Subtypes are real where the term has one. ``noun/legal_concept`` takes the
doctrines, standards and property interests (stare decisis, probable cause, fee
simple); ``noun/legal_document`` takes the writs, orders and pleas, which are
things served on someone rather than ideas (subpoena, mandamus, nolo
contendere). Procedures go to the existing ``noun/process_event`` (voir dire,
arraignment) and the roles to ``noun/human`` (testator, guardian ad litem),
both of which already fit. A catch-all ``*_other`` here -- only "inter alia"
needs one -- is a deliberate statement that the term has no better subtype, and
the terms endpoint honors it rather than diverting it to the pending queue the
way ``add_word`` would.

Running without ``--execute`` only prints the plan and makes no HTTP requests.

These fixed legal phrases join the other specialist legal vocabulary at topic
level 1130.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlist_import_helper import TermEntry, run_term_import

DIFFICULTY_LEVEL = 1130

# Applied to every lemma this script creates, so the band is selectable without
# reading the level number.
TAGS: Sequence[str] = ("legal",)

# Standard legal terminology, not a corpus extract.  Checked against
# ``words_exist`` and against the preceding general and topic wordlists, which is what
# removed the bare forms already claimed there ("certiorari", "indictment" and
# "tolling" belong to topic level 1070, so they appear here only inside a longer phrase
# such as "equitable tolling").  "information" and "standing" are omitted
# entirely: both are already in the database in their ordinary senses, and the
# legal sense of each is a disambiguation of that lemma rather than a new one.
#
# Trimmed of terms that are either dictionary curiosities rather than working
# vocabulary ("profit a prendre", "autrefois acquit") or transparent enough that
# a tokenizer gains nothing from holding them together ("burden of proof").
TERMS: Sequence[TermEntry] = (
    # --- Latin adjectives and adverbial doctrines -------------------------
    TermEntry(
        "ex post facto",
        "adjective",
        "legal",
        "applying to acts committed before the law was passed",
    ),
    TermEntry(
        "prima facie",
        "adjective",
        "legal",
        "sufficient to establish a fact unless disproved",
    ),
    TermEntry("de facto", "adjective", "legal", "existing in practice though not by law"),
    TermEntry("de jure", "adjective", "legal", "existing by law, whatever the practice"),
    TermEntry("de novo", "adjective", "legal", "reheard from the beginning, giving no deference"),
    TermEntry("sui generis", "adjective", "legal", "of its own kind, fitting no existing category"),
    TermEntry("ultra vires", "adjective", "legal", "beyond the legal power of the body that acted"),
    TermEntry("bona fide", "adjective", "legal", "made or held in good faith"),
    TermEntry("pro se", "adjective", "legal", "representing oneself without a lawyer"),
    TermEntry("pro bono", "adjective", "legal", "done without charge in the public interest"),
    TermEntry("ab initio", "adjective", "legal", "void or valid from the very beginning"),
    TermEntry("in personam", "adjective", "legal", "directed against a specific person"),
    TermEntry("in rem", "adjective", "legal", "directed against a thing rather than a person"),
    TermEntry("malum in se", "adjective", "legal", "wrong in itself, apart from any statute"),
    TermEntry("malum prohibitum", "adjective", "legal", "wrong only because a statute forbids it"),
    TermEntry("per curiam", "adjective", "legal", "issued by the court collectively, unsigned"),
    TermEntry("ex parte", "adjective", "legal", "with only one party present or heard"),
    TermEntry("in camera", "adjective", "legal", "heard privately in chambers"),
    TermEntry("in limine", "adjective", "legal", "decided before trial, on the threshold"),
    TermEntry("nunc pro tunc", "adjective", "legal", "given retroactive effect to an earlier date"),
    TermEntry("in forma pauperis", "adjective", "legal", "allowed to proceed without paying fees"),
    TermEntry("pro hac vice", "adjective", "legal", "permitted to appear for this one case"),
    TermEntry("per stirpes", "adjective", "legal", "divided among heirs by family branch"),
    TermEntry("per capita", "adjective", "legal", "divided equally among individuals"),
    TermEntry("ad litem", "adjective", "legal", "appointed for the purposes of this lawsuit"),
    TermEntry("in re", "adjective", "legal", "in the matter of, naming a case with no opponent"),
    TermEntry(
        "guardian ad litem",
        "noun",
        "human",
        "a person appointed to represent someone's interests in a lawsuit",
    ),
    TermEntry("inter alia", "adverb", "adverb_other", "among other things"),
    # --- Latin doctrines and maxims ---------------------------------------
    TermEntry(
        "habeas corpus",
        "noun",
        "legal_document",
        "a judicial order testing the lawfulness of someone's detention",
    ),
    TermEntry(
        "amicus curiae",
        "noun",
        "human",
        "a non-party who files a brief to advise the court",
    ),
    TermEntry(
        "stare decisis",
        "noun",
        "legal_concept",
        "the principle that courts follow their own earlier decisions",
    ),
    TermEntry(
        "res judicata",
        "noun",
        "legal_concept",
        "the bar on relitigating a claim already finally decided",
    ),
    TermEntry("mens rea", "noun", "legal_concept", "the guilty state of mind a crime requires"),
    TermEntry("actus reus", "noun", "legal_concept", "the physical act a crime requires"),
    TermEntry(
        "res ipsa loquitur",
        "noun",
        "legal_concept",
        "the inference of negligence from an accident that speaks for itself",
    ),
    TermEntry(
        "respondeat superior",
        "noun",
        "legal_concept",
        "an employer's liability for acts of its employees",
    ),
    TermEntry(
        "quantum meruit",
        "noun",
        "legal_concept",
        "recovery of the reasonable value of services rendered",
    ),
    TermEntry(
        "corpus delicti",
        "noun",
        "legal_concept",
        "proof that the crime charged actually occurred",
    ),
    TermEntry(
        "obiter dictum",
        "noun",
        "communication_information",
        "a remark in a judgment not necessary to the decision",
    ),
    TermEntry(
        "ratio decidendi",
        "noun",
        "legal_concept",
        "the reasoning essential to a decision, which binds later courts",
    ),
    TermEntry(
        "forum non conveniens",
        "noun",
        "legal_concept",
        "the power to decline a case better heard elsewhere",
    ),
    TermEntry(
        "lis pendens",
        "noun",
        "legal_concept",
        "notice that litigation affecting a property is pending",
    ),
    TermEntry(
        "nolo contendere",
        "noun",
        "legal_document",
        "a plea accepting punishment without admitting guilt",
    ),
    TermEntry(
        "nolle prosequi",
        "noun",
        "legal_document",
        "a prosecutor's formal abandonment of a charge",
    ),
    TermEntry(
        "caveat emptor",
        "noun",
        "legal_concept",
        "the rule that a buyer bears the risk of a purchase",
    ),
    TermEntry("quid pro quo", "noun", "legal_concept", "something given in return for something"),
    TermEntry(
        "subpoena duces tecum",
        "noun",
        "legal_document",
        "an order to appear and bring specified documents",
    ),
    TermEntry(
        "mandamus",
        "noun",
        "legal_document",
        "an order compelling an official to perform a duty",
    ),
    TermEntry(
        "quo warranto",
        "noun",
        "legal_document",
        "a proceeding challenging someone's right to an office",
    ),
    # --- Law French and single-word terms of art --------------------------
    TermEntry(
        "voir dire",
        "noun",
        "process_event",
        "the questioning of prospective jurors or a witness",
    ),
    TermEntry(
        "laches",
        "noun",
        "legal_concept",
        "the loss of a claim through unreasonable delay in bringing it",
    ),
    TermEntry(
        "estoppel",
        "noun",
        "legal_concept",
        "a bar preventing someone contradicting an earlier position",
    ),
    TermEntry("tort", "noun", "legal_concept", "a civil wrong giving rise to liability"),
    TermEntry(
        "escheat",
        "noun",
        "process_event",
        "the reversion of property to the state when no heir exists",
    ),
    TermEntry(
        "servitude",
        "noun",
        "legal_concept",
        "a burden on land for the benefit of another's land",
    ),
    TermEntry("easement", "noun", "legal_concept", "a right to use another's land for a purpose"),
    TermEntry("covenant", "noun", "legal_concept", "a binding promise in a deed or contract"),
    TermEntry("intestate", "adjective", "legal", "having died without a valid will"),
    TermEntry("testator", "noun", "human", "a person who has made a will"),
    TermEntry("executor", "noun", "human", "a person appointed to carry out a will"),
    TermEntry(
        "remainderman",
        "noun",
        "human",
        "a person who inherits property after a prior interest ends",
    ),
    TermEntry(
        "arraignment", "noun", "process_event", "the hearing at which a defendant is charged"
    ),
    TermEntry("subpoena", "noun", "legal_document", "an order compelling testimony or evidence"),
    TermEntry(
        "mootness",
        "noun",
        "abstract_condition",
        "the state of a dispute that no longer needs deciding",
    ),
    TermEntry(
        "ripeness",
        "noun",
        "abstract_condition",
        "the state of a dispute being ready for judicial decision",
    ),
    # --- English doctrinal phrases ----------------------------------------
    TermEntry(
        "promissory estoppel",
        "noun",
        "legal_concept",
        "enforcement of a promise relied on to the promisee's detriment",
    ),
    TermEntry(
        "collateral estoppel",
        "noun",
        "legal_concept",
        "the bar on relitigating an issue already decided",
    ),
    TermEntry(
        "unjust enrichment",
        "noun",
        "legal_concept",
        "a benefit retained at another's expense that must be repaid",
    ),
    TermEntry("fee simple", "noun", "legal_concept", "absolute and inheritable ownership of land"),
    TermEntry(
        "life estate", "noun", "legal_concept", "an interest in property lasting for a lifetime"
    ),
    TermEntry(
        "tenancy in common",
        "noun",
        "legal_concept",
        "co-ownership with separately inheritable shares",
    ),
    TermEntry(
        "joint tenancy",
        "noun",
        "legal_concept",
        "co-ownership where a survivor takes the whole",
    ),
    TermEntry(
        "adverse possession",
        "noun",
        "legal_concept",
        "acquiring title by occupying land openly for long enough",
    ),
    TermEntry(
        "eminent domain",
        "noun",
        "legal_concept",
        "the state's power to take private property for public use",
    ),
    TermEntry(
        "double jeopardy",
        "noun",
        "legal_concept",
        "the bar on trying someone twice for the same offense",
    ),
    TermEntry(
        "due process",
        "noun",
        "legal_concept",
        "the fair procedure the state owes before depriving anyone of rights",
    ),
    TermEntry(
        "equal protection",
        "noun",
        "legal_concept",
        "the guarantee that law applies alike to those alike situated",
    ),
    TermEntry(
        "strict scrutiny",
        "noun",
        "legal_concept",
        "the most demanding standard of constitutional review",
    ),
    TermEntry(
        "substantive due process",
        "noun",
        "legal_concept",
        "the doctrine that some rights are beyond legislative reach",
    ),
    TermEntry(
        "void for vagueness",
        "adjective",
        "legal",
        "invalid because too unclear to give fair notice",
    ),
    TermEntry(
        "fruit of the poisonous tree",
        "noun",
        "legal_concept",
        "evidence tainted by the illegal search that produced it",
    ),
    TermEntry(
        "exclusionary rule",
        "noun",
        "legal_concept",
        "the rule barring illegally obtained evidence from trial",
    ),
    TermEntry(
        "probable cause",
        "noun",
        "legal_concept",
        "the reasonable ground required for a search or arrest",
    ),
    TermEntry(
        "reasonable suspicion",
        "noun",
        "legal_concept",
        "the lower ground justifying a brief investigative stop",
    ),
    TermEntry(
        "beyond a reasonable doubt",
        "noun",
        "legal_concept",
        "the standard of proof required to convict",
    ),
    TermEntry(
        "preponderance of the evidence",
        "noun",
        "legal_concept",
        "the civil standard of proof: more likely than not",
    ),
    TermEntry(
        "clear and convincing evidence",
        "noun",
        "legal_concept",
        "an intermediate standard of proof, above the civil one",
    ),
    TermEntry(
        "prima facie case",
        "noun",
        "legal_concept",
        "a showing sufficient to proceed unless rebutted",
    ),
    TermEntry(
        "summary judgment",
        "noun",
        "process_event",
        "judgment given without trial when no facts are disputed",
    ),
    TermEntry(
        "directed verdict",
        "noun",
        "process_event",
        "a verdict ordered by the judge when the evidence permits only one",
    ),
    TermEntry(
        "judgment notwithstanding the verdict",
        "noun",
        "process_event",
        "a judgment overriding the jury's verdict",
    ),
    TermEntry(
        "class action",
        "noun",
        "process_event",
        "a suit brought by representatives on behalf of a group",
    ),
    TermEntry(
        "political question",
        "noun",
        "legal_concept",
        "an issue the courts leave to the political branches",
    ),
    TermEntry(
        "sovereign immunity",
        "noun",
        "legal_concept",
        "the state's protection from being sued without consent",
    ),
    TermEntry(
        "qualified immunity",
        "noun",
        "legal_concept",
        "an official's protection from suit for acts not clearly unlawful",
    ),
    TermEntry(
        "felony murder",
        "noun",
        "legal_concept",
        "a killing during a felony, charged as murder without intent",
    ),
    TermEntry(
        "plea bargain",
        "noun",
        "legal_concept",
        "an agreed plea in exchange for a reduced charge or sentence",
    ),
    TermEntry(
        "statute of limitations",
        "noun",
        "legal_concept",
        "the deadline after which a claim can no longer be brought",
    ),
    TermEntry(
        "equitable tolling",
        "noun",
        "legal_concept",
        "the pausing of a limitations period for fairness",
    ),
)


if __name__ == "__main__":
    raise SystemExit(run_term_import(TERMS, DIFFICULTY_LEVEL, __doc__ or "", tags=TAGS))
