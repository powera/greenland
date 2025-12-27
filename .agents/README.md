# Greenland Database Agents

This directory contains Claude Code custom agents that wrap the Greenland database operation tools (src/agents).

## Available Agents

### Core Validation & Processing
- **lokys** - English lemma validation (forms and definitions)
- **dramblys** - Missing words detection and processing
- **vilkas** - Word forms generation (declensions, conjugations)
- **voras** - Multi-lingual translation management
- **papuga** - Pronunciation (IPA) validation and generation
- **sernas** - Synonym and alternative form generation

### Audio Generation
- **strazdas** - eSpeak-NG audio generation
- **vieversys** - OpenAI TTS audio generation

### Export & Utilities
- **ungurys** - WireWord export
- **elnias** - Bootstrap export
- **bebras** - Sentence-word link management
- **zvirblis** - Sentence generation

## How These Agents Work

Each agent is a Claude Code custom agent that knows:
1. What the underlying Python tool does
2. How to invoke it with the correct PYTHONPATH
3. What command-line arguments are available
4. Common usage patterns and examples

## General Pattern

All agents follow this invocation pattern:
```bash
PYTHONPATH=src python3 src/agents/<agent-name> [options]
```

## Common Command-Line Arguments

Most agents support these standardized arguments:
- `--guid <guid>` - Process a single item by GUID
- `--db-path <path>` - Database path (usually auto-detected)
- `--model <model>` - LLM model to use (default: gpt-5-mini)
- `--limit <n>` - Maximum number of items to process
- `--output <file>` - Output JSON file for reports
- `--yes` - Skip confirmation prompts
- `--dry-run` - Preview changes without committing
- `--debug` - Enable debug logging

## Using These Agents

To use an agent, simply reference it in your conversation with Claude:
```
@lokys Can you validate the lemma with GUID abc123?
```

Claude will then understand how to invoke the lokys tool with the appropriate arguments.

## Agent Development

These agents were created as part of the command-line standardization effort. All underlying Python tools use the common_args module (src/agents/common_args.py) for consistent argument handling.
