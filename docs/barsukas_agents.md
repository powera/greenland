# Barsukas Agent Dependencies

This document describes the logical workflow dependencies between the various Barsukas agents used to build and maintain the multilingual linguistic database.

## Overview

The agents are organized into a pipeline where each agent typically depends on the output of previous agents. The workflow is generally:

1. **Database Initialization** - Set up the base data structures
2. **Core Data Enrichment** - Add translations, word forms, and linguistic metadata
3. **Quality Validation** - Validate and correct existing data
4. **Sentence Generation** - Create example sentences
5. **Media Generation** - Generate audio files
6. **Export** - Output data in various formats for applications

## Agent Directory

All agents are Lithuanian animal names and live in `src/agents/`.

### Initialization Agents

#### Pradzia (Beginning)
- **Animal**: Beginning/Start (pradžia)
- **Purpose**: Database initialization, corpus management, rank calculation
- **Dependencies**: None (first agent to run)
- **Outputs**: Initialized database with base lemmas from corpora
- **Key Functions**:
  - Create/update database tables
  - Load word frequency corpora
  - Calculate combined frequency ranks
  - Bootstrap from JSON exports

---

### Enrichment Agents

#### Voras (Spider)
- **Animal**: Spider
- **Purpose**: Translation validator and populator - "weaves the web of translations"
- **Dependencies**: Pradzia (needs base lemmas)
- **Outputs**: Translations in multiple languages (Lithuanian, Chinese, French, Korean, Spanish, German, Portuguese, Swahili, Vietnamese)
- **Key Functions**:
  - Validate existing translations
  - Generate missing translations via LLM
  - Update translation quality scores

#### Vilkas (Wolf)
- **Animal**: Wolf
- **Purpose**: Multi-language word forms checker - "watchful guardian of word database"
- **Dependencies**: Voras (needs translations to generate forms)
- **Outputs**: Derivative forms for words (conjugations, declensions, plural forms, etc.)
- **Key Functions**:
  - Generate word forms for multiple languages
  - Validate existing forms
  - Support for Lithuanian, French, German, Spanish, Portuguese, English

#### Lape (Fox)
- **Animal**: Fox
- **Purpose**: Grammar facts generator - "clever and precise in analyzing grammar"
- **Dependencies**: Voras (needs translations for target language)
- **Outputs**: Language-specific grammatical metadata
- **Key Functions**:
  - Generate Chinese measure words/classifiers
  - Determine grammatical gender (French, Spanish, German, Lithuanian, etc.)
  - Extensible for other grammar fact types

#### Šernas (Boar)
- **Animal**: Boar
- **Purpose**: Synonym and alternative form generator - "persistent in finding similar things"
- **Dependencies**: Voras (needs translations)
- **Outputs**: Synonyms and alternative forms across multiple languages
- **Key Functions**:
  - Generate synonyms using LLM
  - Create alternative word forms
  - Multi-language support

---

### Validation Agents

#### Lokys (Bear)
- **Animal**: Bear
- **Purpose**: English lemma validation - "thorough and careful in checking quality"
- **Dependencies**: Pradzia (needs base lemmas), runs parallel to Voras
- **Outputs**: Validated and corrected English lemma forms and definitions
- **Key Functions**:
  - Validate lemma forms (e.g., "shoe" not "shoes")
  - Check definition quality
  - Identify disambiguation needs
  - Auto-correct issues via LLM

#### Papuga (Parrot)
- **Animal**: Parrot
- **Purpose**: Pronunciation validation and generation - "repeating sounds with perfect accuracy"
- **Dependencies**: Lokys (needs validated lemmas)
- **Outputs**: IPA and phonetic pronunciations
- **Key Functions**:
  - Validate existing pronunciations
  - Generate missing pronunciations
  - Focus on English pronunciations

#### Dramblys (Elephant)
- **Animal**: Elephant
- **Purpose**: Missing words detection - "never forgets what's missing"
- **Dependencies**: Lokys (needs validated base vocabulary)
- **Outputs**: Reports on missing vocabulary in sentences
- **Key Functions**:
  - Identify words used in sentences that don't have lemma entries
  - Suggest new vocabulary to add

---

### Sentence Generation Agents

#### Žvirblis (Sparrow)
- **Animal**: Sparrow
- **Purpose**: Sentence generation - "small but prolific, creating many examples"
- **Dependencies**: Voras (needs translations for target languages)
- **Outputs**: Example sentences with grammatical analysis in multiple languages
- **Key Functions**:
  - Generate contextual sentences featuring vocabulary words
  - Create translations across languages
  - Analyze grammatical structure
  - Calculate minimum difficulty level

#### Bebras (Beaver)
- **Animal**: Beaver
- **Purpose**: Sentence-word link management - "industrious builder of connections"
- **Dependencies**: Žvirblis (needs generated sentences)
- **Outputs**: Links between sentences and vocabulary words, database integrity
- **Key Functions**:
  - Link sentences to vocabulary via GUIDs
  - Check database integrity
  - Identify orphaned records

---

### Media Generation Agents

#### Vieversys (Lark)
- **Animal**: Lark
- **Purpose**: Audio generation - "bird known for its beautiful song"
- **Dependencies**: Voras (needs translations), Vilkas (needs grammatical forms for audio)
- **Outputs**: Audio files (MP3) for vocabulary words and their grammatical forms
- **Key Functions**:
  - Generate audio using OpenAI TTS API
  - Support multiple voices per language
  - Generate audio for base lemmas AND grammatical forms (conjugations, declensions, etc.)
  - Create audio quality review records
  - Generate manifests for S3 upload

---

### Export Agents

#### Ungurys (Eel)
- **Animal**: Eel
- **Purpose**: WireWord export - "swimming data downstream to external systems"
- **Dependencies**: Voras, Vilkas, Lape, Šernas, Vieversys (needs complete enriched data)
- **Outputs**: JSON files in WireWord API format
- **Key Functions**:
  - Export vocabulary data for Trakaido app
  - Support multiple languages
  - Create directory structures by difficulty level
  - Separate exports for verbs vs. other POS
  - Include synonyms and alternative forms

#### Elnias (Deer)
- **Animal**: Deer
- **Purpose**: Bootstrap export - "nimble and light, like this minimal export format"
- **Dependencies**: Voras (needs translations)
- **Outputs**: Minimal JSON format with just essential data
- **Key Functions**:
  - Export minimal vocabulary data
  - Include: English, target language, GUID, POS, subtype, difficulty level
  - Lightweight format for bootstrapping systems

#### Povas (Peacock)
- **Animal**: Peacock
- **Purpose**: HTML generation - "beautiful displays of information"
- **Dependencies**: Voras, Vilkas, Papuga (needs full enriched data)
- **Outputs**: Static HTML pages for vocabulary browsing
- **Key Functions**:
  - Generate HTML pages organized by POS subtypes
  - Create index and navigation pages
  - Display comprehensive linguistic information

#### Kiškis (Rabbit)
- **Animal**: Rabbit
- **Purpose**: Sentence export - "quick to deliver sentences everywhere"
- **Dependencies**: Žvirblis, Bebras (needs generated and linked sentences)
- **Outputs**: JSON files containing example sentences with translations
- **Key Functions**:
  - Export sentence data for language learning applications
  - Include sentence translations in multiple languages
  - Link sentences to vocabulary via GUIDs
  - Support filtering by difficulty level

---

## Workflow Pipeline

### Phase 1: Initialization
```
Pradzia (Database Init)
  ↓
  Creates base lemmas from word frequency corpora
```

### Phase 2: Core Enrichment (mostly parallel)
```
Pradzia → Voras (Translations)
  ├→ Vilkas (Word Forms)
  ├→ Lape (Grammar Facts)
  ├→ Šernas (Synonyms)
  └→ Žvirblis (Sentence Generation)
```

### Phase 3: Validation (parallel with enrichment)
```
Pradzia → Lokys (Lemma Validation)
  ├→ Papuga (Pronunciation Generation)
  └→ Dramblys (Missing Word Detection)
```

### Phase 4: Sentence Linking
```
Žvirblis → Bebras (Link Sentences to Vocabulary)
```

### Phase 5: Audio Generation
```
Voras → Vieversys (Audio - Base Lemmas)
Vilkas → Vieversys (Audio - Grammatical Forms)
```

### Phase 6: Export (all parallel, require complete data)
```
Complete Data → Ungurys (WireWord Export - needs Voras, Vilkas, Lape, Šernas, Vieversys)
              → Elnias (Bootstrap Export - needs Voras)
              → Povas (HTML Export - needs Voras, Vilkas, Papuga)
              → Kiškis (Sentence Export - needs Žvirblis, Bebras)
```

## Critical Dependencies

### Must Run Before Others
- **Pradzia** must run first to initialize the database and load base lemmas
- **Voras** must run before most enrichment agents since translations are fundamental

### Typical Execution Order
1. `pradzia` - Initialize database
2. `voras` - Generate/validate translations
3. `lokys` - Validate English lemmas (can run in parallel with Voras)
4. `vilkas`, `lape`, `šernas` - Generate enrichment data (parallel after Voras)
5. `papuga` - Generate pronunciations (after Lokys)
6. `žvirblis` - Generate sentences (after Voras)
7. `bebras` - Link sentences to vocabulary (after Žvirblis)
8. `vieversys` - Generate audio files for base lemmas (after Voras) AND grammatical forms (after Vilkas)
9. `ungurys`, `elnias`, `povas`, `kiškis` - Export data (after all enrichment complete)

### Optional/Maintenance Agents
- **Dramblys** - Run periodically to find missing vocabulary
- **Bebras** (integrity mode) - Run to check database consistency

## Viewing the Dependency Graph

To generate a visual graph from the DOT file:

```bash
# Install Graphviz if needed
brew install graphviz  # macOS
# or
sudo apt-get install graphviz  # Linux

# Generate PNG
dot -Tpng docs/barsukas_agents.gv -o docs/barsukas_agents.png

# Generate SVG
dot -Tsvg docs/barsukas_agents.gv -o docs/barsukas_agents.svg

# Generate PDF
dot -Tpdf docs/barsukas_agents.gv -o docs/barsukas_agents.pdf
```

## Notes

- All agent names are Lithuanian animal names, chosen for memorable and thematic naming
- Agents are designed to be idempotent where possible (can be run multiple times safely)
- Most agents support `--dry-run` mode to preview changes
- Agents use LLM APIs (OpenAI, Anthropic) for generation tasks, so they incur costs
- Export agents should be run last after all data enrichment is complete
