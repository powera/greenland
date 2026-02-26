# Benchmark Index and Numbering Outline

This document captures the current benchmark lineup and numbering through `0299`.

## Numbering policy

- `001X`: word tokenization and string-level parsing benchmarks.
- `002X`: basic math benchmarks.
- `003X`–`009X`: word-level and sentence-level processing benchmarks.
- `0101`–`0149`: linguistics benchmarks (language, translation, morphology, sentence structure).
- `0150`–`0199`: knowledge benchmarks (facts, world knowledge, reasoning-over-facts).
- `021X`: maze and spatial puzzle benchmarks.
- `022X`: game-strategy benchmarks.
- `023X`: computer tool-use benchmarks (ed, regex, shell).
- `024X`: task-planning / blockworld benchmarks.

## Current implemented benchmarks

> Source of truth is the benchmark registry in `lib/utils/registry.py`.

| Code | Slug | Name | Category | Status |
|---|---|---|---|---|
| 0011 | `word_length` | Word Length | token processing | implemented |
| 0012 | `letter_count` | Letter Count | token processing | implemented |
| 0013 | `vowel_count` | Vowel Count | token processing | implemented |
| 0014 | `syllable_count` | Syllable Count | token processing | implemented |
| 0015 | `spell_check` | Spell Check | word processing | implemented |
| 0016 | `antonym` | Antonym Check | word processing | implemented |
| 0021 | `simple_arithmetic` | Simple Arithmetic | simple math | implemented |
| 0022 | `unit_conversion` | Unit Conversion | simple math | implemented |
| 0023 | `word_problems` | Math Word Problems | simple math | implemented |
| 0024 | `percentage_math` | Fractions and Percentages | simple math | implemented |
| 0025 | `algebra` | Algebra | simple math | implemented |
| 0026 | `time_arithmetic` | Time Arithmetic | simple math | implemented |
| 0027 | `geometry` | Geometry | simple math | implemented |
| 0031 | `definitions` | Definitions | word processing | implemented |
| 0032 | `part_of_speech` | Part of Speech | word processing | implemented |
| 0051 | `pinyin_letters` | Pinyin Letter Count | token processing | implemented |
| 0061 | `word_to_ipa` | Word to IPA | token processing | implemented |
| 0062 | `sentence_decomposition` | Sentence Decomposition | word processing | implemented |
| 0108 | `translation_en_fr` | Translation en_fr | translation | implemented |
| 0109 | `translation_en_zh` | Translation en_zh | translation | implemented |
| 0110 | `translation_sw_ko` | Translation sw_ko | translation | implemented |
| 0111 | `synonyms` | Multilingual Synonym Generation | word processing | implemented |
| 0121 | `verb_forms` | Verb Forms | word processing | implemented |
| 0122 | `lemma` | Lemma Identification | word processing | implemented |
| 0130 | `validate_lemma_form` | Validate Lemma Form (lokys) | agent regression | implemented |
| 0131 | `validate_definition` | Validate Definition (lokys) | agent regression | implemented |
| 0132 | `validate_translation` | Validate Translation (voras) | agent regression | implemented |
| 0151 | `geography` | Geography Knowledge | general knowledge | implemented |
| 0152 | `syllogism_validity` | Syllogism Validity | general knowledge | implemented |
| 0153 | `book_author_match` | Book Author Match | general knowledge | implemented |
| 0154 | `food_category_classification` | Food Category Classification | general knowledge | implemented |
| 0155 | `historical_event_year` | Historical Event Year | general knowledge | implemented |

## Numbering changes applied

- `0033_lemma` → `0122_lemma`.
- `0050_translation_en_fr` → `0108_translation_en_fr`.
- `0050_translation_en_zh` → `0109_translation_en_zh`.
- `0050_translation_sw_ko` → `0110_translation_sw_ko`.
- `0111_synonyms` is now explicitly registered and listed as implemented.
- `0035_simple_haystack` assets were removed from the repository.
- `0020_definitions` → `0031_definitions` (002X reserved for basic math; 003X for word processing).

## Proposed unimplemented additions

### 001X–009X: token/word/simple math

- `0034_pluralization` — singular/plural generation and validation.
- `0036_word_segmentation` — split compounds or run-on tokens into words.
- `0040_character_normalization` — Unicode/case/diacritic normalization checks.

### 0101–0149: linguistics

- `0105_reading_comprehension_short` — short paragraph QA with explicit answer spans.
- `0115_cultural_knowledge` — fact retrieval with multiple-choice distractors.
- `0140_cross_sentence_coreference` — pronoun/entity resolution across sentence pairs.
- `0145_sentence_reordering` — reconstruct coherent order from shuffled sentence chunks.

### 0150–0199: knowledge

- `0150_multihop_facts` — two-hop factual reasoning from short contexts.

### 021X–024X: planning, navigation, tool use

See the dedicated section below for the full proposed list.


## Overlap analysis (non-001X benchmarks)

The following overlapping pairs were reviewed. Benchmarks marked **keep** remain; any
consolidation is noted.

| Benchmark A | Benchmark B | Overlap | Decision |
|---|---|---|---|
| `0032_part_of_speech` | `0062_sentence_decomposition` | **High** – decomposition explicitly outputs POS tags for every token, so 0032 is a strict subset of 0062. | Keep both: 0032 isolates the POS signal; 0062 tests holistic token-level annotation. Acceptable duplication of signal. |
| `0016_antonym` | `0111_synonyms` | **Low-medium** – both probe lexical-semantic relationships, but in opposite directions and with different answer mechanics. | Keep both. |
| `0122_lemma` | `0130_validate_lemma_form` | **Medium** – both involve lemmatization. 0122 is a production task; 0130 is a binary validation + correction task. | Keep both; they are distinct task types (generate vs. validate). |
| `0108/0109/0110` (translation) | each other | **Medium** – identical methodology, different language pairs. | Keep all three; performance differences across language pairs are informative. |
| `0021_simple_arithmetic` | `0024_percentage_math` | **Low** – both require arithmetic, but 0024 adds ratio and percent-change semantics. | Keep both. |
| `0021_simple_arithmetic` | `0026_time_arithmetic` | **Low** – time arithmetic requires clock-domain knowledge (modular 60/24) on top of basic arithmetic. | Keep both. |

## Similar lemma-related benchmarks

- `0122_lemma`: core lemmatization task (given a word form, return lemma).
- `0130_validate_lemma_form`: agent-regression validator task (judge whether a form is lemma and suggest correction).
- They are related but not the same benchmark objective.

## Proposed benchmarks: 021X–024X

The 021X–024X range targets **planning, spatial reasoning, game strategy, and computer tool use**.
These require multi-step reasoning rather than a single fact lookup or arithmetic operation.

### 021X — Mazes and spatial puzzles

| Code | Slug | Name | Status | Notes |
|---|---|---|---|---|
| 0210 | `maze_navigation` | ASCII Maze Navigation | proposed | Given a maze rendered in ASCII (`#` walls, `.` open, `S` start, `E` end), produce the step sequence (N/S/E/W) to reach the exit. |
| 0211 | `sokoban` | Sokoban Puzzle | proposed | Given a small Sokoban board in ASCII, produce the player-move sequence that pushes all boxes onto goal squares. |
| 0212 | `hanoi` | Tower of Hanoi | proposed | Given N disks and 3 pegs, produce the minimal move sequence. N in range 3–6 to keep output tractable. |
| 0213 | `logic_grid` | Logic Grid Puzzle | proposed | Einstein/Zebra-style constraint satisfaction: given a set of clues, deduce the unique attribute assignment. |
| 0214 | `path_planning` | Grid Path Planning | proposed | Given a grid with obstacles and a start/end cell, produce the shortest path as a list of (row, col) steps. Validates correctness and optimality. |

### 022X — Game strategy

| Code | Slug | Name | Status | Notes |
|---|---|---|---|---|
| 0220 | `tictactoe` | Tic-Tac-Toe Strategy | proposed | Given a board state (X/O/empty), identify the winning move or the correct blocking move. |
| 0221 | `nim` | Nim / Combinatorial Game | proposed | Given a Nim heap configuration, identify the optimal move using Sprague–Grundy theory. |
| 0222 | `chess_endgame` | Chess Endgame | proposed | Simple endgame positions (K+Q vs K, K+R vs K); find mate in 1 or 2. |
| 0223 | `mastermind` | Mastermind / Code Deduction | proposed | Given a sequence of guesses with bull/cow feedback, deduce the hidden code or identify the next best guess. |

### 023X — Computer tool use

| Code | Slug | Name | Status | Notes |
|---|---|---|---|---|
| 0230 | `ed_golf` | Ed Command Golf | proposed | Given a source string and a target string, produce the shortest valid `ed` script that transforms source → target. Scored by command count. |
| 0231 | `regex_synthesis` | Regex Synthesis | proposed | Given a set of positive and negative example strings, produce a regular expression that accepts all positives and rejects all negatives. |
| 0232 | `program_trace` | Simple Program Trace | proposed | Given a tiny program in a well-defined toy language (assignments, if, while with bounded iterations), trace execution and report final variable values. |
| 0233 | `jq_transform` | jq / JSON Transformation | proposed | Given an input JSON document and a natural-language description of the desired transformation, produce the correct `jq` filter. |

### 024X — Task planning (blockworld)

| Code | Slug | Name | Status | Notes |
|---|---|---|---|---|
| 0240 | `blockworld` | Blockworld Task Planning | proposed | Given a start stack configuration and a goal configuration, produce the minimal ordered `move(block, from, to)` sequence. |
| 0241 | `dependency_ordering` | Dependency Ordering | proposed | Given a set of tasks with prerequisite constraints, produce a valid topological ordering. |
| 0242 | `resource_scheduling` | Resource Scheduling | proposed | Given tasks with durations and shared-resource constraints, produce a valid schedule minimising total completion time. |
