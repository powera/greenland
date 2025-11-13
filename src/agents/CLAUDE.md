# CLAUDE.md - Agents Architecture Guide

This document provides guidance for AI assistants working with or creating autonomous agents for the Greenland WordFreq database.

**Last Updated:** 2025-11-13

---

## Overview

Agents are autonomous Python scripts that perform database maintenance, quality assurance, and data processing tasks. Each agent is named after a Lithuanian animal and operates independently without user interaction, making them suitable for scheduled jobs or CI/CD pipelines.

**Philosophy:** Agents should be autonomous, idempotent, and safe to run multiple times.

---

## Agent Architecture Patterns

### Single-File Agents (Simple)

For straightforward agents with single responsibility:

```python
#!/usr/bin/env python3
"""
AgentName - Brief Description

"AgentName" means "animal" in Lithuanian - metaphor for what it does!
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

import constants
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import Lemma, DerivativeForm  # etc.

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MyAgent:
    """Agent for doing XYZ."""

    def __init__(self, db_path: str = None, debug: bool = False, model: str = "gpt-5-mini"):
        """Initialize the agent."""
        self.db_path = db_path or constants.WORDFREQ_DB_PATH
        self.debug = debug
        self.model = model

        if debug:
            logger.setLevel(logging.DEBUG)

    def get_session(self):
        """Get database session."""
        return create_database_session(self.db_path)

    def check(self, limit: int = None) -> dict:
        """
        Check for issues (read-only, no changes).

        Args:
            limit: Maximum items to check

        Returns:
            Dictionary with check results
        """
        logger.info("Running checks...")
        session = self.get_session()
        try:
            # Query database
            # Identify issues
            # Return results
            return {
                'total_checked': 0,
                'issues_found': 0,
                'issues': []
            }
        except Exception as e:
            logger.error(f"Error: {e}")
            return {'error': str(e)}
        finally:
            session.close()

    def fix(self, limit: int = None, dry_run: bool = False) -> dict:
        """
        Fix identified issues.

        Args:
            limit: Maximum items to fix
            dry_run: Preview changes without committing

        Returns:
            Dictionary with fix results
        """
        logger.info(f"{'DRY RUN: ' if dry_run else ''}Fixing issues...")
        session = self.get_session()
        try:
            # Get issues
            # Apply fixes
            if not dry_run:
                session.commit()
            else:
                session.rollback()

            return {
                'fixed': 0,
                'failed': 0
            }
        except Exception as e:
            logger.error(f"Error: {e}")
            session.rollback()
            return {'error': str(e)}
        finally:
            session.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="MyAgent - Description")
    parser.add_argument('--check', action='store_true', help='Run checks only')
    parser.add_argument('--fix', action='store_true', help='Fix issues')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes')
    parser.add_argument('--limit', type=int, help='Limit items to process')
    parser.add_argument('--model', default='gpt-5-mini', help='LLM model to use')
    parser.add_argument('--db-path', help='Custom database path')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation')

    args = parser.parse_args()

    agent = MyAgent(
        db_path=args.db_path,
        debug=args.debug,
        model=args.model
    )

    if args.check or not args.fix:
        results = agent.check(limit=args.limit)
        logger.info(f"Check results: {results}")

    if args.fix:
        if not args.yes:
            confirm = input("Proceed with fixes? [y/N]: ")
            if confirm.lower() != 'y':
                logger.info("Aborted")
                return 1

        results = agent.fix(limit=args.limit, dry_run=args.dry_run)
        logger.info(f"Fix results: {results}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
```

**Examples:** `lokys.py`, `papuga.py`, `pradzia.py`, `ungurys.py`, `zvirblis.py`

---

### Multi-Module Agents (Complex)

For agents with substantial logic, refactor into a subdirectory:

```
agents/
├── myagent.py              # Thin wrapper/entry point
└── myagent/                # Agent package
    ├── __init__.py         # Package exports
    ├── agent.py            # Main agent class
    ├── cli.py              # Command-line interface
    ├── coverage.py         # Reporting logic
    ├── batch.py            # Batch processing
    └── display.py          # Output formatting
```

**Wrapper pattern** (`myagent.py`):

```python
#!/usr/bin/env python3
"""
MyAgent - Brief Description

This is a compatibility wrapper that imports from the refactored myagent package.
The actual implementation is in agents/myagent/

"MyAgent" means "animal" in Lithuanian - metaphor!
"""

import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from agents.myagent.agent import MyAgent
from agents.myagent.cli import main

__all__ = ['MyAgent', 'main']

if __name__ == '__main__':
    main()
```

**Examples:** `voras/`, `bebras/`, `sernas/`, `vilkas/`, `dramblys/`

---

## Current Agents

### Core Database Management

| Agent | Lithuanian | Purpose |
|-------|-----------|---------|
| **Pradzia** | Beginning | Database initialization, corpus synchronization, frequency rank calculation |
| **Bebras** | Beaver | Database integrity checker (orphaned records, missing fields, sentence-word linking) |

### English Validation

| Agent | Lithuanian | Purpose |
|-------|-----------|---------|
| **Lokys** | Bear | English lemma validation (proper dictionary form, definitions, POS) |
| **Dramblys** | Elephant | Missing words detector (scans frequency corpora, auto-processes with LLM) |

### Multi-Language Processing

| Agent | Lithuanian | Purpose |
|-------|-----------|---------|
| **Voras** | Spider | Translation validator and populator (10 languages) |
| **Vilkas** | Wolf | Word forms checker (verb conjugations, noun declensions for 6 languages) |
| **Papuga** | Parrot | Pronunciation validation/generation (IPA and phonetic) |
| **Šernas** | Boar | Synonym and alternative form generator (10 languages) |

### Content Generation

| Agent | Lithuanian | Purpose |
|-------|-----------|---------|
| **Žvirblis** | Sparrow | Example sentence generator with automatic difficulty calculation |
| **Povas** | Peacock | HTML report generator (POS subtype pages with comprehensive data) |

### Export & Integration

| Agent | Lithuanian | Purpose |
|-------|-----------|---------|
| **Ungurys** | Eel | WireWord export agent (API format for external systems) |
| **Elnias** | Deer | WireWord bootstrap export (all levels) |

### Placeholder

| Agent | Lithuanian | Purpose |
|-------|-----------|---------|
| **Lape** | Fox | (Purpose to be determined) |

---

## Key Design Principles

### 1. Modes

All agents should support at least two modes:

- **Check Mode** (`--check`): Read-only reporting, no database changes
- **Fix Mode** (`--fix`): Make actual changes to database
- **Dry Run** (`--dry-run`): Preview changes without committing (used with `--fix`)

### 2. Idempotency

Agents must be safe to run multiple times. Running the same agent twice should:
- Not duplicate data
- Not corrupt existing data
- Produce consistent results

### 3. Logging

Use Python's `logging` module:
- `INFO` level for normal operations
- `WARNING` for potential issues
- `ERROR` for failures
- `DEBUG` for detailed diagnostics (enabled via `--debug`)

### 4. Error Handling

```python
try:
    # Database operations
    session.commit()
except Exception as e:
    logger.error(f"Error: {e}")
    session.rollback()
    return {'error': str(e)}
finally:
    session.close()
```

### 5. User Confirmation

For operations that make changes, require confirmation unless `--yes` flag is provided:

```python
if not args.yes:
    confirm = input(f"About to process {count} items. Continue? [y/N]: ")
    if confirm.lower() != 'y':
        logger.info("Aborted")
        return 1
```

### 6. Limits and Sampling

Support `--limit` to process subset of data:

```python
parser.add_argument('--limit', type=int, help='Maximum items to process')
parser.add_argument('--sample-rate', type=float, default=1.0,
                    help='Fraction to sample (0.0-1.0)')
```

### 7. Progress Reporting

For long-running operations, report progress:

```python
for i, item in enumerate(items, 1):
    if i % 10 == 0:
        logger.info(f"Processed {i}/{len(items)} items...")
```

---

## Common Patterns

### Database Access

```python
from wordfreq.storage.database import create_database_session

session = create_database_session(db_path)
try:
    # Do work
    session.commit()
except Exception as e:
    session.rollback()
    raise
finally:
    session.close()
```

### LLM Integration

```python
from wordfreq.tools.llm_validators import validate_lemma_form

result = validate_lemma_form(
    lemma_text="shoes",
    pos_type="noun",
    model="gpt-5-mini"
)

if not result['is_lemma']:
    logger.warning(f"Issue: {result['reason']}")
    logger.info(f"Suggested: {result['suggested_lemma']}")
```

### Batch Processing

```python
from clients.batch_queue import BatchQueue

queue = BatchQueue(model="gpt-4")
for item in items:
    queue.add(prompt=f"Process {item}")

results = queue.execute()
```

### Query Patterns

```python
from wordfreq.storage.models.schema import Lemma

# Get lemmas with GUIDs (curated words)
lemmas = session.query(Lemma).filter(
    Lemma.guid.isnot(None)
).order_by(Lemma.id).all()

# Get lemmas missing translations
lemmas_without_lt = session.query(Lemma).filter(
    Lemma.lithuanian.is_(None)
).all()

# Get with limit
lemmas = query.limit(100).all()
```

---

## Testing Agents

### Manual Testing

```bash
# Check mode (no changes)
python myagent.py --check

# Dry run (preview changes)
python myagent.py --fix --dry-run --limit 10

# Small batch with confirmation
python myagent.py --fix --limit 5

# Full run (skip confirmation)
python myagent.py --fix --yes
```

### Expected Behavior

1. **Check mode**: Should never modify database
2. **Dry run**: Should show what would change but not commit
3. **Fix mode**: Should only change what was reported in check mode
4. **Idempotency**: Running twice should not cause issues

---

## Adding a New Agent

1. **Choose a Lithuanian animal name** that metaphorically represents the agent's function
2. **Decide on architecture**:
   - Single file if logic is < 500 lines
   - Multi-module if complex or >500 lines
3. **Implement core methods**:
   - `__init__()` - Setup
   - `check()` - Read-only reporting
   - `fix()` - Make changes
4. **Add CLI with argparse**:
   - `--check`, `--fix`, `--dry-run`
   - `--limit`, `--yes`, `--debug`
   - `--db-path`, `--model`
5. **Add logging** throughout
6. **Test thoroughly**:
   - Check mode doesn't change data
   - Dry run doesn't commit
   - Fix mode is idempotent
7. **Document**:
   - Update `README.md` with full documentation
   - Update this `CLAUDE.md` agent roster
   - Update main `/CLAUDE.md` agent section

---

## Common Pitfalls

### ❌ Don't

```python
# Making changes in check mode
def check(self):
    lemma.definition = "new value"
    session.commit()  # BAD!

# Not handling errors
def fix(self):
    session.query(Lemma).update(...)  # No try/except

# Hardcoding paths
db_path = "/home/user/greenland/src/wordfreq/data/linguistics.sqlite"

# No confirmation for destructive operations
def fix(self):
    session.query(Lemma).delete()  # No confirmation!
```

### ✅ Do

```python
# Check mode is read-only
def check(self):
    issues = []
    lemmas = session.query(Lemma).all()
    for lemma in lemmas:
        if self._has_issue(lemma):
            issues.append(lemma)
    return {'issues': issues}

# Proper error handling
def fix(self):
    try:
        session.query(Lemma).update(...)
        session.commit()
    except Exception as e:
        logger.error(f"Error: {e}")
        session.rollback()
    finally:
        session.close()

# Use constants
from constants import WORDFREQ_DB_PATH
db_path = db_path or WORDFREQ_DB_PATH

# Require confirmation
if not args.yes:
    confirm = input("Delete all lemmas? [y/N]: ")
    if confirm.lower() != 'y':
        return
```

---

## Agent Naming Convention

Choose Lithuanian animal names that metaphorically represent the agent's function:

- **Lokys** (Bear) - Thorough and careful validation
- **Voras** (Spider) - Weaving web of translations
- **Dramblys** (Elephant) - Never forgets missing words
- **Bebras** (Beaver) - Builds solid structures (integrity)
- **Vilkas** (Wolf) - Watchful guardian of forms
- **Šernas** (Boar) - Persistent in finding similar things
- **Papuga** (Parrot) - Repeats sounds with accuracy
- **Žvirblis** (Sparrow) - Small but prolific
- **Povas** (Peacock) - Beautiful displays
- **Ungurys** (Eel) - Swimming data downstream

Avoid:
- Names already used by other agents
- Names that don't fit the metaphor
- Non-animal words

---

## Integration Points

### Database Models

Agents interact with SQLAlchemy models from `wordfreq.storage.models.schema`:
- `Lemma` - Base word meanings
- `WordToken` - Specific spellings
- `DerivativeForm` - Grammatical forms
- `LemmaTranslation` - Multi-language translations
- `Sentence`, `SentenceTranslation`, `SentenceWord` - Example sentences
- `GrammarFact` - Synonyms, alternatives, pronunciations
- `OperationLog` - Audit trail

### LLM Tools

Use utilities from `wordfreq.tools.llm_validators`:
- `validate_lemma_form()` - Check if word is in lemma form
- `validate_definition()` - Validate definition quality
- `validate_pronunciation()` - Check IPA/phonetic
- `generate_pronunciation()` - Generate missing pronunciations

### Clients

Use unified LLM client from `clients.unified_client`:
- `UnifiedClient(model="gpt-4")` - Single queries
- `BatchQueue(model="gpt-4")` - Batch processing

---

## For AI Assistants

When creating or modifying agents:

1. **Always follow the architecture pattern** - Don't reinvent the wheel
2. **Check existing agents** for similar functionality before creating new ones
3. **Maintain idempotency** - Critical for production use
4. **Add comprehensive logging** - Helps with debugging
5. **Support dry-run mode** - Users need to preview changes
6. **Handle errors gracefully** - Database operations can fail
7. **Update documentation** - Both README.md and CLAUDE.md
8. **Test all modes** - check, fix, dry-run must all work correctly

When asked to create a new agent:
1. Ask user for the agent's purpose and Lithuanian name
2. Determine if single-file or multi-module is appropriate
3. Follow the architecture pattern above exactly
4. Add all standard arguments and modes
5. Include logging, error handling, and user confirmation
6. Test with check, dry-run, and fix modes
7. Update documentation

---

**Remember:** Agents should be autonomous, safe, and maintainable. When in doubt, look at existing agents like `lokys.py` or `voras/` for reference.
