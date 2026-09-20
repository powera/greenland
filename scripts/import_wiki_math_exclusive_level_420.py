#!/usr/bin/env python3
"""Import the algebra, analysis, topology and the rest of mathematics vocabulary that only the wiki_math corpus attests.

Sourced from /word-tokens/corpus-skew?corpus=wiki_math&exclusive=1 -- not the
Zipf-delta list that levels 330-400 were drawn from, but its companion: the words
this corpus has and no other corpus in the collection does.  A word with no
"elsewhere" cannot be scored, so these are reported apart from the skew ranking;
they are also the sharper list, because being unattested everywhere else is a
stronger claim about a word's domain than merely being commoner here.

Thirty-nine broadly useful mathematics words form a general-curriculum sample
at level 420. The remaining terms belong to the mathematics extension at topic
level 1080.

This script deliberately uses the public ``ROOT/api`` facade.  In particular,
``api.lemmas.add_word`` runs Barsukas' intelligent word workflow: the server's
LLM identifies the senses and supplies their translations, then the server
selects and stores the useful senses.  The script never supplies definitions or
translations itself.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlist_import_helper import run_domain_import

DIFFICULTY_LEVEL = 420
TOPIC_DIFFICULTY_LEVEL = 1080

# The corpus-exclusive words of wiki_math on 2026-08-29, ordered by their rank
# within the corpus and cut at 125, reduced to what words_exist does not already
# account for, then curated.  Dropped: capitalized tokens and tokens carrying
# digits or punctuation (proper nouns and possessives the exclusivity test cannot
# separate), tokens under four letters, mangled diacritics left by the corpus
# load ("thinsp", "mdash"), wiki markup fragments and
# participles whose headword survives in the list, fragments that occur mainly
# inside compounds ("theoretic", "finitely"), dominantly non-mathematical words
# ("positional") and bare Greek letter names ("zeta").  Plurals are dropped whenever
# the singular is an attested word at all, not merely when the singular also
# appears in this list -- the earlier, narrower rule left ~120 plurals behind; a
# few -s words that are their own lemma are kept (blues, goods, ethics, memoirs,
# archives, arts, texts, rights, peoples, relics).  Also dropped: words whose
# exclusivity is
# an accident of this corpus's register rather than a fact about their domain.
#
# A word exclusive to one corpus is by construction absent from the others, so
# these ten lists cannot collide with each other.  Words already claimed by
# import_unlinked_level_320.py and by the skew batches at 330-400 are removed here,
# since those lists were drawn from the same token table.
WORDS: Sequence[str] = (
    "algebraic",
    "polynomial",
    "topology",
    "graph",
    "multiplication",
    "topological",
    "commutative",
    "decimal",
    "abelian",
    "quadratic",
    "exponential",
    "axiom",
    "digit",
    "tangent",
    "trigonometric",
    "holomorphic",
    "isomorphism",
    "vertex",
    "quadrilateral",
    "projective",
    "quotient",
    "homology",
    "differentiable",
    "homotopy",
    "infinity",
    "logarithm",
    "associative",
    "determinant",
    "affine",
    "null",
    "numeral",
    "isomorphic",
    "polygon",
    "permutation",
    "convergence",
    "dynamical",
    "hyperbolic",
    "parabola",
    "subtraction",
    "computable",
    "stochastic",
    "combinatorics",
    "hyperbola",
    "binomial",
    "optimization",
    "regression",
    "conic",
    "multiplicative",
    "sine",
    "cosine",
    "estimator",
    "orthogonal",
    "axiomatic",
    "factorization",
    "polyhedron",
    "exponentiation",
    "sheaf",
    "homomorphism",
    "combinatorial",
    "countable",
    "exponent",
    "divisor",
    "subgroup",
    "functor",
    "diagonal",
    "subspace",
    "integrable",
    "cohomology",
    "factorial",
    "maximal",
    "infinitesimal",
    "propositional",
    "postulate",
    "computability",
    "distributive",
    "asymptotic",
    "irreducible",
    "morphism",
    "parametric",
    "cardinality",
    "quadrature",
    "recursive",
    "fractal",
    "parallelogram",
    "invertible",
    "modulo",
    "algebraically",
    "eigenvalue",
    "lemma",
    "noncommutative",
    "incompleteness",
    "recursion",
    "tiling",
    "simplicial",
    "unbiased",
    "automorphism",
    "deterministic",
    "homological",
    "trigonometry",
    "transitive",
    "homeomorphic",
    "bijective",
    "commutativity",
    "torus",
    "associativity",
    "closure",
    "covariance",
    "hypotenuse",
    "transcendental",
    "duality",
    "probabilistic",
    "homeomorphism",
    "antiderivative",
    "chaotic",
    "cryptography",
    "disjoint",
    "radians",
    "recurrence",
    "injective",
    "multivariate",
    "codomain",
)

GENERAL_WORDS: Sequence[str] = (
    "algebraic",
    "polynomial",
    "graph",
    "multiplication",
    "decimal",
    "quadratic",
    "exponential",
    "axiom",
    "digit",
    "tangent",
    "trigonometric",
    "vertex",
    "quadrilateral",
    "quotient",
    "infinity",
    "logarithm",
    "associative",
    "numeral",
    "polygon",
    "convergence",
    "parabola",
    "subtraction",
    "hyperbola",
    "optimization",
    "regression",
    "sine",
    "cosine",
    "exponent",
    "diagonal",
    "factorial",
    "postulate",
    "recursive",
    "fractal",
    "parallelogram",
    "recursion",
    "trigonometry",
    "closure",
    "hypotenuse",
    "radians",
)


if __name__ == "__main__":
    raise SystemExit(
        run_domain_import(
            WORDS,
            GENERAL_WORDS,
            DIFFICULTY_LEVEL,
            TOPIC_DIFFICULTY_LEVEL,
            __doc__ or "",
        )
    )
