# Agent Refactoring Status

## Recent Refactoring Pattern (7 commits)

The recent refactoring of ŠERNAS, VILKAS, VORAS, ŽVIRBLIS, VIEVERSYS, STRAZDAS, and LAPE established a consistent pattern:

### Key Changes:

1. **Get lemmas first** using `get_lemmas_for_agent(session, args)` from `agents.common.lemma_selection`
   - Returns a list whether processing one lemma (--guid) or many (--limit)
   - All subsequent processing works uniformly on this list

2. **Use shared display libraries**:
   - Import `display_language_header()` from `agents.common.cli_display`
   - Agent-specific display functions in agent subfolder's `cli_display.py` (if needed)

3. **NO "if args.guid" conditionals** after getting lemmas
   - Old pattern: separate code paths for single lemma vs batch
   - New pattern: unified code path, just different lemma list sizes

4. **Pass lemmas to agent methods** instead of having them query internally
   - Agent methods accept `lemmas: Optional[List[Lemma]] = None` parameter
   - No internal querying based on guid parameter

### Refactoring Commits:

1. **ŠERNAS** (9d01f0e): Refactor SERNAS agent to use shared utilities and unified processing
   - Move utilities to `agents/common/cli_display.py`
   - Create `agents/sernas/cli_display.py` for agent-specific display
   - Unified CLI processing - single lemmas list

2. **VILKAS** (89ed8cd): Clean up Vilkas and use new "agents/common" helpers
   - Use `get_lemmas_for_agent()` upfront
   - Remove all "if args.guid" checks
   - Pass lemmas to agent methods

3. **VORAS** (a2a87a4): Refactor voras agent to use shared utilities and unified lemma processing
   - Created `voras/cli_display.py` for display functions
   - No "if args.guid" conditionals
   - All processing on unified lemmas list

4. **ŽVIRBLIS** (eaeef7f): Refactor Žvirblis to use shared lemma selection and support all languages
   - Use `get_lemmas_for_agent()` instead of custom find_lemma_by_guid
   - Import display utilities from `agents.common.cli_display`
   - Remove "if args.guid" conditionals

5. **VIEVERSYS** (54505ff): Refactor VIEVERSYS to use shared lemma selection pattern
   - Use `get_lemmas_for_agent()` instead of find_lemma_by_guid
   - Remove "if args.guid" conditionals
   - Pass lemmas to generate_batch() method

6. **STRAZDAS** (54505ff): Refactor STRAZDAS to use shared lemma selection pattern
   - Use `get_lemmas_for_agent()` instead of find_lemma_by_guid
   - Remove "if args.guid" conditionals
   - Pass lemmas to generate_batch() method
   - Fix import paths (removed src. prefix)

7. **LAPE** (8441089): Refactor LAPE to use shared lemma selection pattern
   - Use `get_lemmas_for_agent()` instead of find_lemma_by_guid
   - Remove guid parameter from agent method
   - Remove guid handling inside agent method
   - Pass lemmas to generate_grammar_facts() method
   - Fix import paths (removed src. prefix)
   - Filter lemmas by required POS types inside agent

---

## Agents Status

### ✅ REFACTORED (Following new pattern):

1. **ŠERNAS** (sernas/) - Synonym and Alternative Form Generator
   - ✅ Uses `get_lemmas_for_agent()`
   - ✅ Has `sernas/cli_display.py` subfolder
   - ✅ No "if args.guid" conditionals
   - ✅ Passes lemmas to agent methods

2. **VILKAS** (vilkas/) - Word Forms Checker
   - ✅ Uses `get_lemmas_for_agent()`
   - ✅ No "if args.guid" conditionals
   - ✅ Passes lemmas to agent methods

3. **VORAS** (voras/) - Translation Agent
   - ✅ Uses `get_lemmas_for_agent()`
   - ✅ Has `voras/cli_display.py` subfolder
   - ✅ No "if args.guid" conditionals
   - ✅ Passes lemmas to agent methods

4. **ŽVIRBLIS** (zvirblis.py) - Single-file agent
   - ✅ Uses `get_lemmas_for_agent()`
   - ✅ No "if args.guid" conditionals
   - ✅ Uses shared cli_display

5. **VIEVERSYS** (vieversys.py) - OpenAI TTS Audio Generation
   - ✅ Uses `get_lemmas_for_agent()`
   - ✅ No "if args.guid" conditionals
   - ✅ Passes lemmas to generate_batch()
   - ✅ Uses correct import paths (agents.common)

6. **STRAZDAS** (strazdas.py) - eSpeak-NG Audio Generation
   - ✅ Uses `get_lemmas_for_agent()`
   - ✅ No "if args.guid" conditionals
   - ✅ Passes lemmas to generate_batch()
   - ✅ Fixed import paths (removed src. prefix)

7. **LAPE** (lape.py) - Grammar Facts Generator
   - ✅ Uses `get_lemmas_for_agent()`
   - ✅ No "if args.guid" conditionals
   - ✅ Passes lemmas to generate_grammar_facts()
   - ✅ Fixed import paths (removed src. prefix)
   - ✅ Agent method accepts lemmas, not guid

---

### ⚠️ NEEDS REFACTORING (Still has old pattern):

1. **DRAMBLYS** (dramblys/) - Missing Words Detection
   - ❌ Has "if args.guid" in cli.py
   - ❌ Uses old pattern
   - 📁 Has subfolder structure (could add cli_display.py)
   - Uses `from src.agents.common.common_args` (needs to remove `src.` prefix)
   - ⚠️ NOTE: --guid doesn't make sense for this agent (finding missing words can't be done for just one word)

2. **LOKYS** (lokys.py) - English Lemma Validation
   - ❌ Has "if args.guid" conditionals
   - ❌ Uses `find_lemma_by_guid` directly
   - 📄 Single file agent
   - ⚠️ Has Barsukas API integration (check if API needs updates)
   - Uses `from src.agents.common` (needs to remove `src.` prefix)

3. **PAPUGA** (papuga.py) - Pronunciation Validation
   - ❌ Has "if args.guid" conditionals
   - ❌ Uses `find_lemma_by_guid` directly
   - 📄 Single file agent
   - ⚠️ Has Barsukas API integration (check if API needs updates)
   - Uses `from src.agents.common` (needs to remove `src.` prefix)

---

### ✅ NO REFACTORING NEEDED (Special-purpose agents):

1. **UNGURYS** (ungurys.py) - WireWord Export Agent
   - ℹ️ Export agent, doesn't process individual lemmas with --guid
   - No --guid parameter

2. **BEBRAS** (bebras/) - Sentence-Word Link Management
   - ℹ️ Sentence processing agent, not lemma-based
   - Has subfolder structure
   - No --guid parameter for lemmas

3. **BUIVOLAS** (buivolas.py) - Simple Pattern Sentence Generation
   - ℹ️ Sentence generation agent, not lemma-based
   - No --guid parameter

4. **ELNIAS** (elnias.py) - Bootstrap Export Agent
   - ℹ️ Export agent, doesn't process individual lemmas
   - No --guid parameter

5. **POVAS** (povas.py) - HTML Generation for POS Subtypes
   - ℹ️ HTML generation agent, not lemma-based
   - No --guid parameter

6. **PRADZIA** (pradzia.py) - Database Initialization Agent
   - ℹ️ Database initialization, not lemma-based
   - No --guid parameter

---

## Refactoring Checklist

For each agent that needs refactoring:

### CLI Changes (cli.py or single-file agent):

- [ ] Remove all `if args.guid:` conditionals
- [ ] Add `from agents.common.lemma_selection import get_lemmas_for_agent`
- [ ] Add `from agents.common.cli_display import display_language_header`
- [ ] Call `get_lemmas_for_agent(session, args)` once at the start
- [ ] Use `len(lemmas) == 1` instead of `args.guid` if checking for single lemma
- [ ] Pass `lemmas` to all agent methods
- [ ] Fix import paths (remove `src.` prefix if present)

### Agent Method Changes (agent.py):

- [ ] Update methods to accept `lemmas: Optional[List[Lemma]] = None` parameter
- [ ] Remove `guid` parameter from methods
- [ ] Remove internal querying based on guid
- [ ] Filter lemmas list if needed (e.g., by POS type)

### Display Changes (optional):

- [ ] For agents with subfolder: Create `{agent}/cli_display.py` if complex display logic
- [ ] Move display functions from cli.py to cli_display.py
- [ ] Import and use display functions in cli.py

### Testing:

- [ ] Test with `--guid GUID` (single lemma)
- [ ] Test with `--limit N` (batch processing)
- [ ] Verify no "if args.guid" references remain (except in STYLE.md)
- [ ] Ensure agent methods work with lemmas list

---

## Priority Order for Refactoring

Based on complexity and usage:

1. ~~**DRAMBLYS**~~ - Has subfolder, but --guid doesn't make sense for this agent
2. **LOKYS** - Single file, Barsukas API integration, careful changes needed
3. **PAPUGA** - Single file, Barsukas API integration, careful changes needed
4. ~~**LAPE**~~ - ✅ **COMPLETED** (commit 8441089)
5. ~~**VIEVERSYS**~~ - ✅ **COMPLETED** (commit 54505ff, fixed in 1646c88)
6. ~~**STRAZDAS**~~ - ✅ **COMPLETED** (commit 54505ff, fixed in 1646c88)

---

## Notes

### About --guid Parameter:

- The `--guid` parameter itself is NOT removed from CLI
- It's still accepted and passed to `get_lemmas_for_agent()`
- The change is: NO conditional logic based on `args.guid` after getting lemmas
- `get_lemmas_for_agent()` handles it internally and returns appropriate list

### About Barsukas API:

Agents with Barsukas API integrations (LOKYS, PAPUGA, LAPE):
- Check if API endpoints in `src/barsukas/routes/agents.py` need updates
- Ensure API contract matches refactored agent interface
- Test API endpoints after refactoring

### About Display Libraries:

- **Shared**: `agents/common/cli_display.py` - language headers, common display
- **Agent-specific**: `agents/{agent}/cli_display.py` - complex agent-specific displays
- **When to create subfolder display**:
  - Agent has complex display logic (>50 lines)
  - Multiple display functions
  - Agent already has subfolder structure
  - Examples: SERNAS, VORAS have this

### About Import Paths:

Several agents still use `from src.agents.common` instead of `from agents.common`:
- DRAMBLYS
- LOKYS
- PAPUGA
- STRAZDAS
- LAPE

These should be updated to use `from agents.common` (without `src.` prefix) as per
project conventions.
