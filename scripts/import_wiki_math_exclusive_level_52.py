#!/usr/bin/env python3
"""Import the algebra, analysis, topology and the rest of mathematics vocabulary that only the wiki_math corpus attests.

Sourced from /word-tokens/corpus-skew?corpus=wiki_math&exclusive=1 -- not the
Zipf-delta list that levels 35-42 were drawn from, but its companion: the words
this corpus has and no other corpus in the collection does.  A word with no
"elsewhere" cannot be scored, so these are reported apart from the skew ranking;
they are also the sharper list, because being unattested everywhere else is a
stronger claim about a word's domain than merely being commoner here.

Level 52 continues from the skew batches at 35-42, reusing their corpora in
the same order.  These lists are disjoint; see the note on the word list below.

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

from scripts.wordlist_import_helper import run_import

DIFFICULTY_LEVEL = 52

# The corpus-exclusive words of wiki_math on 2026-08-29, ordered by their rank
# within the corpus and cut at 125, reduced to what words_exist does not already
# account for, then curated.  Dropped: capitalized tokens and tokens carrying
# digits or punctuation (proper nouns and possessives the exclusivity test cannot
# separate), tokens under four letters, mangled diacritics left by the corpus
# load ("thinsp", "mdash"), wiki markup fragments and
# participles whose headword survives in the list.  Plurals are dropped whenever
# the singular is an attested word at all, not merely when the singular also
# appears in this list -- the earlier, narrower rule left ~120 plurals behind; a
# few -s words that are their own lemma are kept (blues, goods, ethics, memoirs,
# archives, arts, texts, rights, peoples, relics).  Also dropped: words whose
# exclusivity is
# an accident of this corpus's register rather than a fact about their domain.
#
# A word exclusive to one corpus is by construction absent from the others, so
# these ten lists cannot collide with each other.  Words already claimed by
# import_unlinked_level_34.py and by the skew batches at 35-42 are removed here,
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
    "finitely",
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
    "theoretic",
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
    "positional",
    "morphism",
    "parametric",
    "zeta",
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


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
